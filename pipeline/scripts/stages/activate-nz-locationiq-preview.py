#!/usr/bin/env python3
"""Queue bounded private LocationIQ jobs for single-location NZ RMP records."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
from typing import Any
import uuid

import psycopg

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from pipeline.geocoding.locationiq import LocationIqAdapter
from pipeline.geocoding.private_profiles import profile_by_id

SOURCE_ID = "nz.locations"
PROFILE_ID = "locationiq-nz-mpi-rmp"
DATABASE = "uec_launch_sources_test_20261025"
SOURCE_URL = ("https://mpi.my.site.com/publicregister/s/RiskMeasureSearch"
              "?riskMeasureType=Risk%20Management%20Programme")
SOURCE_NAME = "New Zealand Ministry for Primary Industries — Risk Management Programme Register"
_POSTCODE = re.compile(r"^[0-9]{4}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
NZ_RECHECK_RULESET = "nz-address-node-v1"


def _as_utc(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        stamp = value
    elif isinstance(value, str):
        try:
            stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if stamp.utcoffset() is None:
        return None
    return stamp.astimezone(timezone.utc)


def _validate_source_binding(run: dict[str, Any], manifest: dict[str, Any],
                             acquisition: Any) -> dict[str, Any]:
    if not isinstance(acquisition, dict):
        raise ValueError("verified_source_acquisition_missing")
    run_hash, manifest_hash = run.get("source_artifact_sha256"), manifest.get("source_artifact_sha256")
    normalized_hash = run.get("normalized_sha256")
    manifest_normalized_hash = manifest.get("normalized_sha256")
    run_retrieved = _as_utc(run.get("retrieved_at"))
    manifest_retrieved = _as_utc(manifest.get("retrieved_at"))
    acquisition_retrieved = _as_utc(acquisition.get("retrieved_at_utc"))
    run_count, manifest_count = run.get("imported_observation_count"), manifest.get("normalized_rows")
    adapter, schema = run.get("adapter_version"), run.get("schema_version")
    if (not isinstance(run_hash, str) or not _SHA256.fullmatch(run_hash)
            or manifest_hash != run_hash or acquisition.get("source_artifact_sha256") != run_hash
            or not isinstance(normalized_hash, str) or not _SHA256.fullmatch(normalized_hash)
            or manifest_normalized_hash != normalized_hash
            or run_count != manifest_count or type(run_count) is not int or run_count < 1
            or not isinstance(adapter, str) or not adapter or manifest.get("code_version") != adapter
            or not isinstance(schema, str) or not schema or manifest.get("config_version") != schema
            or run.get("source_url") != SOURCE_URL or manifest.get("source_url") != SOURCE_URL
            or acquisition.get("source_url") != SOURCE_URL
            or run_retrieved is None or manifest_retrieved is None or acquisition_retrieved is None
            or run_retrieved != manifest_retrieved or run_retrieved != acquisition_retrieved
            or run_retrieved > datetime.now(timezone.utc)
            or acquisition.get("source_id") != SOURCE_ID
            or acquisition.get("adapter_version") != adapter
            or acquisition.get("schema_version") != schema
            or acquisition.get("source_processing_mode") != "local-artifact"
            or not isinstance(acquisition.get("runner_run_id"), str)
            or not acquisition.get("runner_run_id")
            or run.get("processing_mode") != "assisted_local_artifact_processing"
            or run.get("acquisition_classification") != "assisted"
            or type(acquisition.get("source_artifact_byte_size")) is not int
            or acquisition["source_artifact_byte_size"] < 1):
        raise ValueError("source_manifest_acquisition_binding_mismatch")
    return {"source_artifact_sha256": run_hash,
            "source_artifact_byte_size": acquisition["source_artifact_byte_size"],
            "source_url": SOURCE_URL, "retrieved_at": run_retrieved,
            "normalized_sha256": normalized_hash, "normalized_rows": run_count,
            "adapter_version": adapter, "schema_version": schema}


def _projection_source_record_key(snapshot: Any, source_group_key: Any) -> str:
    if (not isinstance(snapshot, str) or not _SHA256.fullmatch(snapshot)
            or not isinstance(source_group_key, str) or not source_group_key.strip()):
        raise ValueError("source_record_projection_identity_invalid")
    return f"real-preview:{snapshot}:{source_group_key}"


def _ensure_source_linkage(connection: Any, *, snapshot: str, source_group_key: str,
                           metadata: dict[str, Any]) -> Any:
    connection.execute("""INSERT INTO uec.sources(source_id,country_code,name,official_url,access_method)
        VALUES(%s,'NZ',%s,%s,'private_preview_address_enrichment') ON CONFLICT(source_id) DO NOTHING""",
        (SOURCE_ID, SOURCE_NAME, SOURCE_URL))
    source = connection.execute("SELECT country_code,official_url,access_method FROM uec.sources WHERE source_id=%s",
                                (SOURCE_ID,)).fetchone()
    if source != ("NZ", SOURCE_URL, "private_preview_address_enrichment"):
        raise ValueError("standard_source_identity_mismatch")
    connection.execute("""INSERT INTO uec.raw_artifacts(storage_key,sha256,byte_size,media_type,retrieved_at)
        VALUES(%s,%s,%s,'text/csv',%s) ON CONFLICT(sha256) DO NOTHING""",
        (f"private-preview-source-artifact:{SOURCE_ID}:{metadata['source_artifact_sha256']}",
         metadata["source_artifact_sha256"], metadata["source_artifact_byte_size"], metadata["retrieved_at"]))
    artifact = connection.execute("SELECT artifact_id,byte_size FROM uec.raw_artifacts WHERE sha256=%s",
                                  (metadata["source_artifact_sha256"],)).fetchone()
    if artifact is None or artifact[1] != metadata["source_artifact_byte_size"]:
        raise ValueError("standard_source_artifact_missing_or_mismatched")
    projection_key = _projection_source_record_key(snapshot, source_group_key)
    raw_fields = {"projection": "real_preview_private_geocode_target", "snapshot_sha256": snapshot}
    connection.execute("""INSERT INTO uec.source_records(source_id,source_record_key,artifact_id,raw_fields,parsed_at)
        VALUES(%s,%s,%s,%s::jsonb,%s) ON CONFLICT(source_id,source_record_key,artifact_id) DO NOTHING""",
        (SOURCE_ID, projection_key, artifact[0], json.dumps(raw_fields, sort_keys=True), metadata["retrieved_at"]))
    record = connection.execute("""SELECT source_record_id,artifact_id,raw_fields FROM uec.source_records
        WHERE source_id=%s AND source_record_key=%s AND artifact_id=%s""",
        (SOURCE_ID, projection_key, artifact[0])).fetchone()
    if record is None or record[1] != artifact[0] or record[2] != raw_fields:
        raise ValueError("standard_source_record_linkage_mismatch")
    return record[0]


def _query_from_location(location: Any) -> str | None:
    """Build only a street/town/NZ query from retained, single-location evidence."""
    if not isinstance(location, dict):
        return None
    if (type(location.get("location_count")) is not int or location["location_count"] != 1
            or location.get("country_code") != "NZ"
            or str(location.get("number_of_locations", "")).strip() != "1"
            or location.get("coordinates") is not None
            or any(location.get(key) is not None for key in ("latitude", "longitude"))):
        return None
    street, town = location.get("address"), location.get("city")
    if not isinstance(street, str) or not isinstance(town, str):
        return None
    street = " ".join(street.split())
    town = " ".join(town.split())
    if (not street or not town or len(street) > 500 or len(town) > 200
            or "," in street or "," in town):
        return None
    postcode = location.get("postal_code", location.get("postcode"))
    if postcode is not None:
        if not isinstance(postcode, str):
            return None
        postcode = postcode.strip()
        if not _POSTCODE.fullmatch(postcode):
            return None
    query = ", ".join(part for part in (street, postcode, town, "New Zealand") if part)
    if LocationIqAdapter._parse_nz_query(query) is None:
        return None
    return query


def _replay_retained_response(query: str, retained_response: Any):
    """Re-evaluate saved provider candidates without a key or network access."""
    if not isinstance(retained_response, dict) or not isinstance(retained_response.get("results"), list):
        raise ValueError("retained_provider_response_invalid")

    class MemoryResponse:
        def __init__(self, payload: bytes):
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _limit=-1):
            return self.payload

    payload = json.dumps(retained_response["results"], ensure_ascii=False).encode("utf-8")
    adapter = LocationIqAdapter(api_key="placeholder-offline-recheck",
                                opener=lambda *_args, **_kwargs: MemoryResponse(payload),
                                country_code="nz", private_source_profile=True)
    return adapter.geocode(query)


def _retained_recheck_identity(parent_id: Any, outcome: Any) -> tuple[uuid.UUID, dict[str, Any]]:
    result_id = uuid.uuid5(uuid.NAMESPACE_URL, f"urn:uec:nz-address-node-v1:{parent_id}")
    response = {**outcome.response, "parent_geocode_result_id": str(parent_id),
                "recheck_ruleset": NZ_RECHECK_RULESET, "offline_recheck": True}
    return result_id, response


_RETAINED_RECHECK_SQL = """
WITH latest AS (
    SELECT DISTINCT ON (source_id) source_id,snapshot_sha256
      FROM real_preview.source_preview_runs
     WHERE source_id='nz.locations'
     ORDER BY source_id,created_at DESC,run_id DESC
), eligible AS (
    SELECT target.job_id,target.candidate_id,target.snapshot_sha256,target.source_id,
           target.source_record_key,job.source_record_id,job.query,result.geocode_result_id,
           result.response,result.attempt_number,result.queried_at,
           location.location_evidence
      FROM real_preview.geocode_targets target
      JOIN latest USING (source_id,snapshot_sha256)
      JOIN uec.geocode_jobs job ON job.job_id=target.job_id AND job.provider_id='locationiq'
      JOIN LATERAL (
          SELECT result.* FROM uec.geocode_results result
           WHERE result.source_record_id=job.source_record_id
             AND result.provider_id='locationiq' AND result.query=job.query
           ORDER BY result.queried_at DESC,result.geocode_result_id DESC LIMIT 1
      ) result ON result.status='review_required'
      JOIN real_preview.candidate_private_location_evidence location
        ON location.candidate_id=target.candidate_id
       AND location.snapshot_sha256=target.snapshot_sha256
       AND location.source_id=target.source_id
      JOIN real_preview.candidates candidate
        ON candidate.candidate_id=target.candidate_id
       AND candidate.snapshot_sha256=target.snapshot_sha256
       AND candidate.source_id=target.source_id
      JOIN LATERAL (
          SELECT event.details FROM uec.geocode_job_events event
           WHERE event.job_id=job.job_id AND event.event_type='queued'
           ORDER BY event.occurred_at DESC,event.event_id DESC LIMIT 1
      ) queued ON queued.details->>'profile_id'='locationiq-nz-mpi-rmp'
     WHERE target.source_id='nz.locations' AND target.snapshot_sha256=(SELECT snapshot_sha256 FROM latest)
       AND candidate.country_code='NZ' AND candidate.latitude IS NULL AND candidate.longitude IS NULL
       AND candidate.display_latitude IS NULL AND candidate.display_longitude IS NULL
       AND location.location_evidence->>'country_code'='NZ'
       AND location.location_evidence->'location_count'='1'::jsonb
       AND BTRIM(COALESCE(location.location_evidence->>'number_of_locations',''))='1'
       AND NULLIF(BTRIM(location.location_evidence->>'address'),'') IS NOT NULL
       AND NULLIF(BTRIM(location.location_evidence->>'city'),'') IS NOT NULL
       AND COALESCE(location.location_evidence->'coordinates','null'::jsonb)='null'::jsonb
       AND NOT (location.location_evidence ? 'latitude')
       AND NOT (location.location_evidence ? 'longitude')
       AND NOT EXISTS (SELECT 1 FROM uec.public_access_restricted restricted
                        WHERE restricted.source_record_id=job.source_record_id)
       AND NOT EXISTS (SELECT 1 FROM real_preview.enrichment_state_events state
                        WHERE state.candidate_id=target.candidate_id AND state.state_code='restricted')
       AND NOT EXISTS (SELECT 1 FROM uec.geocode_results derived
                        WHERE derived.source_record_id=job.source_record_id
                          AND derived.response->>'recheck_ruleset'=%s)
     ORDER BY candidate.candidate_id
     LIMIT %s
     FOR UPDATE OF candidate SKIP LOCKED
)
SELECT * FROM eligible
"""


def recheck_retained(database_url: str, *, limit: int = 24):
    if not 1 <= limit <= 5000:
        raise ValueError("NZ retained recheck batch must contain 1 to 5000 records")
    profile = profile_by_id(PROFILE_ID)
    if (profile is None or profile.get("provider_id") != "locationiq"
            or profile.get("source_id") != SOURCE_ID or profile.get("country_code") != "NZ"):
        raise ValueError("NZ LocationIQ profile is not enabled")
    with psycopg.connect(database_url) as connection, connection.transaction():
        if connection.execute("SELECT current_database()").fetchone()[0] != DATABASE:
            raise ValueError("database_identity_invalid")
        rows = connection.execute(_RETAINED_RECHECK_SQL, (NZ_RECHECK_RULESET, limit)).fetchall()
        created = 0
        for row in rows:
            (job_id, candidate_id, snapshot, source_id, source_key, source_record_id,
             query, parent_id, retained_response, attempt, queried_at, location) = row
            if source_id != SOURCE_ID or _query_from_location(location) != query:
                continue
            outcome = _replay_retained_response(query, retained_response)
            if outcome.status != "accepted":
                continue
            result_id, response = _retained_recheck_identity(parent_id, outcome)
            inserted = connection.execute("""INSERT INTO uec.geocode_results
                (geocode_result_id,source_record_id,provider_id,query,provider_address_id,result,
                 precision,match_method,status,attempt_number,retryable,response,queried_at)
                VALUES(%s,%s,'locationiq',%s,%s,
                    CASE WHEN %s::double precision IS NULL OR %s::double precision IS NULL THEN NULL
                         ELSE ST_SetSRID(ST_MakePoint(%s::double precision,%s::double precision),4326)::geography END,
                    %s,%s,%s,%s,%s,%s::jsonb,%s)
                ON CONFLICT(geocode_result_id) DO NOTHING RETURNING geocode_result_id""",
                (result_id, source_record_id, query, outcome.provider_address_id,
                 outcome.longitude, outcome.latitude, outcome.longitude, outcome.latitude,
                 outcome.precision, outcome.match_method, outcome.status, attempt,
                 outcome.retryable, json.dumps(response, ensure_ascii=False), queried_at)).fetchone()
            if inserted is None:
                continue
            connection.execute("""INSERT INTO uec.geocode_job_events
                (job_id,event_type,attempt_number,retryable,details,occurred_at)
                VALUES(%s,'accepted',%s,false,%s::jsonb,now())""",
                (job_id, attempt, json.dumps({"offline_recheck": True,
                    "parent_geocode_result_id": str(parent_id), "derived_geocode_result_id": str(result_id),
                    "recheck_ruleset": NZ_RECHECK_RULESET})))
            created += 1
        return {"source": SOURCE_ID, "recheck_ruleset": NZ_RECHECK_RULESET,
                "results_derived": created, "provider_calls": 0}, ()


_LATEST_RUN_SQL = """
WITH latest AS (
    SELECT *
      FROM real_preview.source_preview_runs
     WHERE source_id=%s
     ORDER BY created_at DESC,run_id DESC
     LIMIT 1
)
SELECT run.snapshot_sha256,run.source_artifact_sha256,run.source_url,run.retrieved_at,
       run.normalized_sha256,run.imported_observation_count,run.adapter_version,run.schema_version,
       run.runtime_details,
       manifest.source_artifact_sha256,manifest.normalized_sha256,manifest.source_url,
       manifest.retrieved_at,manifest.normalized_rows,manifest.code_version,manifest.config_version
  FROM latest run
  LEFT JOIN real_preview.source_manifests manifest
    ON manifest.source_id=run.source_id AND manifest.snapshot_sha256=run.snapshot_sha256
"""

_LATEST_CANDIDATES_SQL = """
SELECT candidate.candidate_id,candidate.snapshot_sha256,candidate.source_group_key,
       candidate.country_code,candidate.latitude,candidate.longitude,
       candidate.display_latitude,candidate.display_longitude,candidate.facility_address,candidate.city,
       location.location_evidence,
       artifact.artifact_id,artifact.byte_size,source_record.source_record_id,source_record.raw_fields
  FROM real_preview.candidates candidate
  JOIN real_preview.candidate_private_location_evidence location
    ON location.candidate_id=candidate.candidate_id
   AND location.snapshot_sha256=candidate.snapshot_sha256
   AND location.source_id=candidate.source_id
  LEFT JOIN uec.raw_artifacts artifact ON artifact.sha256=%s
  LEFT JOIN uec.source_records source_record
    ON source_record.source_id=candidate.source_id
   AND source_record.source_record_key=('real-preview:'||candidate.snapshot_sha256||':'||candidate.source_group_key)
   AND source_record.artifact_id=artifact.artifact_id
 WHERE candidate.source_id=%s
   AND candidate.snapshot_sha256=%s
   AND candidate.country_code='NZ'
   AND candidate.location_class<>'numeric_source_coordinate'
   AND candidate.latitude IS NULL AND candidate.longitude IS NULL
   AND candidate.display_latitude IS NULL AND candidate.display_longitude IS NULL
   AND location.location_evidence->>'country_code'='NZ'
   AND location.location_evidence->'location_count'='1'::jsonb
   AND BTRIM(COALESCE(location.location_evidence->>'number_of_locations',''))='1'
   AND NULLIF(BTRIM(location.location_evidence->>'address'),'') IS NOT NULL
   AND NULLIF(BTRIM(location.location_evidence->>'city'),'') IS NOT NULL
   AND COALESCE(location.location_evidence->'coordinates','null'::jsonb)='null'::jsonb
   AND NOT (location.location_evidence ? 'latitude')
   AND NOT (location.location_evidence ? 'longitude')
   AND NOT EXISTS (
       SELECT 1 FROM uec.public_access_restricted restricted
        WHERE restricted.source_record_id=source_record.source_record_id)
   AND NOT EXISTS (
       SELECT 1 FROM real_preview.enrichment_state_events state
        WHERE state.candidate_id=candidate.candidate_id AND state.state_code='restricted')
   AND NOT EXISTS (
       SELECT 1 FROM real_preview.geocode_targets target
       JOIN uec.geocode_jobs job ON job.job_id=target.job_id
        WHERE target.candidate_id=candidate.candidate_id
          AND target.snapshot_sha256=candidate.snapshot_sha256
          AND job.provider_id='locationiq')
   AND NOT EXISTS (
       SELECT 1 FROM uec.geocode_jobs job
        WHERE job.source_record_id=source_record.source_record_id
          AND job.provider_id='locationiq')
   AND NOT EXISTS (
       SELECT 1 FROM uec.geocode_results result
        WHERE result.source_record_id=source_record.source_record_id
          AND result.status='accepted')
 ORDER BY candidate.candidate_id
 LIMIT %s
 FOR UPDATE OF candidate SKIP LOCKED
"""


def activate(database_url: str, *, limit: int = 100):
    if not 1 <= limit <= 5000:
        raise ValueError("NZ LocationIQ batch must contain 1 to 5000 records")
    profile = profile_by_id(PROFILE_ID)
    if (profile is None or profile.get("provider_id") != "locationiq"
            or profile.get("source_id") != SOURCE_ID or profile.get("country_code") != "NZ"):
        raise ValueError("NZ LocationIQ profile is not enabled")
    with psycopg.connect(database_url) as connection, connection.transaction():
        if connection.execute("SELECT current_database()").fetchone()[0] != DATABASE:
            raise ValueError("database_identity_invalid")
        latest_row = connection.execute(_LATEST_RUN_SQL, (SOURCE_ID,)).fetchone()
        if latest_row is None:
            raise ValueError("latest_source_preview_run_missing")
        (snapshot, run_hash, run_url, run_retrieved, run_normalized, run_count,
         adapter_version, schema_version, runtime_details, manifest_hash,
         manifest_normalized, manifest_url, manifest_retrieved, manifest_count,
         manifest_adapter, manifest_schema) = latest_row
        runtime_details = runtime_details if isinstance(runtime_details, dict) else {}
        metadata = _validate_source_binding(
            {"snapshot_sha256": snapshot, "source_artifact_sha256": run_hash,
             "source_url": run_url, "retrieved_at": run_retrieved,
             "normalized_sha256": run_normalized,
             "imported_observation_count": run_count,
             "adapter_version": adapter_version, "schema_version": schema_version,
             "processing_mode": runtime_details.get("processing_mode"),
             "acquisition_classification": runtime_details.get("acquisition_classification")},
            {"source_artifact_sha256": manifest_hash,
             "normalized_sha256": manifest_normalized, "source_url": manifest_url,
             "retrieved_at": manifest_retrieved, "normalized_rows": manifest_count,
             "code_version": manifest_adapter, "config_version": manifest_schema},
            runtime_details.get("source_artifacts"),
        )
        if not isinstance(snapshot, str) or not _SHA256.fullmatch(snapshot):
            raise ValueError("latest_source_snapshot_invalid")
        metadata["snapshot_sha256"] = snapshot
        rows = connection.execute(_LATEST_CANDIDATES_SQL,
                                  (metadata["source_artifact_sha256"], SOURCE_ID, snapshot, 5000)).fetchall()
        job_ids = []
        skipped = 0
        for row in rows:
            if len(job_ids) >= limit:
                break
            (candidate_id, candidate_snapshot, source_key, country, latitude, longitude,
             display_latitude, display_longitude, candidate_address, candidate_city,
             location, artifact_id, artifact_size, source_record_id, raw_fields) = row
            query = _query_from_location(location)
            if (candidate_snapshot != snapshot or query is None or country != "NZ" or any(value is not None for value in
                    (latitude, longitude, display_latitude, display_longitude))
                    or not isinstance(candidate_address, str) or not isinstance(candidate_city, str)
                    or " ".join(candidate_address.split()) != " ".join(location["address"].split())
                    or " ".join(candidate_city.split()) != " ".join(location["city"].split())):
                skipped += 1
                continue
            source_record_id = _ensure_source_linkage(
                connection, snapshot=snapshot, source_group_key=str(source_key), metadata=metadata)
            if connection.execute("""SELECT 1 FROM uec.public_access_restricted
                WHERE source_record_id=%s LIMIT 1""", (source_record_id,)).fetchone():
                skipped += 1
                continue
            job = connection.execute("""INSERT INTO uec.geocode_jobs(source_record_id,provider_id,query)
                VALUES(%s,'locationiq',%s)
                ON CONFLICT(source_record_id,provider_id,query) DO NOTHING RETURNING job_id""",
                (source_record_id, query)).fetchone()
            if job is None:
                skipped += 1
                continue
            job_id = job[0]
            target = connection.execute("""INSERT INTO real_preview.geocode_targets
                (job_id,candidate_id,snapshot_sha256,source_id,source_record_key)
                VALUES(%s,%s,%s,%s,%s) ON CONFLICT(job_id,candidate_id) DO NOTHING
                RETURNING candidate_id""",
                (job_id, candidate_id, snapshot, SOURCE_ID, source_key)).fetchone()
            if target is None:
                raise ValueError("NZ geocode target already exists")
            details = {
                "processing_mode": "private_locationiq_source_profile",
                "profile_id": PROFILE_ID,
                "source_artifact_sha256": metadata["source_artifact_sha256"],
                "source_normalized_sha256": metadata["normalized_sha256"],
                "source_normalized_rows": metadata["normalized_rows"],
                "source_adapter_version": metadata["adapter_version"],
                "source_schema_version": metadata["schema_version"],
                "source_retrieved_at": metadata["retrieved_at"].isoformat(),
                "query_components": ["physical_street", "town", "country"] +
                    (["source_postcode"] if location.get("postal_code", location.get("postcode")) else []),
                "location_count": 1,
            }
            connection.execute("""INSERT INTO uec.geocode_job_events
                (job_id,event_type,attempt_number,retryable,details)
                VALUES(%s,'queued',1,false,%s::jsonb)""", (job_id, json.dumps(details)))
            connection.execute("""INSERT INTO real_preview.enrichment_state_events
                (candidate_id,snapshot_sha256,source_id,source_record_key,state_code,reason_code)
                VALUES(%s,%s,%s,%s,'queued','locationiq_nz_mpi_rmp')""",
                (candidate_id, snapshot, SOURCE_ID, source_key))
            job_ids.append(job_id)
        return {"provider": "locationiq", "source": SOURCE_ID, "profile_id": PROFILE_ID,
                "jobs_staged": len(job_ids), "ineligible_or_existing_skipped": skipped,
                "provider_calls": 0}, tuple(job_ids)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.environ.get("UEC_DATABASE_URL"))
    parser.add_argument("--limit", type=int, default=24)
    parser.add_argument("--recheck-retained", action="store_true",
                        help="offline recheck of retained NZ LocationIQ responses; makes no provider calls")
    parser.add_argument("--run-worker", action="store_true")
    parser.add_argument("--provider-account", choices=("primary", "secondary"), default="primary")
    args = parser.parse_args()
    if args.recheck_retained and args.run_worker:
        parser.error("--recheck-retained cannot be combined with --run-worker")
    key_env = "LOCATIONIQ_SECONDARY_API_KEY" if args.provider_account == "secondary" else "LOCATIONIQ_API_KEY"
    if not args.database_url:
        print(json.dumps({"status": "blocked", "reason": "database_url_missing"}))
        return 2
    if args.run_worker and not os.environ.get(key_env, "").strip():
        print(json.dumps({"status": "blocked", "reason": "locationiq_key_missing"}))
        return 2
    try:
        if args.recheck_retained:
            summary, jobs = recheck_retained(args.database_url, limit=args.limit)
            print(json.dumps(summary), flush=True)
            return 0
        summary, jobs = activate(args.database_url, limit=args.limit)
        print(json.dumps(summary), flush=True)
        if args.run_worker and jobs:
            worker_spec = importlib.util.spec_from_file_location(
                "locationiq_worker", Path(__file__).with_name("geocode-worker.py"))
            if worker_spec is None or worker_spec.loader is None:
                raise RuntimeError("geocode worker unavailable")
            worker = importlib.util.module_from_spec(worker_spec)
            worker_spec.loader.exec_module(worker)
            processed = worker.run(args.database_url, "locationiq", len(jobs), 0, 1,
                                   daily_budget=5000, max_attempts=2,
                                   provider_interval=1.05,
                                   private_source_profile_id=PROFILE_ID, job_ids=jobs,
                                   provider_account=args.provider_account)
            print(json.dumps({"provider": "locationiq", "status": "complete", "processed": processed}))
        return 0
    except Exception as error:
        print(json.dumps({"status": "failed", "error_type": type(error).__name__,
                          "sqlstate": getattr(error, "sqlstate", None)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
