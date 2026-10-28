"""Offline, conservative postcode-reference replay for retained UK results."""
from __future__ import annotations

import argparse
import copy
import json
import math
import os
from pathlib import Path
import re
import uuid

import psycopg

from pipeline.scripts.release_baseline import load_contract, validate_database_url, verify_connection

ROOT = Path(__file__).resolve().parents[2]
DATABASE = "uec_launch_sources_test_20261025"
RULESET = "uk-postcode-reference-v1"
MATCH_METHOD = "locationiq_postcode_reference_v1"
_NAMESPACE = uuid.UUID("c7ce64dd-65b4-5bf3-bf1f-48e05fd17982")
_POSTCODE = re.compile(r"^(?:GIR0AA|[A-Z]{1,2}[0-9][A-Z0-9]?[0-9][A-Z]{2})$")


def normalize_postcode(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    compact = re.sub(r"\s+", "", value).upper()
    return compact if _POSTCODE.fullmatch(compact) else None


def select_postcode_reference(response: object, source_postcode: object):
    """Return the unique matching point's index and coordinates, or None.

    Identical duplicate candidates are safe; two distinct matching points are
    ambiguous. No rank/importance/confidence field is consulted.
    """
    postcode = normalize_postcode(source_postcode)
    if postcode is None or not isinstance(response, dict):
        return None
    results = response.get("results")
    if not isinstance(results, list) or not 1 <= len(results) <= 2:
        return None
    found: list[tuple[int, float, float]] = []
    for index, item in enumerate(results):
        if not isinstance(item, dict) or item.get("class") != "place" or item.get("type") != "postcode":
            continue
        address = item.get("address")
        if (not isinstance(address, dict)
                or str(address.get("country_code", "")).lower() != "gb"
                or normalize_postcode(address.get("postcode")) != postcode):
            continue
        if not isinstance(item.get("lat"), str) or not isinstance(item.get("lon"), str):
            continue
        try:
            lat, lon = float(item["lat"]), float(item["lon"])
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        if not math.isfinite(lat) or not math.isfinite(lon):
            continue
        if not (49.8 <= lat <= 60.9 and -8.7 <= lon <= 2.1):
            continue
        found.append((index, lat, lon))
    distinct = {(lat, lon) for _, lat, lon in found}
    if len(distinct) != 1:
        return None
    return next(row for row in found if (row[1], row[2]) in distinct)


def derived_result_id(parent_id: uuid.UUID | str) -> uuid.UUID:
    return uuid.uuid5(_NAMESPACE, f"{parent_id}:{RULESET}")


def _append_result(connection, *, parent, result_id, response, latitude, longitude):
    with connection.transaction():
        inserted = connection.execute("""
            INSERT INTO uec.geocode_results
                (geocode_result_id,source_record_id,provider_id,query,provider_address_id,
                 result,precision,match_method,status,attempt_number,retryable,response,queried_at)
            VALUES(%s,%s,'locationiq',%s,NULL,
                   ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography,
                   'locationiq_postcode_point',%s,'accepted',%s,false,%s::jsonb,%s)
            ON CONFLICT (geocode_result_id) DO NOTHING
            RETURNING geocode_result_id
        """, (result_id, parent["source_record_id"], parent["query"], longitude, latitude,
              MATCH_METHOD, parent["attempt_number"], json.dumps(response, ensure_ascii=False),
              parent["queried_at"])).fetchone()
        if inserted is None:
            return False
        # The migration trigger independently replays provenance and candidate
        # checks, then appends display evidence for every matching target.
        visible = connection.execute("""
            SELECT EXISTS (
                SELECT 1 FROM real_preview.geocode_targets target
                JOIN real_preview.geocode_display_evidence evidence
                  ON evidence.candidate_id=target.candidate_id
                 AND evidence.geocode_result_id=%s
            )
        """, (result_id,)).fetchone()[0]
        if not visible:
            raise ValueError("postcode_reference_has_no_audited_display")
        return True


def reconcile(database_url: str, *, limit: int) -> dict:
    """Derive approximate postcode pins only from saved first-pass responses."""
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 5000:
        raise ValueError("finite_limit_required")
    validate_database_url(database_url)
    contract = load_contract(ROOT / "pipeline/contracts/development-baseline.json")
    counts = {"examined": 0, "appended": 0, "already_present": 0,
              "rejected": 0, "database_rejected": 0}
    with psycopg.connect(database_url) as connection, connection.transaction():
        if connection.execute("SELECT current_database()").fetchone()[0] != DATABASE:
            raise ValueError("wrong_disposable_database")
        if verify_connection(connection, contract)["status"] != "verified":
            raise ValueError("baseline_not_verified")
        rows = connection.execute("""
            SELECT DISTINCT ON (job.job_id)
                   job.job_id,job.source_record_id,job.query,parent.geocode_result_id,
                   parent.response,parent.attempt_number,parent.queried_at
              FROM uec.geocode_jobs job
              JOIN uec.geocode_results parent
                ON parent.source_record_id=job.source_record_id
               AND parent.provider_id=job.provider_id AND parent.query=job.query
               AND parent.status='review_required'
              JOIN real_preview.geocode_targets target ON target.job_id=job.job_id
              JOIN real_preview.candidates candidate ON candidate.candidate_id=target.candidate_id
              JOIN real_preview.candidate_private_location_evidence location
                ON location.candidate_id=candidate.candidate_id
               AND location.snapshot_sha256=candidate.snapshot_sha256
               AND location.source_id=candidate.source_id
              JOIN real_preview.private_geocoding_source_profiles profile
                ON profile.profile_id IN ('locationiq-gb-fsa-approved-establishments',
                                          'locationiq-gb-fss-approved-establishments')
               AND profile.source_id=candidate.source_id AND profile.country_code='GB'
               AND profile.provider_id='locationiq' AND profile.enabled
             WHERE job.provider_id='locationiq'
               AND candidate.source_id IN ('fsa_approved_establishments','fss_approved_establishments')
               AND candidate.country_code='GB' AND candidate.default_map_scope
               AND candidate.latitude IS NULL AND candidate.longitude IS NULL
               AND candidate.display_latitude IS NULL AND candidate.display_longitude IS NULL
               AND candidate.snapshot_sha256=(SELECT run.snapshot_sha256
                   FROM real_preview.source_preview_runs run
                   WHERE run.source_id=candidate.source_id
                   ORDER BY run.created_at DESC,run.run_id DESC LIMIT 1)
               AND EXISTS (SELECT 1 FROM uec.geocode_job_events queued
                    WHERE queued.job_id=job.job_id AND queued.event_type='queued'
                      AND queued.details->>'processing_mode'='private_locationiq_source_profile'
                      AND queued.details->>'profile_id'=profile.profile_id
                      AND queued.details->>'first_pass_only'='true')
               AND NOT EXISTS (SELECT 1 FROM uec.public_access_restricted restricted
                    WHERE restricted.source_record_id=job.source_record_id)
               AND NOT EXISTS (SELECT 1 FROM real_preview.enrichment_state_events state
                    WHERE state.candidate_id=candidate.candidate_id AND state.state_code='restricted')
               AND NOT EXISTS (SELECT 1 FROM real_preview.locationiq_first_pass_context_audit audit
                    WHERE audit.candidate_id=candidate.candidate_id
                      AND audit.geocode_result_id=parent.geocode_result_id)
             ORDER BY job.job_id,parent.queried_at DESC,parent.geocode_result_id DESC
             LIMIT %s
        """, (limit,)).fetchall()
        counts["examined"] = len(rows)
        for (job_id, source_record_id, query, parent_id, parent_response, attempt, queried_at) in rows:
            try:
                parent_id = uuid.UUID(str(parent_id))
            except (TypeError, ValueError):
                counts["rejected"] += 1
                continue
            try:
                payload = json.loads(query)
            except (TypeError, json.JSONDecodeError):
                counts["rejected"] += 1
                continue
            if (not isinstance(payload, dict) or payload.get("schema_version") != "uec-address-query-v1"
                    or payload.get("country_code") != "GB"):
                counts["rejected"] += 1
                continue
            selected = select_postcode_reference(parent_response, payload.get("postcode"))
            if selected is None:
                counts["rejected"] += 1
                continue
            index, latitude, longitude = selected
            result_id = derived_result_id(parent_id)
            if connection.execute("SELECT 1 FROM uec.geocode_results WHERE geocode_result_id=%s",
                                  (result_id,)).fetchone():
                counts["already_present"] += 1
                continue
            response = copy.deepcopy(parent_response)
            response["_uec_parent_geocode_result_id"] = str(parent_id)
            response["_uec_ruleset_version"] = RULESET
            response["_uec_selected_result_index"] = index
            response["_uec_offline_recheck"] = True
            parent = {"source_record_id": source_record_id, "query": query,
                      "attempt_number": attempt, "queried_at": queried_at}
            try:
                inserted = _append_result(connection, parent=parent, result_id=result_id,
                    response=response, latitude=latitude, longitude=longitude)
            except (psycopg.errors.CheckViolation, ValueError):
                counts["database_rejected"] += 1
                continue
            counts["appended" if inserted else "already_present"] += 1
    return {"ruleset": RULESET, **counts, "provider_calls": 0,
            "requests_or_job_events_created": 0, "parent_results_modified": 0}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(reconcile(os.environ.get("UEC_DATABASE_URL", ""), limit=args.limit), sort_keys=True))
    except Exception as error:
        print(json.dumps({"status": "failed", "error_type": type(error).__name__}, sort_keys=True))
        raise SystemExit(1)
