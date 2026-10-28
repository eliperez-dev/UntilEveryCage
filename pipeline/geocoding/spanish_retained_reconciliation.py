"""Replay saved Spanish LocationIQ responses without external requests."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import uuid

import psycopg

from .locationiq import LocationIqAdapter
from .spanish_addresses import RULESET
from pipeline.scripts.release_baseline import load_contract, validate_database_url, verify_connection

ROOT = Path(__file__).resolve().parents[2]
DATABASE = "uec_launch_sources_test_20261025"
MATCH_METHOD = "locationiq_spanish_replay_v1"
NAMESPACE = uuid.UUID("c432cd12-b496-5d54-aaeb-9551f337b480")


class _Response:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, size):
        return self.payload[:size]


def replay(query: str, retained_response: dict) -> dict | None:
    """Select exactly one address candidate; the opener cannot make a request."""
    if not isinstance(retained_response, dict):
        return None
    payload = retained_response.get("results")
    if not isinstance(payload, list) or not 1 <= len(payload) <= 2:
        return None
    adapter = LocationIqAdapter(
        api_key="offline-placeholder", country_code="es", private_source_profile=True,
        query_kind="source_address_first_pass", first_pass_source=True,
        opener=lambda *_a, **_k: _Response(payload),
    )
    outcome = adapter.geocode(query)
    return outcome.response if outcome.status == "accepted" else None


def result_id(parent_id) -> uuid.UUID:
    return uuid.uuid5(NAMESPACE, f"{parent_id}:{RULESET}")


def append_evaluation(connection, *, parent_id, source_record_id, query, attempt,
                      queried_at, response, candidate_ids) -> int:
    """Rollback any evaluation lacking an independently source-bound SQL audit."""
    selected = response["results"][int(response["_uec_selected_result_index"])]
    child_id = result_id(parent_id)
    response = copy.deepcopy(response)
    response["_uec_parent_geocode_result_id"] = str(parent_id)
    response["_uec_ruleset_version"] = RULESET
    with connection.transaction():
        inserted = connection.execute("""
            INSERT INTO uec.geocode_results
                (geocode_result_id,source_record_id,provider_id,query,provider_address_id,
                 result,precision,match_method,status,attempt_number,retryable,response,queried_at)
            VALUES(%s,%s,'locationiq',%s,%s,
                   ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography,
                   'locationiq_address_point',%s,'accepted',%s,false,%s::jsonb,%s)
            ON CONFLICT(geocode_result_id) DO NOTHING RETURNING geocode_result_id
        """, (child_id, source_record_id, query,
              str(selected["place_id"]) if selected.get("place_id") is not None else None,
              float(selected["lon"]), float(selected["lat"]), MATCH_METHOD, attempt,
              json.dumps(response, ensure_ascii=False), queried_at)).fetchone()
        audited = connection.execute("""
            SELECT count(*) FROM real_preview.geocode_display_evidence evidence
            JOIN real_preview.locationiq_first_pass_context_audit audit
              USING(candidate_id,geocode_result_id)
            WHERE evidence.geocode_result_id=%s AND evidence.candidate_id=ANY(%s::uuid[])
        """, (child_id, list(candidate_ids))).fetchone()[0]
        if audited != len(set(candidate_ids)):
            raise ValueError("derived_evaluation_has_no_source_bound_display")
        return int(inserted is not None)


def reconcile(database_url: str, *, limit: int, apply: bool = False) -> dict:
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 10000:
        raise ValueError("finite_limit_required")
    validate_database_url(database_url)
    counts = {"examined": 0, "matched": 0, "appended": 0, "already_present": 0,
              "rejected": 0, "database_rejected": 0, "matched_candidate_records": 0}
    by_source = {}
    with psycopg.connect(database_url) as connection:
        if connection.execute("SELECT current_database()").fetchone()[0] != DATABASE:
            raise ValueError("wrong_disposable_database")
        contract = load_contract(ROOT / "pipeline/contracts/development-baseline.json")
        if verify_connection(connection, contract)["status"] != "verified":
            raise ValueError("baseline_not_verified")
        rows = connection.execute("""
            SELECT result.geocode_result_id,result.source_record_id,result.query,result.attempt_number,
                   result.queried_at,result.response,candidate.source_id,
                   array_agg(DISTINCT candidate.candidate_id)
            FROM uec.geocode_results result
            JOIN uec.geocode_jobs job ON job.source_record_id=result.source_record_id
                AND job.query=result.query AND job.provider_id=result.provider_id
            JOIN real_preview.geocode_targets target USING(job_id)
            JOIN real_preview.candidates candidate ON candidate.candidate_id=target.candidate_id
                AND candidate.source_id=target.source_id AND candidate.snapshot_sha256=target.snapshot_sha256
            JOIN real_preview.private_geocoding_source_profiles profile
                ON profile.source_id=candidate.source_id AND profile.provider_id='locationiq'
                AND profile.country_code='ES' AND profile.enabled
            WHERE result.provider_id='locationiq' AND result.match_method='locationiq_forward'
              AND result.status='review_required'
              AND candidate.source_id IN ('es.locations','es.cat.feed-sandach')
              AND candidate.country_code='ES' AND candidate.default_map_scope
              AND candidate.latitude IS NULL AND candidate.longitude IS NULL
              AND candidate.location_class<>'numeric_source_coordinate'
              AND candidate.snapshot_sha256=(SELECT run.snapshot_sha256 FROM real_preview.source_preview_runs run
                  WHERE run.source_id=candidate.source_id ORDER BY run.created_at DESC,run.run_id DESC LIMIT 1)
              AND NOT EXISTS (SELECT 1 FROM uec.public_access_restricted restricted
                  WHERE restricted.source_record_id=result.source_record_id)
              AND NOT EXISTS (SELECT 1 FROM real_preview.enrichment_state_events state
                  WHERE state.candidate_id=candidate.candidate_id AND state.state_code='restricted')
              AND NOT EXISTS (SELECT 1 FROM real_preview.geocode_display_evidence exact
                  WHERE exact.candidate_id=candidate.candidate_id
                    AND exact.display_precision='provider_address_point_high_confidence')
            GROUP BY result.geocode_result_id,candidate.source_id
            ORDER BY result.geocode_result_id LIMIT %s
        """, (limit,)).fetchall()
        # Materialize before appending. Each result is committed independently;
        # an interrupted recovery can resume through deterministic child IDs.
        connection.commit()
        for parent_id, source_record_id, query, attempt, queried_at, retained, source, candidates in rows:
            counts["examined"] += 1
            child_id = result_id(parent_id)
            if connection.execute("SELECT 1 FROM uec.geocode_results WHERE geocode_result_id=%s",
                                  (child_id,)).fetchone():
                counts["already_present"] += 1
                connection.commit()
                continue
            response = replay(query, retained)
            if response is None:
                counts["rejected"] += 1
                connection.commit()
                continue
            counts["matched"] += 1
            counts["matched_candidate_records"] += len(candidates)
            by_source[source] = by_source.get(source, 0) + len(candidates)
            if apply:
                try:
                    counts["appended"] += append_evaluation(connection,
                        parent_id=parent_id, source_record_id=source_record_id, query=query,
                        attempt=attempt, queried_at=queried_at, response=response, candidate_ids=candidates)
                except (ValueError, psycopg.errors.CheckViolation):
                    counts["database_rejected"] += 1
            connection.commit()
        if verify_connection(connection, contract)["status"] != "verified":
            raise ValueError("baseline_changed")
    return {"ruleset": RULESET, "mode": "apply" if apply else "dry_run", **counts,
            "matched_records_by_source": by_source, "provider_calls": 0, "parent_results_modified": 0}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        print(json.dumps(reconcile(os.environ.get("UEC_DATABASE_URL", ""),
                                   limit=args.limit, apply=args.apply), sort_keys=True))
    except Exception as error:
        print(json.dumps({"status": "failed", "error_type": type(error).__name__}, sort_keys=True))
        raise SystemExit(1)
