#!/usr/bin/env python3
"""Attach existing AU NPI preview address targets to bounded Geoapify jobs.

This command only configures private queue rows. It does not call the provider,
reimport a source, or create a source snapshot. Worker requests remain a
separate explicit operation.
"""
from __future__ import annotations

import argparse
import os
import sys

import psycopg


PILOT_SIZE = 24
SOURCE_ID = "au.npi.facilities"
PLACEHOLDER_PROVIDER = "pending-provider-review"


def activate(database_url: str) -> dict[str, int]:
    with psycopg.connect(database_url) as connection:
        with connection.transaction():
            targets = connection.execute(
                """SELECT candidate.candidate_id, candidate.snapshot_sha256,
                          candidate.source_id, candidate.source_group_key,
                          candidate.country_code, placeholder.source_record_id,
                          placeholder.query
                     FROM real_preview.geocode_targets old_target
                     JOIN uec.geocode_jobs placeholder ON placeholder.job_id=old_target.job_id
                     JOIN real_preview.candidates candidate ON candidate.candidate_id=old_target.candidate_id
                     JOIN real_preview.candidate_private_location_evidence private_location
                       ON private_location.candidate_id=candidate.candidate_id
                    WHERE candidate.source_id=%s
                      AND candidate.country_code='AU'
                      AND candidate.location_class='city_postal'
                      AND placeholder.provider_id=%s
                      AND NULLIF(BTRIM(private_location.location_evidence->>'address'),'') IS NOT NULL
                    ORDER BY candidate.candidate_id""",
                (SOURCE_ID, PLACEHOLDER_PROVIDER),
            ).fetchall()
            if len(targets) != PILOT_SIZE:
                raise RuntimeError("AU Geoapify pilot target set is not the expected bounded size")

            activated = 0
            already_complete = 0
            for candidate_id, snapshot, source_id, source_key, country, source_record_id, query in targets:
                if country != "AU" or source_id != SOURCE_ID:
                    raise RuntimeError("AU Geoapify pilot source scope validation failed")
                job_id = connection.execute(
                    """INSERT INTO uec.geocode_jobs(source_record_id,provider_id,query)
                       VALUES (%s,'geoapify',%s)
                       ON CONFLICT (source_record_id,provider_id,query) DO NOTHING
                       RETURNING job_id""",
                    (source_record_id, query),
                ).fetchone()
                if job_id:
                    geoapify_job_id = job_id[0]
                else:
                    geoapify_job_id = connection.execute(
                        """SELECT job_id FROM uec.geocode_jobs
                           WHERE source_record_id=%s AND provider_id='geoapify' AND query=%s""",
                        (source_record_id, query),
                    ).fetchone()[0]

                existing_target = connection.execute(
                    "SELECT candidate_id FROM real_preview.geocode_targets WHERE job_id=%s",
                    (geoapify_job_id,),
                ).fetchone()
                if existing_target and existing_target[0] != candidate_id:
                    raise RuntimeError("existing Geoapify target identity conflicts with the pilot candidate")
                connection.execute(
                    """INSERT INTO real_preview.geocode_targets
                           (job_id,candidate_id,snapshot_sha256,source_id,source_record_key)
                       VALUES (%s,%s,%s,%s,%s) ON CONFLICT (job_id) DO NOTHING""",
                    (geoapify_job_id, candidate_id, snapshot, source_id, source_key),
                )
                created_event = connection.execute(
                    """INSERT INTO uec.geocode_job_events(job_id,event_type,attempt_number,retryable,details)
                       SELECT %s,'queued',1,false,
                              '{"processing_mode":"private_au_preview_pilot","provider_configuration":"geoapify_au_country_filter"}'::jsonb
                       WHERE NOT EXISTS (SELECT 1 FROM uec.geocode_job_events WHERE job_id=%s)
                       RETURNING event_id""",
                    (geoapify_job_id, geoapify_job_id),
                ).fetchone()
                if created_event:
                    activated += 1
                else:
                    already_complete += 1
                connection.execute(
                    """INSERT INTO real_preview.enrichment_state_events
                           (candidate_id,snapshot_sha256,source_id,source_record_key,state_code,reason_code)
                       SELECT %s,%s,%s,%s,'queued','geoapify_au_pilot_activated'
                       WHERE NOT EXISTS (
                           SELECT 1 FROM real_preview.enrichment_state_events
                           WHERE candidate_id=%s AND reason_code='geoapify_au_pilot_activated'
                       )""",
                    (candidate_id, snapshot, source_id, source_key, candidate_id),
                )
            return {"targets": len(targets), "queued": activated, "already_queued_or_terminal": already_complete}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=os.environ.get("UEC_DATABASE_URL", "postgresql://uec:uec-local-development-only@localhost:5433/uec"),
    )
    args = parser.parse_args()
    if not os.environ.get("GEOAPIFY_API_KEY", "").strip():
        print("blocked: GEOAPIFY_API_KEY is not configured; no queue changes made", file=sys.stderr)
        return 2
    try:
        summary = activate(args.database_url)
    except Exception as error:
        print(f"activation_failed: {type(error).__name__}; no provider calls made", file=sys.stderr)
        return 1
    print(
        "provider=geoapify source=au.npi.facilities "
        f"targets={summary['targets']} queued={summary['queued']} "
        f"already_queued_or_terminal={summary['already_queued_or_terminal']} provider_calls=0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
