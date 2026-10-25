"""Enqueue Spain municipality-only Geoapify jobs from retained verified evidence."""
from __future__ import annotations

import json
from typing import Any

SOURCE_ID = "es.locations"
PROFILE_ID = "geoapify-es-aesan-verified-municipality"


def verified_municipality_query(municipality: str, province: str) -> str:
    """Build a locality-only query; commas are rejected to preserve three exact fields."""
    values = (municipality, province)
    if any(not isinstance(value, str) or not value.strip() or "," in value for value in values):
        raise ValueError("verified_municipality_query_invalid")
    return f"{' '.join(municipality.split())}, {' '.join(province.split())}, Spain"


def activate(database_url: str, *, limit: int = 24, connect: Any = None) -> dict[str, int]:
    """Queue only municipality/province/country queries; never contact Geoapify."""
    if not 1 <= limit <= 24:
        raise ValueError("Spain municipality activation limit must be 1..24")
    if connect is None:
        import psycopg
        connect = psycopg.connect
    counts = {"evidence_available": 0, "evidence_ineligible": 0, "jobs_created": 0,
              "targets_created": 0, "provider_calls": 0}
    with connect(database_url) as connection, connection.transaction():
        if connection.execute("SELECT current_database()").fetchone()[0] != "uec_launch_sources_test_20261025":
            raise RuntimeError("database_identity_invalid")
        profile = connection.execute("""
            SELECT 1 FROM real_preview.private_geocoding_source_profiles
             WHERE profile_id=%s AND source_id=%s AND country_code='ES' AND enabled
        """, (PROFILE_ID, SOURCE_ID)).fetchone()
        if profile is None:
            raise RuntimeError("spain_verified_municipality_profile_unavailable")

        rows = connection.execute("""
            WITH latest AS (
                SELECT snapshot_sha256 FROM real_preview.source_preview_runs
                 WHERE source_id=%s ORDER BY created_at DESC,run_id DESC LIMIT 1
            ), latest_evidence AS (
                SELECT DISTINCT ON (evidence.candidate_id)
                       evidence.evidence_event_id,evidence.candidate_id,evidence.snapshot_sha256,
                       evidence.source_id,evidence.municipality,evidence.province,evidence.retrieved_at
                  FROM real_preview.spain_verified_locality_evidence evidence
                  JOIN latest USING(snapshot_sha256)
                 WHERE evidence.source_id=%s
                 ORDER BY evidence.candidate_id,evidence.retrieved_at DESC,evidence.evidence_event_id DESC
            )
            SELECT evidence.evidence_event_id,c.candidate_id,c.snapshot_sha256,c.source_group_key,
                   evidence.municipality,evidence.province,manifest.source_artifact_sha256,artifact.artifact_id,
                   c.country_code,c.location_class,c.default_map_scope,
                   location.location_evidence->>'country_code',
                   NOT EXISTS (
                       SELECT 1 FROM real_preview.geocode_targets target
                       JOIN uec.geocode_jobs job USING(job_id)
                       JOIN uec.public_access_restricted restricted USING(source_record_id)
                       WHERE target.candidate_id=c.candidate_id
                   ) AS restriction_clear
              FROM latest_evidence evidence
              JOIN real_preview.candidates c
                ON c.candidate_id=evidence.candidate_id AND c.snapshot_sha256=evidence.snapshot_sha256
               AND c.source_id=evidence.source_id
              JOIN real_preview.candidate_private_location_evidence location
                ON location.candidate_id=c.candidate_id
              JOIN real_preview.source_manifests manifest
                ON manifest.snapshot_sha256=c.snapshot_sha256 AND manifest.source_id=c.source_id
              JOIN uec.raw_artifacts artifact ON artifact.sha256=manifest.source_artifact_sha256
             WHERE evidence.source_id=%s AND c.country_code='ES'
             ORDER BY evidence.retrieved_at,evidence.evidence_event_id
             LIMIT %s
        """, (SOURCE_ID, SOURCE_ID, SOURCE_ID, limit)).fetchall()
        counts["evidence_available"] = len(rows)
        for row in rows:
            (evidence_id,candidate_id,snapshot,source_key,municipality,province,artifact_sha,artifact_id,
             country,location_class,map_scope,evidence_country,restriction_clear) = row
            if (country != "ES" or evidence_country != "ES" or location_class != "unmapped_private_observation"
                    or map_scope is not True or not artifact_sha or not artifact_id or not restriction_clear):
                counts["evidence_ineligible"] += 1
                continue
            try:
                query = verified_municipality_query(municipality, province)
            except ValueError:
                counts["evidence_ineligible"] += 1
                continue

            source_record_key = f"real-preview:spain-verified-municipality:{snapshot}:{evidence_id}"
            source_record = connection.execute("""
                INSERT INTO uec.source_records(source_id,source_record_key,artifact_id,raw_fields,parsed_at)
                VALUES (%s,%s,%s,%s::jsonb,now())
                ON CONFLICT (source_id,source_record_key,artifact_id) DO NOTHING
                RETURNING source_record_id
            """, (SOURCE_ID, source_record_key, artifact_id, json.dumps({
                    "projection": "real_preview_spain_verified_municipality_geocode_target",
                    "snapshot_sha256": snapshot,
                    "locality_evidence_event_id": str(evidence_id),
                }, sort_keys=True))).fetchone()
            if source_record is None:
                source_record = connection.execute("""
                    SELECT source_record_id FROM uec.source_records
                     WHERE source_id=%s AND source_record_key=%s AND artifact_id=%s
                """, (SOURCE_ID, source_record_key, artifact_id)).fetchone()
            if source_record is None:
                raise RuntimeError("spain_municipality_source_record_missing")
            source_record_id = source_record[0]
            if connection.execute("SELECT 1 FROM uec.public_access_restricted WHERE source_record_id=%s",
                                  (source_record_id,)).fetchone():
                counts["evidence_ineligible"] += 1
                continue
            job = connection.execute("""
                INSERT INTO uec.geocode_jobs(source_record_id,provider_id,query)
                VALUES (%s,'geoapify',%s)
                ON CONFLICT (source_record_id,provider_id,query) DO NOTHING
                RETURNING job_id
            """, (source_record_id, query)).fetchone()
            job_created = job is not None
            if job is None:
                job = connection.execute("""
                    SELECT job_id FROM uec.geocode_jobs
                     WHERE source_record_id=%s AND provider_id='geoapify' AND query=%s
                """, (source_record_id, query)).fetchone()
            if job is None:
                raise RuntimeError("spain_municipality_job_missing")
            job_id = job[0]
            counts["jobs_created"] += int(job_created)
            target = connection.execute("""
                INSERT INTO real_preview.geocode_targets
                    (job_id,candidate_id,snapshot_sha256,source_id,source_record_key)
                VALUES (%s,%s,%s,%s,%s)
                ON CONFLICT DO NOTHING RETURNING candidate_id
            """, (job_id,candidate_id,snapshot,SOURCE_ID,source_key)).fetchone()
            counts["targets_created"] += int(target is not None)
            connection.execute("""
                INSERT INTO uec.geocode_job_events(job_id,event_type,attempt_number,retryable,details)
                SELECT %s,'queued',1,false,%s::jsonb
                WHERE NOT EXISTS (SELECT 1 FROM uec.geocode_job_events WHERE job_id=%s)
            """, (job_id,json.dumps({
                    "processing_mode": "private_geoapify_source_profile",
                    "profile_id": PROFILE_ID,
                    "provider_configuration": PROFILE_ID,
                    "source_artifact_sha256": artifact_sha,
                    "locality_evidence_event_id": str(evidence_id),
                    "query_role": "verified_municipality_province_country_only",
                }, sort_keys=True),job_id))
            if target is not None:
                connection.execute("""
                    INSERT INTO real_preview.enrichment_state_events
                        (candidate_id,snapshot_sha256,source_id,source_record_key,state_code,reason_code)
                    VALUES (%s,%s,%s,%s,'queued','spain_verified_municipality_profile')
                """, (candidate_id,snapshot,SOURCE_ID,source_key))
    return counts
