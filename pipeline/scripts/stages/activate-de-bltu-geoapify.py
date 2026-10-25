#!/usr/bin/env python3
"""Queue 24 current Germany BLtU street-address candidates for private Geoapify.

This stages durable worker jobs only. It performs no provider requests and
never includes establishment names in the query.
"""
from __future__ import annotations

import argparse
import os

import psycopg


SOURCE_ID = "de.locations"
PROFILE_ID = "geoapify-de-bltu"
PILOT_SIZE = 24


def activate(database_url: str) -> dict[str, int]:
    with psycopg.connect(database_url) as connection, connection.transaction():
        rows = connection.execute(
            """WITH latest AS (
                   SELECT COALESCE(
                       (SELECT run.snapshot_sha256 FROM real_preview.source_preview_runs run
                        WHERE run.source_id=%s ORDER BY run.created_at DESC,run.run_id DESC LIMIT 1),
                       (SELECT manifest.snapshot_sha256 FROM real_preview.source_manifests manifest
                        WHERE manifest.source_id=%s ORDER BY manifest.retrieved_at DESC,manifest.snapshot_sha256 DESC LIMIT 1)
                   ) AS snapshot_sha256
               )
               SELECT candidate.candidate_id,candidate.snapshot_sha256,
                      candidate.source_id,candidate.source_group_key,
                      candidate.country_code,candidate.representative_observation_id,
                      private_location.location_evidence->>'address' AS street,
                      private_location.location_evidence->>'postal_code' AS postal_code,
                      COALESCE(private_location.location_evidence->>'city',candidate.city) AS city
                 FROM real_preview.candidates candidate
                 JOIN latest ON latest.snapshot_sha256=candidate.snapshot_sha256
                 JOIN real_preview.candidate_private_location_evidence private_location
                   ON private_location.candidate_id=candidate.candidate_id
                 JOIN uec.observations observation
                   ON observation.observation_id=candidate.representative_observation_id
                 WHERE candidate.source_id=%s AND candidate.country_code='DE'
                   AND candidate.location_class <> 'numeric_source_coordinate'
                   AND NULLIF(BTRIM(private_location.location_evidence->>'address'),'') IS NOT NULL
                   AND NULLIF(BTRIM(COALESCE(private_location.location_evidence->>'city',candidate.city)),'') IS NOT NULL
                   AND observation.source_record_id IS NOT NULL
                   AND NOT EXISTS (SELECT 1 FROM uec.public_access_restricted restricted
                                   WHERE restricted.source_record_id=observation.source_record_id)
                 ORDER BY candidate.candidate_id
                 LIMIT %s""",
            (SOURCE_ID, SOURCE_ID, SOURCE_ID, PILOT_SIZE),
        ).fetchall()
        if len(rows) != PILOT_SIZE:
            raise RuntimeError("DE Geoapify pilot target set is smaller than the approved bounded size")

        queued = targets = already = 0
        for candidate_id, snapshot, source_id, source_key, country, observation_id, street, postal, city in rows:
            if source_id != SOURCE_ID or country != "DE" or not street or not city:
                raise RuntimeError("DE Geoapify candidate scope validation failed")
            observation = connection.execute(
                "SELECT source_record_id FROM uec.observations WHERE observation_id=%s",
                (observation_id,),
            ).fetchone()
            if observation is None:
                raise RuntimeError("DE Geoapify candidate observation is missing")
            source_record_id = observation[0]
            if connection.execute(
                "SELECT 1 FROM uec.public_access_restricted WHERE source_record_id=%s",
                (source_record_id,),
            ).fetchone():
                raise RuntimeError("DE Geoapify candidate became restricted")

            query = ", ".join(part.strip() for part in (street, postal, city, "Germany") if part and part.strip())
            job = connection.execute(
                """INSERT INTO uec.geocode_jobs(source_record_id,provider_id,query)
                   VALUES (%s,'geoapify',%s)
                   ON CONFLICT (source_record_id,provider_id,query) DO NOTHING
                   RETURNING job_id""",
                (source_record_id, query),
            ).fetchone()
            job_id = job[0] if job else connection.execute(
                "SELECT job_id FROM uec.geocode_jobs WHERE source_record_id=%s AND provider_id='geoapify' AND query=%s",
                (source_record_id, query),
            ).fetchone()[0]
            queued += int(job is not None)

            target = connection.execute(
                """INSERT INTO real_preview.geocode_targets
                       (job_id,candidate_id,snapshot_sha256,source_id,source_record_key)
                   VALUES (%s,%s,%s,%s,%s) ON CONFLICT (job_id) DO NOTHING
                   RETURNING candidate_id""",
                (job_id, candidate_id, snapshot, source_id, source_key),
            ).fetchone()
            if target is None:
                existing = connection.execute(
                    "SELECT candidate_id FROM real_preview.geocode_targets WHERE job_id=%s", (job_id,)
                ).fetchone()
                if existing is None or existing[0] != candidate_id:
                    raise RuntimeError("DE Geoapify job target identity conflicts")
                already += 1
            else:
                targets += 1

            event = connection.execute(
                """INSERT INTO uec.geocode_job_events(job_id,event_type,attempt_number,retryable,details)
                   SELECT %s,'queued',1,false,%s::jsonb
                   WHERE NOT EXISTS (SELECT 1 FROM uec.geocode_job_events WHERE job_id=%s)
                   RETURNING event_id""",
                (job_id, '{"processing_mode":"private_geoapify_source_profile","profile_id":"geoapify-de-bltu","query_components":["street","postal_code","city","country"]}', job_id),
            ).fetchone()
            if event is None:
                already += 1
            connection.execute(
                """INSERT INTO real_preview.enrichment_state_events
                       (candidate_id,snapshot_sha256,source_id,source_record_key,state_code,reason_code)
                   SELECT %s,%s,%s,%s,'queued','geoapify_de_bltu_profile'
                   WHERE NOT EXISTS (SELECT 1 FROM real_preview.enrichment_state_events
                                     WHERE candidate_id=%s AND reason_code='geoapify_de_bltu_profile')""",
                (candidate_id, snapshot, source_id, source_key, candidate_id),
            )
        return {"targets_selected": len(rows), "jobs_created": queued,
                "targets_created": targets, "already_present": already, "provider_calls": 0}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.environ.get("UEC_DATABASE_URL"))
    args = parser.parse_args()
    if not args.database_url:
        return 2
    try:
        summary = activate(args.database_url)
    except Exception as error:
        print(f"activation_failed: {type(error).__name__}")
        return 1
    print("provider=geoapify source=de.locations " + " ".join(f"{key}={value}" for key, value in summary.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
