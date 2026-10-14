#!/usr/bin/env python3
"""Queue deduplicated APHIS mailing-locality jobs; never call Geoapify."""
from __future__ import annotations

import argparse
import hashlib
import os
from collections import defaultdict

import psycopg

SOURCE_ID = "us.aphis"
PROFILE_ID = "geoapify-us-aphis-mailing-locality"
US_STATE_CODES = {"AL","AK","AS","AZ","AR","CA","CO","CT","DE","DC","FL","FM","GA","GU","HI","IA","ID","IL","IN","KS","KY","LA","MA","MD","ME","MH","MI","MN","MO","MP","MS","MT","NC","ND","NE","NH","NJ","NM","NV","NY","OH","OK","OR","PA","PR","PW","RI","SC","SD","TN","TX","UT","VA","VI","VT","WA","WI","WV","WY"}


def locality_query(city: str, state: str) -> str:
    state = " ".join(state.split()).upper()
    if state not in US_STATE_CODES:
        raise ValueError("invalid_us_mailing_state")
    return ", ".join((" ".join(city.split()), state, "United States"))


def activate(database_url: str, limit: int | None = None) -> dict[str, int]:
    with psycopg.connect(database_url) as connection, connection.transaction():
        if connection.execute("SELECT current_database()").fetchone()[0] != "uec_v0_api_repair":
            raise RuntimeError("database_identity_invalid")
        rows = connection.execute("""WITH latest AS (
              SELECT snapshot_sha256 FROM real_preview.source_preview_runs
               WHERE source_id=%s ORDER BY created_at DESC,run_id DESC LIMIT 1)
            SELECT c.candidate_id,c.snapshot_sha256,c.source_group_key,c.country_code,
                   l.location_evidence->>'city',l.location_evidence->>'region',
                   m.source_artifact_sha256,m.source_url,m.retrieved_at,m.normalized_sha256,m.normalized_rows
              FROM real_preview.candidates c JOIN latest USING(snapshot_sha256)
              JOIN real_preview.candidate_private_location_evidence l USING(candidate_id)
              JOIN real_preview.source_manifests m ON m.source_id=c.source_id AND m.snapshot_sha256=c.snapshot_sha256
             WHERE c.source_id=%s AND c.country_code='US'
               AND NULLIF(BTRIM(l.location_evidence->>'city'),'') IS NOT NULL
               AND NULLIF(BTRIM(l.location_evidence->>'region'),'') IS NOT NULL
             ORDER BY c.candidate_id""", (SOURCE_ID, SOURCE_ID)).fetchall()
        grouped: dict[str, list[tuple]] = defaultdict(list)
        for row in rows:
            grouped[locality_query(str(row[4]), str(row[5]))].append(row)
        if limit is not None:
            grouped = dict(list(sorted(grouped.items()))[:limit])
        queued = targets = existing = 0
        for query, group in grouped.items():
            first = group[0]
            snapshot, artifact_sha, source_url, retrieved = first[1], first[6], first[7], first[8]
            connection.execute("""INSERT INTO uec.sources(source_id,country_code,name,official_url,access_method)
                VALUES (%s,'US','USDA APHIS Animal Care active directory',%s,'private_preview_mailing_locality')
                ON CONFLICT (source_id) DO NOTHING""", (SOURCE_ID, source_url))
            artifact = connection.execute("SELECT artifact_id FROM uec.raw_artifacts WHERE sha256=%s", (artifact_sha,)).fetchone()
            if artifact is None:
                raise RuntimeError("source_artifact_missing")
            artifact_id = artifact[0]
            key = "aphis-mailing-locality:" + hashlib.sha256((str(snapshot) + "\0" + query).encode()).hexdigest()
            connection.execute("""INSERT INTO uec.source_records(source_id,source_record_key,artifact_id,raw_fields,parsed_at)
                VALUES (%s,%s,%s,%s::jsonb,%s) ON CONFLICT DO NOTHING""",
                (SOURCE_ID, key, artifact_id, '{"projection":"real_preview_aphis_mailing_locality"}', retrieved))
            record_id = connection.execute("SELECT source_record_id FROM uec.source_records WHERE source_id=%s AND source_record_key=%s AND artifact_id=%s", (SOURCE_ID, key, artifact_id)).fetchone()[0]
            job = connection.execute("""INSERT INTO uec.geocode_jobs(source_record_id,provider_id,query)
                VALUES (%s,'geoapify',%s) ON CONFLICT (source_record_id,provider_id,query) DO NOTHING RETURNING job_id""", (record_id, query)).fetchone()
            job_id = job[0] if job else connection.execute("SELECT job_id FROM uec.geocode_jobs WHERE source_record_id=%s AND provider_id='geoapify' AND query=%s", (record_id, query)).fetchone()[0]
            queued += int(job is not None)
            connection.execute("""INSERT INTO uec.geocode_job_events(job_id,event_type,attempt_number,retryable,details)
                SELECT %s,'queued',1,false,%s::jsonb WHERE NOT EXISTS (SELECT 1 FROM uec.geocode_job_events WHERE job_id=%s)""",
                (job_id, '{"processing_mode":"private_geoapify_source_profile","profile_id":"geoapify-us-aphis-mailing-locality","location_role":"mailing_locality_only_not_operating_site"}', job_id))
            for candidate in group:
                inserted = connection.execute("""INSERT INTO real_preview.geocode_targets(job_id,candidate_id,snapshot_sha256,source_id,source_record_key)
                    VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING candidate_id""",
                    (job_id, candidate[0], candidate[1], SOURCE_ID, candidate[2])).fetchone()
                targets += int(inserted is not None)
                existing += int(inserted is None)
                connection.execute("""INSERT INTO real_preview.enrichment_state_events(candidate_id,snapshot_sha256,source_id,source_record_key,state_code,reason_code)
                    SELECT %s,%s,%s,%s,'queued','aphis_mailing_locality_profile'
                    WHERE NOT EXISTS (SELECT 1 FROM real_preview.enrichment_state_events WHERE candidate_id=%s AND reason_code='aphis_mailing_locality_profile')""",
                    (candidate[0], candidate[1], SOURCE_ID, candidate[2], candidate[0]))
        return {"unique_localities": len(grouped), "jobs_created": queued, "targets_created": targets, "targets_existing": existing}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.environ.get("UEC_DATABASE_URL"))
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    if not args.database_url or args.limit is not None and args.limit < 1:
        return 2
    try:
        summary = activate(args.database_url, args.limit)
    except Exception as error:
        print(f"activation_failed: {type(error).__name__}")
        return 1
    print("provider=geoapify source=us.aphis provider_calls=0 " + " ".join(f"{key}={value}" for key, value in summary.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
