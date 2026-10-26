#!/usr/bin/env python3
"""Queue current Germany BLtU street-address candidates for private Geoapify.

This stages durable worker jobs only. It performs no provider requests and
never includes establishment names in the query.
"""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path

import psycopg


SOURCE_ID = "de.locations"
PROFILE_ID = "geoapify-de-bltu"
DEFAULT_BATCH_SIZE = 500
DEFAULT_ARTIFACT = Path(r"D:\UntilEveryCage-Operations\source-captures\de-launch-20261025\accepted-shared-run-worker-target\runs\refresh-a9a6a0d172343491\sources\de.locations\acquisition\preview-de-locations-7b148310-cb9e-4f9f-bde3-a11a3a167b0e\bltu-general-list.csv")


def activate(database_url: str, *, limit: int = DEFAULT_BATCH_SIZE, offset: int = 0,
             artifact_path: str | Path = DEFAULT_ARTIFACT) -> dict[str, int]:
    if limit < 1 or offset < 0:
        raise ValueError("invalid DE batch limit or offset")
    with psycopg.connect(database_url) as connection, connection.transaction():
        if connection.execute("SELECT current_database()").fetchone()[0] != "uec_launch_sources_test_20261025":
            raise RuntimeError("database_identity_invalid")
        artifact_path = Path(artifact_path)
        artifact_digest = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
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
                      candidate.country_code,manifest.source_artifact_sha256,
                      manifest.source_url,manifest.retrieved_at,
                      private_location.location_evidence->>'address' AS street,
                      COALESCE(private_location.location_evidence->>'city',candidate.city) AS city,
                      COALESCE(private_location.location_evidence->>'postal_code',
                               (regexp_match(COALESCE(private_location.location_evidence->>'city',candidate.city),
                                             '^([0-9]{5})[[:space:]]+'))[1]) AS postal_code,
                      private_location.location_evidence->>'region' AS region
                 FROM real_preview.candidates candidate
                 JOIN latest ON latest.snapshot_sha256=candidate.snapshot_sha256
                 JOIN real_preview.candidate_private_location_evidence private_location
                   ON private_location.candidate_id=candidate.candidate_id
                 JOIN real_preview.source_manifests manifest
                   ON manifest.source_id=candidate.source_id
                  AND manifest.snapshot_sha256=candidate.snapshot_sha256
                 WHERE candidate.source_id=%s AND candidate.country_code='DE'
                   AND candidate.location_class <> 'numeric_source_coordinate'
                   AND NULLIF(BTRIM(private_location.location_evidence->>'address'),'') IS NOT NULL
                   AND NULLIF(BTRIM(COALESCE(private_location.location_evidence->>'city',candidate.city)),'') IS NOT NULL
                   AND COALESCE(private_location.location_evidence->>'postal_code',
                                (regexp_match(COALESCE(private_location.location_evidence->>'city',candidate.city),
                                              '^([0-9]{5})[[:space:]]+'))[1]) ~ '^[0-9]{5}$'
                 ORDER BY candidate.candidate_id
                 LIMIT %s OFFSET %s""",
            (SOURCE_ID, SOURCE_ID, SOURCE_ID, limit, offset),
        ).fetchall()
        if not rows:
            raise RuntimeError("DE Geoapify batch has no eligible current-snapshot street-address candidates")

        queued = targets = already = 0
        for candidate_id, snapshot, source_id, source_key, country, artifact_sha, source_url, retrieved, street, raw_city, postal, region in rows:
            city = raw_city
            if isinstance(city, str) and len(city) >= 6 and city[:5].isdigit() and city[5].isspace():
                city = city[6:].strip()
            if source_id != SOURCE_ID or country != "DE" or not street or not city or not postal or len(postal) != 5:
                raise RuntimeError("DE Geoapify candidate scope validation failed")
            if artifact_digest != artifact_sha:
                raise RuntimeError("DE preserved source artifact checksum does not match current manifest")
            artifact = connection.execute("SELECT artifact_id FROM uec.raw_artifacts WHERE sha256=%s", (artifact_sha,)).fetchone()
            if artifact is None:
                artifact = connection.execute(
                    """INSERT INTO uec.raw_artifacts(storage_key,sha256,byte_size,media_type,retrieved_at)
                       VALUES (%s,%s,%s,'text/csv',%s) RETURNING artifact_id""",
                    (str(artifact_path), artifact_sha, artifact_path.stat().st_size, retrieved),
                ).fetchone()
            artifact_id = artifact[0]
            projection_key = f"real-preview:{snapshot}:{source_key}"
            connection.execute(
                """INSERT INTO uec.sources(source_id,country_code,name,official_url,access_method)
                   VALUES (%s,'DE','German BVL approved establishments',%s,'private_preview_street_address_projection')
                   ON CONFLICT (source_id) DO NOTHING""", (SOURCE_ID, source_url),
            )
            connection.execute(
                """INSERT INTO uec.source_records(source_id,source_record_key,artifact_id,raw_fields,parsed_at)
                   VALUES (%s,%s,%s,%s::jsonb,%s) ON CONFLICT DO NOTHING""",
                (SOURCE_ID, projection_key, artifact_id, '{"projection":"real_preview_de_bltu_street_address"}', retrieved),
            )
            source_record_id = connection.execute(
                "SELECT source_record_id FROM uec.source_records WHERE source_id=%s AND source_record_key=%s AND artifact_id=%s",
                (SOURCE_ID, projection_key, artifact_id),
            ).fetchone()[0]
            if connection.execute("SELECT 1 FROM uec.public_access_restricted WHERE source_record_id=%s", (source_record_id,)).fetchone():
                raise RuntimeError("DE Geoapify candidate is restricted")

            query = ", ".join(part.strip() for part in (street, postal, city, region, "Germany") if part and part.strip())
            retained_job = connection.execute(
                """SELECT job.job_id,job.query FROM uec.geocode_jobs job
                   JOIN real_preview.geocode_targets target ON target.job_id=job.job_id
                   JOIN uec.geocode_job_events queued ON queued.job_id=job.job_id AND queued.event_type='queued'
                    AND queued.details->>'processing_mode'='private_geoapify_source_profile'
                    AND queued.details->>'profile_id'=%s
                   WHERE target.candidate_id=%s AND target.snapshot_sha256=%s
                     AND job.source_record_id=%s AND job.provider_id='geoapify'
                   ORDER BY target.created_at,job.created_at LIMIT 1""",
                (PROFILE_ID, candidate_id, snapshot, source_record_id),
            ).fetchone()
            if retained_job:
                query = retained_job[1]
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
                   VALUES (%s,%s,%s,%s,%s) ON CONFLICT (job_id,candidate_id) DO NOTHING
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
                "targets_created": targets, "already_present": already,
                "limit": limit, "offset": offset, "provider_calls": 0}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.environ.get("UEC_DATABASE_URL"))
    parser.add_argument("--limit", type=int, default=DEFAULT_BATCH_SIZE,
                        help="finite candidate batch size (default: 500)")
    parser.add_argument("--offset", type=int, default=0,
                        help="candidate-order offset for later finite batches")
    args = parser.parse_args()
    if not args.database_url or args.limit < 1 or args.offset < 0:
        return 2
    try:
        summary = activate(args.database_url, limit=args.limit, offset=args.offset)
    except Exception as error:
        sqlstate = getattr(error, "sqlstate", None)
        constraint = getattr(getattr(error, "diag", None), "constraint_name", None)
        print(f"activation_failed: {type(error).__name__} sqlstate={sqlstate} constraint={constraint}")
        return 1
    print("provider=geoapify source=de.locations " + " ".join(f"{key}={value}" for key, value in summary.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
