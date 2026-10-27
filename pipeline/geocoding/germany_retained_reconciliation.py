"""Versioned offline replay for retained German LocationIQ responses."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import uuid

import psycopg

from .german_streets import street_matches
from .locationiq import LocationIqAdapter
from pipeline.scripts.release_baseline import load_contract, validate_database_url, verify_connection

ROOT = Path(__file__).resolve().parents[2]
DATABASE = "uec_launch_sources_test_20261025"
RULESET = "german-street-spelling-v1"
MATCH_METHOD = "locationiq_retained_street_v1"
NAMESPACE = uuid.UUID("a0d20735-9455-5eb0-8ef5-7d7d15153f35")


class _Response:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, size):
        return self.payload[:size]


class _ReplayAdapter(LocationIqAdapter):
    @classmethod
    def _street_matches(cls, source, road, number):
        return super()._street_matches(source, road, number) or street_matches(source, road, number)


def replay(query: str, retained_response: dict) -> dict | None:
    """Return a sanitized, uniquely selected response when v1 matches."""
    if not isinstance(retained_response, dict) or not isinstance(retained_response.get("results"), list):
        return None
    payload = retained_response["results"]
    if not 1 <= len(payload) <= 2:
        return None
    adapter = _ReplayAdapter(
        api_key="offline-placeholder", country_code="de", private_source_profile=True,
        opener=lambda *_args, **_kwargs: _Response(payload),
    )
    outcome = adapter.geocode(query)
    if outcome.status != "accepted":
        return None
    return outcome.response


def _context_matches(query, street, postcode, locality, region) -> bool:
    parsed = LocationIqAdapter._parse_query(query)
    if parsed is None:
        return False
    context = tuple(value.strip() if isinstance(value, str) else ""
                    for value in (street, postcode, locality, region))
    return context == parsed


def _result_id(parent_id: uuid.UUID) -> uuid.UUID:
    return uuid.uuid5(NAMESPACE, f"{parent_id}:{RULESET}")


def _append_evaluation(connection, *, parent_id, child_id, candidate_id, snapshot,
                       source_record_id, query, attempt, queried_at, response,
                       selected, latitude, longitude) -> bool:
    # A rejected independent database check rolls back this evaluation only.
    with connection.transaction():
        connection.execute("""
            INSERT INTO real_preview.germany_retained_geocode_reconciliations
                (parent_geocode_result_id,derived_geocode_result_id,candidate_id,
                 snapshot_sha256,ruleset_version,selected_result_index)
            VALUES(%s,%s,%s,%s,%s,%s)
            ON CONFLICT(parent_geocode_result_id,ruleset_version) DO NOTHING
        """, (parent_id, child_id, candidate_id, snapshot, RULESET,
              int(response["_uec_selected_result_index"])))
        inserted = connection.execute("""
            INSERT INTO uec.geocode_results
                (geocode_result_id,source_record_id,provider_id,query,provider_address_id,
                 result,precision,match_method,status,attempt_number,retryable,response,queried_at)
            VALUES(%s,%s,'locationiq',%s,%s,
                   ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography,
                   'locationiq_address_point',%s,'accepted',%s,false,%s::jsonb,%s)
            ON CONFLICT(geocode_result_id) DO NOTHING RETURNING geocode_result_id
        """, (child_id, source_record_id, query,
              str(selected.get("place_id")) if selected.get("place_id") is not None else None,
              longitude, latitude, MATCH_METHOD, attempt,
              json.dumps(response, ensure_ascii=False), queried_at)).fetchone()
        if not connection.execute("""
            SELECT 1 FROM real_preview.geocode_display_evidence
            WHERE candidate_id=%s AND geocode_result_id=%s
        """, (candidate_id, child_id)).fetchone():
            raise ValueError("derived_evaluation_has_no_audited_display")
        return inserted is not None


def reconcile(database_url: str, *, limit: int) -> dict:
    """Append derived accepted evaluations; never update retained provider rows."""
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1 or limit > 5000:
        raise ValueError("finite_limit_required")
    validate_database_url(database_url)
    contract = load_contract(ROOT / "pipeline/contracts/development-baseline.json")
    counts = {"examined": 0, "appended": 0, "already_present": 0, "rejected": 0,
              "database_rejected": 0}
    with psycopg.connect(database_url) as connection:
        with connection.transaction():
            if connection.execute("SELECT current_database()").fetchone()[0] != DATABASE:
                raise ValueError("wrong_disposable_database")
            if verify_connection(connection, contract)["status"] != "verified":
                raise ValueError("baseline_not_verified")
            rows = connection.execute("""
                SELECT candidate.candidate_id, candidate.snapshot_sha256,
                       job.source_record_id, job.query, result.geocode_result_id,
                       result.attempt_number, result.queried_at, result.response,
                       location.location_evidence->>'address',
                       COALESCE(location.location_evidence->>'postal_code',
                         (regexp_match(COALESCE(location.location_evidence->>'city',candidate.city),
                                       '^([0-9]{5})[[:space:]]+'))[1]),
                       regexp_replace(COALESCE(location.location_evidence->>'city',candidate.city),
                                      '^[0-9]{5}[[:space:]]+',''),
                       COALESCE(location.location_evidence->>'region','')
                  FROM real_preview.candidates candidate
                  JOIN real_preview.candidate_private_location_evidence location USING(candidate_id)
                  JOIN real_preview.geocode_targets target ON target.candidate_id=candidate.candidate_id
                    AND target.snapshot_sha256=candidate.snapshot_sha256 AND target.source_id=candidate.source_id
                  JOIN uec.geocode_jobs job ON job.job_id=target.job_id AND job.provider_id='locationiq'
                  JOIN LATERAL (
                    SELECT retained.* FROM uec.geocode_results retained
                     WHERE retained.source_record_id=job.source_record_id
                       AND retained.query=job.query AND retained.provider_id=job.provider_id
                       AND retained.status='review_required'
                     ORDER BY retained.queried_at DESC,retained.geocode_result_id DESC LIMIT 1
                  ) result ON true
                  WHERE candidate.source_id='de.locations' AND candidate.country_code='DE'
                    AND candidate.default_map_scope AND candidate.display_latitude IS NULL
                    AND candidate.display_longitude IS NULL
                    AND candidate.snapshot_sha256=(SELECT run.snapshot_sha256
                      FROM real_preview.source_preview_runs run WHERE run.source_id='de.locations'
                      ORDER BY run.created_at DESC,run.run_id DESC LIMIT 1)
                    AND EXISTS (SELECT 1 FROM real_preview.private_geocoding_source_profiles profile
                      WHERE profile.profile_id='locationiq-de-bltu' AND profile.enabled
                        AND profile.provider_id=job.provider_id)
                    AND EXISTS (SELECT 1 FROM uec.geocode_job_events queued
                      WHERE queued.job_id=job.job_id AND queued.event_type='queued'
                        AND queued.details->>'profile_id'='locationiq-de-bltu'
                        AND queued.details->>'processing_mode'='private_locationiq_source_profile')
                    AND NOT EXISTS (SELECT 1 FROM uec.public_access_restricted restricted
                      WHERE restricted.source_record_id=job.source_record_id)
                    AND NOT EXISTS (SELECT 1 FROM real_preview.enrichment_state_events state
                      WHERE state.candidate_id=candidate.candidate_id AND state.state_code='restricted')
                  ORDER BY result.queried_at DESC,result.geocode_result_id DESC
                  LIMIT %s FOR UPDATE OF candidate SKIP LOCKED
            """, (limit,)).fetchall()
            counts["examined"] = len(rows)
            for (candidate_id, snapshot, source_record_id, query, parent_id, attempt,
                 queried_at, parent_response, street, postcode, locality, region) in rows:
                try:
                    parent_id = uuid.UUID(str(parent_id))
                except (TypeError, ValueError):
                    counts["rejected"] += 1
                    continue
                if not _context_matches(query, street, postcode, locality, region):
                    counts["rejected"] += 1
                    continue
                child_id = _result_id(parent_id)
                exists = connection.execute("""
                    SELECT 1 FROM real_preview.germany_retained_geocode_reconciliations
                    WHERE parent_geocode_result_id=%s AND ruleset_version=%s
                """, (parent_id, RULESET)).fetchone()
                if exists:
                    counts["already_present"] += 1
                    continue
                selected_response = replay(query, parent_response)
                if selected_response is None:
                    counts["rejected"] += 1
                    continue
                response = copy.deepcopy(selected_response)
                response["_uec_parent_geocode_result_id"] = str(parent_id)
                response["_uec_ruleset_version"] = RULESET
                selected = response["results"][int(response["_uec_selected_result_index"])]
                try:
                    latitude, longitude = float(selected["lat"]), float(selected["lon"])
                except (KeyError, TypeError, ValueError):
                    counts["rejected"] += 1
                    continue
                try:
                    inserted = _append_evaluation(connection, parent_id=parent_id,
                        child_id=child_id, candidate_id=candidate_id, snapshot=snapshot,
                        source_record_id=source_record_id, query=query, attempt=attempt,
                        queried_at=queried_at, response=response, selected=selected,
                        latitude=latitude, longitude=longitude)
                except (psycopg.errors.CheckViolation, ValueError):
                    counts["database_rejected"] += 1
                    continue
                counts["appended" if inserted else "already_present"] += 1
    return {"source": "de.locations", "ruleset": RULESET, **counts,
            "provider_calls": 0, "parent_results_modified": 0}


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(reconcile(os.environ.get("UEC_DATABASE_URL", ""), limit=args.limit), sort_keys=True))
    except Exception as error:
        print(json.dumps({"status": "failed", "error_type": type(error).__name__}, sort_keys=True))
        raise SystemExit(1)
