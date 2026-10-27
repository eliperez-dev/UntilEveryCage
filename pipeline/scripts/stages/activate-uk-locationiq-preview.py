#!/usr/bin/env python3
"""Stage strict, source-scoped GB LocationIQ jobs without making provider calls."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
from typing import Any

import psycopg

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from pipeline.geocoding.locationiq import LocationIqAdapter
from pipeline.geocoding.private_profiles import profile_by_id

DATABASE = "uec_launch_sources_test_20261025"
FSA = "fsa_approved_establishments"
FSS = "fss_approved_establishments"
PROFILE_IDS = {FSA: "locationiq-gb-fsa-approved-establishments",
               FSS: "locationiq-gb-fss-approved-establishments"}
SOURCE_URLS = {
    FSA: "https://fsaopendata.blob.core.windows.net/opendatacatalog/Approved-Establishments-01-10-2026.csv",
    FSS: "https://www.foodstandards.gov.scot/sites/default/files/2026-09/Approved%20Establishments%20in%20Scotland_1.csv",
}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def canonical_uk_query(address_lines: Any, locality: Any, postcode: Any) -> str | None:
    """Return HOUSE ROAD, LOCALITY, POSTCODE, United Kingdom or None.

    Only a uniquely matched numbered-road subfield is sent to the provider;
    all other source address text (including names) is omitted.
    """
    return LocationIqAdapter.canonical_uk_query(address_lines, locality, postcode)


def _utc(value: Any) -> datetime | None:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(value, datetime) or value.utcoffset() is None:
        return None
    return value.astimezone(timezone.utc)


def _validate_provenance(source: str, run: dict[str, Any], manifest: dict[str, Any],
                         acquisition: Any) -> dict[str, Any]:
    if source not in PROFILE_IDS or not isinstance(acquisition, dict):
        raise ValueError("verified_uk_acquisition_missing")
    retrieved = _utc(run.get("retrieved_at"))
    manifest_retrieved = _utc(manifest.get("retrieved_at"))
    acquisition_retrieved = _utc(acquisition.get("retrieved_at_utc"))
    digest, normalized = run.get("source_artifact_sha256"), run.get("normalized_sha256")
    adapter, schema = run.get("adapter_version"), run.get("schema_version")
    source_url = manifest.get("source_url")
    if (not isinstance(digest, str) or not _SHA256.fullmatch(digest)
            or manifest.get("source_artifact_sha256") != digest or acquisition.get("sha256") != digest
            or not isinstance(normalized, str) or not _SHA256.fullmatch(normalized)
            or manifest.get("normalized_sha256") != normalized
            or run.get("imported_observation_count") != manifest.get("normalized_rows")
            or type(run.get("imported_observation_count")) is not int
            or not isinstance(adapter, str) or manifest.get("code_version") != adapter
            or not isinstance(schema, str) or manifest.get("config_version") != schema
            or acquisition.get("adapter_version") != adapter
            or acquisition.get("config_version", acquisition.get("schema_version")) != schema
            or acquisition.get("source_id") != source or acquisition.get("run_id") != run.get("run_id")
            or source_url != SOURCE_URLS[source] or acquisition.get("final_url") != source_url
            or run.get("source_url") != source_url
            or retrieved is None or manifest_retrieved is None
            or manifest_retrieved > retrieved or retrieved != acquisition_retrieved
            or retrieved > datetime.now(timezone.utc)
            or type(acquisition.get("byte_size")) is not int or acquisition["byte_size"] < 1
            or run.get("processing_mode") != "live_acquisition"
            or run.get("acquisition_classification") != "live"
            or run.get("fresh_live_run") is not True
            or not isinstance(acquisition.get("terms_review"), dict)
            or acquisition["terms_review"].get("decision") != "approved"):
        raise ValueError("uk_source_manifest_acquisition_binding_mismatch")
    return {"source_artifact_sha256": digest, "source_artifact_byte_size": acquisition["byte_size"],
            "source_url": source_url, "retrieved_at": retrieved,
            "normalized_sha256": normalized, "normalized_rows": run["imported_observation_count"],
            "adapter_version": adapter, "schema_version": schema}


def _ensure_linkage(connection: Any, source: str, snapshot: str, source_key: str,
                    metadata: dict[str, Any]) -> Any:
    connection.execute("""INSERT INTO uec.sources(source_id,country_code,name,official_url,access_method)
        VALUES(%s,'GB',%s,%s,'private_preview_address_enrichment') ON CONFLICT(source_id) DO NOTHING""",
        (source, {FSA: "Food Standards Agency approved establishments",
                  FSS: "Food Standards Scotland approved establishments"}[source], metadata["source_url"]))
    identity = connection.execute("SELECT country_code,official_url,access_method FROM uec.sources WHERE source_id=%s",
                                  (source,)).fetchone()
    source_urls = {metadata["source_url"]}
    if source == FSA:
        source_urls.add("https://fsaopendata.blob.core.windows.net/opendatacatalog/Approved-Establishments-01-09-26.csv")
    # A monthly capture has its own verified artifact URL. Do not rewrite the
    # shared source row merely because its earlier capture used another month.
    if (identity is None or identity[0] != "GB" or identity[1] not in source_urls
            or identity[2] != "private_preview_address_enrichment"):
        raise ValueError("uk_source_identity_mismatch")
    digest = metadata["source_artifact_sha256"]
    connection.execute("""INSERT INTO uec.raw_artifacts(storage_key,sha256,byte_size,media_type,retrieved_at)
        VALUES(%s,%s,%s,'text/csv',%s) ON CONFLICT(sha256) DO NOTHING""",
        (f"private-preview-source-artifact:{source}:{digest}", digest,
         metadata["source_artifact_byte_size"], metadata["retrieved_at"]))
    artifact = connection.execute("SELECT artifact_id,byte_size FROM uec.raw_artifacts WHERE sha256=%s",
                                  (digest,)).fetchone()
    if artifact is None or artifact[1] != metadata["source_artifact_byte_size"]:
        raise ValueError("uk_source_artifact_mismatch")
    projection_key = f"real-preview:{snapshot}:{source_key}"
    raw_fields = {"projection": "real_preview_private_geocode_target", "snapshot_sha256": snapshot}
    connection.execute("""INSERT INTO uec.source_records(source_id,source_record_key,artifact_id,raw_fields,parsed_at)
        VALUES(%s,%s,%s,%s::jsonb,%s) ON CONFLICT(source_id,source_record_key,artifact_id) DO NOTHING""",
        (source, projection_key, artifact[0], json.dumps(raw_fields, sort_keys=True), metadata["retrieved_at"]))
    record = connection.execute("""SELECT source_record_id,artifact_id,raw_fields FROM uec.source_records
        WHERE source_id=%s AND source_record_key=%s AND artifact_id=%s""",
        (source, projection_key, artifact[0])).fetchone()
    if record is None or record[1] != artifact[0] or record[2] != raw_fields:
        raise ValueError("uk_source_record_linkage_mismatch")
    return record[0]


_CANDIDATES_SQL = """
WITH latest AS MATERIALIZED (
    SELECT source_id,snapshot_sha256
      FROM real_preview.source_preview_runs WHERE source_id=%s
     ORDER BY created_at DESC,run_id DESC LIMIT 1
), accepted_source_records AS MATERIALIZED (
    SELECT DISTINCT record.source_id,record.source_record_key
      FROM uec.source_records record
      JOIN uec.geocode_results result ON result.source_record_id=record.source_record_id
     WHERE record.source_id=%s AND result.status='accepted'
       AND record.source_record_key LIKE ('real-preview:'||(SELECT snapshot_sha256 FROM latest)||':%%')
), restricted_candidates AS MATERIALIZED (
    SELECT DISTINCT state.candidate_id
      FROM real_preview.enrichment_state_events state
     WHERE state.source_id=%s AND state.snapshot_sha256=(SELECT snapshot_sha256 FROM latest)
       AND state.state_code='restricted'
), existing_locationiq_targets AS MATERIALIZED (
    SELECT DISTINCT target.candidate_id
      FROM real_preview.geocode_targets target
      JOIN uec.geocode_jobs job ON job.job_id=target.job_id
     WHERE target.source_id=%s AND target.snapshot_sha256=(SELECT snapshot_sha256 FROM latest)
       AND job.provider_id='locationiq'
), existing_other_results AS MATERIALIZED (
    SELECT DISTINCT target.candidate_id
      FROM real_preview.geocode_targets target
      JOIN uec.geocode_jobs job ON job.job_id=target.job_id
      JOIN uec.geocode_results result ON result.source_record_id=job.source_record_id
       AND result.provider_id=job.provider_id AND result.query=job.query
     WHERE target.source_id=%s AND target.snapshot_sha256=(SELECT snapshot_sha256 FROM latest)
       AND job.provider_id<>'locationiq'
), existing_locationiq_jobs AS MATERIALIZED (
    SELECT DISTINCT record.source_id,record.source_record_key
      FROM uec.geocode_jobs job
      JOIN uec.source_records record ON record.source_record_id=job.source_record_id
     WHERE record.source_id=%s AND job.provider_id='locationiq'
       AND record.source_record_key LIKE ('real-preview:'||(SELECT snapshot_sha256 FROM latest)||':%%')
)
SELECT candidate.candidate_id,candidate.snapshot_sha256,candidate.source_group_key,
       candidate.country_code,candidate.latitude,candidate.longitude,
       candidate.display_latitude,candidate.display_longitude,candidate.city,candidate.postal_code,
       location.location_evidence,manifest.source_artifact_sha256
  FROM real_preview.candidates candidate
  JOIN latest ON latest.source_id=candidate.source_id AND latest.snapshot_sha256=candidate.snapshot_sha256
  JOIN real_preview.candidate_private_location_evidence location
    ON location.candidate_id=candidate.candidate_id AND location.snapshot_sha256=candidate.snapshot_sha256
   AND location.source_id=candidate.source_id
  JOIN real_preview.source_manifests manifest
    ON manifest.source_id=candidate.source_id AND manifest.snapshot_sha256=candidate.snapshot_sha256
  LEFT JOIN accepted_source_records accepted
    ON accepted.source_id=candidate.source_id
   AND accepted.source_record_key=('real-preview:'||candidate.snapshot_sha256||':'||candidate.source_group_key)
  LEFT JOIN restricted_candidates restricted
    ON restricted.candidate_id=candidate.candidate_id
  LEFT JOIN existing_locationiq_jobs existing_job
    ON existing_job.source_id=candidate.source_id
   AND existing_job.source_record_key=('real-preview:'||candidate.snapshot_sha256||':'||candidate.source_group_key)
  LEFT JOIN existing_locationiq_targets locationiq_target
    ON locationiq_target.candidate_id=candidate.candidate_id
  LEFT JOIN existing_other_results other_result
    ON other_result.candidate_id=candidate.candidate_id
 WHERE candidate.source_id=%s AND candidate.country_code='GB'
   AND candidate.latitude IS NULL AND candidate.longitude IS NULL
   AND candidate.display_latitude IS NULL AND candidate.display_longitude IS NULL
   AND location.location_evidence->>'country_code'='GB'
   AND jsonb_typeof(location.location_evidence->'address_lines')='array'
   AND jsonb_typeof(location.location_evidence->'city')='string'
   AND jsonb_typeof(location.location_evidence->'postal_code')='string'
   AND accepted.source_record_key IS NULL
   AND restricted.candidate_id IS NULL
   AND locationiq_target.candidate_id IS NULL
   AND existing_job.source_record_key IS NULL
 ORDER BY (other_result.candidate_id IS NULL) DESC,candidate.candidate_id
 LIMIT %s FOR UPDATE OF candidate SKIP LOCKED
"""


def _latest_run_sql() -> str:
    return """
WITH latest AS (
    SELECT * FROM real_preview.source_preview_runs WHERE source_id=%s
     ORDER BY created_at DESC,run_id DESC LIMIT 1
)
SELECT run.run_id,run.snapshot_sha256,run.source_artifact_sha256,run.source_url,run.retrieved_at,
       run.normalized_sha256,run.imported_observation_count,run.adapter_version,run.schema_version,
       run.runtime_details,manifest.source_artifact_sha256,manifest.normalized_sha256,manifest.source_url,
       manifest.retrieved_at,manifest.normalized_rows,manifest.code_version,manifest.config_version
  FROM latest run LEFT JOIN real_preview.source_manifests manifest
    ON manifest.source_id=run.source_id AND manifest.snapshot_sha256=run.snapshot_sha256
"""


def activate(database_url: str, *, source: str, limit: int = 100):
    if source not in PROFILE_IDS or not 1 <= limit <= 5000:
        raise ValueError("UK source or bounded LocationIQ limit invalid")
    profile_id = PROFILE_IDS[source]
    profile = profile_by_id(profile_id)
    if (profile is None or profile.get("provider_id") != "locationiq"
            or profile.get("source_id") != source or profile.get("country_code") != "GB"):
        raise ValueError("UK LocationIQ profile is not enabled")
    with psycopg.connect(database_url) as connection, connection.transaction():
        if connection.execute("SELECT current_database()").fetchone()[0] != DATABASE:
            raise ValueError("database_identity_invalid")
        connection.execute("SET LOCAL statement_timeout = '30s'")
        row = connection.execute(_latest_run_sql(), (source,)).fetchone()
        if row is None:
            raise ValueError("latest_uk_source_run_missing")
        (run_id,snapshot,run_hash,run_url,run_retrieved,run_normalized,run_count,adapter,schema,
         details,manifest_hash,manifest_normalized,manifest_url,manifest_retrieved,manifest_count,
         manifest_adapter,manifest_schema) = row
        details = details if isinstance(details, dict) else {}
        acquisition = details.get("source_artifacts")
        metadata = _validate_provenance(source,
            {"run_id":run_id,"snapshot_sha256":snapshot,"source_artifact_sha256":run_hash,
             "source_url":run_url,"retrieved_at":run_retrieved,"normalized_sha256":run_normalized,
             "imported_observation_count":run_count,"adapter_version":adapter,"schema_version":schema,
             "processing_mode":details.get("processing_mode"),
             "acquisition_classification":details.get("acquisition_classification"),
             "fresh_live_run":details.get("fresh_live_run")},
            {"source_artifact_sha256":manifest_hash,"normalized_sha256":manifest_normalized,
             "source_url":manifest_url,"retrieved_at":manifest_retrieved,"normalized_rows":manifest_count,
             "code_version":manifest_adapter,"config_version":manifest_schema}, acquisition)
        if not isinstance(snapshot, str) or not _SHA256.fullmatch(snapshot):
            raise ValueError("latest_uk_snapshot_invalid")
        rows = connection.execute(_CANDIDATES_SQL,
                                  (source, source, source, source, source, source, source, 5000)).fetchall()
        jobs, skipped = [], 0
        for item in rows:
            if len(jobs) >= limit:
                break
            (candidate_id,candidate_snapshot,source_key,country,lat,lon,display_lat,display_lon,
             candidate_city,candidate_postal,location,artifact_hash) = item
            city = location.get("city") if isinstance(location, dict) else None
            postcode = location.get("postal_code") if isinstance(location, dict) else None
            address_lines = location.get("address_lines") if isinstance(location, dict) else None
            query = canonical_uk_query(address_lines, city, postcode)
            if (query is None or not isinstance(city, str) or not isinstance(postcode, str)
                    or candidate_snapshot != snapshot or country != "GB"
                    or artifact_hash != metadata["source_artifact_sha256"]
                    or any(value is not None for value in (lat,lon,display_lat,display_lon))
                    or not isinstance(candidate_city, str) or candidate_city.strip() != city.strip()
                    or not isinstance(candidate_postal, str)
                    or re.sub(r"\s+", "", candidate_postal).upper() != re.sub(r"\s+", "", postcode).upper()
                    ):
                skipped += 1
                continue
            source_record = _ensure_linkage(connection, source, snapshot, str(source_key), metadata)
            if connection.execute("SELECT 1 FROM uec.public_access_restricted WHERE source_record_id=%s LIMIT 1",
                                  (source_record,)).fetchone():
                skipped += 1
                continue
            job = connection.execute("""INSERT INTO uec.geocode_jobs(source_record_id,provider_id,query)
                VALUES(%s,'locationiq',%s) ON CONFLICT(source_record_id,provider_id,query) DO NOTHING
                RETURNING job_id""", (source_record, query)).fetchone()
            if job is None:
                skipped += 1
                continue
            job_id = job[0]
            target = connection.execute("""INSERT INTO real_preview.geocode_targets
                (job_id,candidate_id,snapshot_sha256,source_id,source_record_key)
                VALUES(%s,%s,%s,%s,%s) ON CONFLICT(job_id,candidate_id) DO NOTHING
                RETURNING candidate_id""", (job_id,candidate_id,snapshot,source,str(source_key))).fetchone()
            if target is None:
                raise ValueError("UK LocationIQ candidate target already exists")
            connection.execute("""INSERT INTO uec.geocode_job_events
                (job_id,event_type,attempt_number,retryable,details)
                VALUES(%s,'queued',1,false,%s::jsonb)""",
                (job_id,json.dumps({"processing_mode":"private_locationiq_source_profile",
                    "profile_id":profile_id,"query_components":["source_road_house","source_locality",
                    "source_postcode","country"],"source_id":source,"source_snapshot_sha256":snapshot})))
            connection.execute("""INSERT INTO real_preview.enrichment_state_events
                (candidate_id,snapshot_sha256,source_id,source_record_key,state_code,reason_code)
                VALUES(%s,%s,%s,%s,'queued','locationiq_uk_address')""",
                (candidate_id,snapshot,source,str(source_key)))
            jobs.append(job_id)
        return {"source":source,"profile_id":profile_id,"targets_staged":len(jobs),
                "ineligible_or_existing_skipped":skipped,"provider_calls":0}, tuple(jobs)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.environ.get("UEC_DATABASE_URL"))
    parser.add_argument("--source", required=True, choices=tuple(PROFILE_IDS))
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    if not args.database_url:
        print(json.dumps({"status":"blocked","reason":"database_url_missing"}))
        return 2
    try:
        summary, _jobs = activate(args.database_url, source=args.source, limit=args.limit)
        print(json.dumps(summary))
        return 0
    except Exception as error:
        print(json.dumps({"status":"failed","error_type":type(error).__name__,
                          "sqlstate":getattr(error,"sqlstate",None)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
