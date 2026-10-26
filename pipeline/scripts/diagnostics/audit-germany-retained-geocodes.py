#!/usr/bin/env python3
"""Count German street-spelling recovery candidates, without requests or writes."""
import json
import os
from pathlib import Path
import sys

import psycopg

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from pipeline.geocoding.german_streets import street_matches
from pipeline.geocoding.locationiq import LocationIqAdapter
from pipeline.scripts.release_baseline import load_contract, validate_database_url, verify_connection

DATABASE = "uec_launch_sources_test_20261025"


class _StreetSpellingReplay(LocationIqAdapter):
    @classmethod
    def _street_matches(cls, source, road, number):
        return super()._street_matches(source, road, number) or street_matches(source, road, number)


class _Response:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, size):
        return self.payload[:size]


def classify(query, response):
    """Replay only retained candidates. Returned labels are not approval decisions."""
    if (not isinstance(response, dict) or not isinstance(response.get("results"), list)
            or not 1 <= len(response["results"]) <= 2):
        return "invalid_retained_response"
    def evaluate(adapter):
        return adapter(api_key="offline-placeholder", country_code="de",
                       private_source_profile=True,
                       opener=lambda *_args, **_kwargs: _Response(response["results"])).geocode(query)
    if evaluate(LocationIqAdapter).status == "accepted":
        return "already_matches_current_rule"
    outcome = evaluate(_StreetSpellingReplay)
    if outcome.status == "accepted":
        return "street_spelling_recovery_candidate"
    if outcome.acceptance == "ambiguous_multiple_viable_results":
        return "ambiguous_after_street_normalization"
    return "still_requires_review"


def audit(database_url):
    validate_database_url(database_url)
    with psycopg.connect(database_url, options="-c default_transaction_read_only=on -c statement_timeout=30000") as connection:
        if connection.execute("SELECT current_database()").fetchone()[0] != DATABASE:
            raise ValueError("wrong_disposable_database")
        baseline = verify_connection(connection, load_contract(ROOT / "pipeline/contracts/development-baseline.json"))
        if baseline["status"] != "verified":
            raise ValueError("baseline_not_verified")
        rows = connection.execute("""
            SELECT DISTINCT ON (candidate.candidate_id) job.query,result.response,
                   location.location_evidence->>'address',
                   COALESCE(location.location_evidence->>'postal_code',
                     (regexp_match(COALESCE(location.location_evidence->>'city',candidate.city),'^([0-9]{5})[[:space:]]+'))[1]),
                   regexp_replace(COALESCE(location.location_evidence->>'city',candidate.city),'^[0-9]{5}[[:space:]]+',''),
                   COALESCE(location.location_evidence->>'region','')
            FROM real_preview.candidates candidate
            JOIN real_preview.candidate_private_location_evidence location USING(candidate_id)
            JOIN real_preview.geocode_targets target ON target.candidate_id=candidate.candidate_id
              AND target.snapshot_sha256=candidate.snapshot_sha256 AND target.source_id=candidate.source_id
            JOIN uec.geocode_jobs job ON job.job_id=target.job_id AND job.provider_id='locationiq'
            JOIN uec.geocode_results result ON result.source_record_id=job.source_record_id
              AND result.query=job.query AND result.provider_id=job.provider_id
            WHERE candidate.source_id='de.locations' AND candidate.country_code='DE'
              AND candidate.default_map_scope AND candidate.display_latitude IS NULL AND candidate.display_longitude IS NULL
              AND candidate.snapshot_sha256=(SELECT run.snapshot_sha256 FROM real_preview.source_preview_runs run
                  WHERE run.source_id='de.locations' ORDER BY run.created_at DESC,run.run_id DESC LIMIT 1)
              AND result.status='review_required'
              AND EXISTS (SELECT 1 FROM real_preview.private_geocoding_source_profiles profile
                  WHERE profile.profile_id='locationiq-de-bltu' AND profile.enabled AND profile.provider_id=job.provider_id)
              AND NOT EXISTS (SELECT 1 FROM uec.public_access_restricted restricted WHERE restricted.source_record_id=job.source_record_id)
              AND NOT EXISTS (SELECT 1 FROM real_preview.enrichment_state_events state
                  WHERE state.candidate_id=candidate.candidate_id AND state.state_code='restricted')
            ORDER BY candidate.candidate_id,result.queried_at DESC,result.geocode_result_id DESC
        """).fetchall()
        counts = {}
        for query, response, *source_context in rows:
            parsed = LocationIqAdapter._parse_query(query)
            if parsed is None or tuple(part.strip() if isinstance(part, str) else "" for part in source_context) != parsed:
                label = "source_context_changed_or_invalid"
            else:
                label = classify(query, response)
            counts[label] = counts.get(label, 0) + 1
        return {"source": "de.locations", "records_examined": len(rows), "outcomes": counts,
                "baseline": baseline["status"], "provider_calls": 0, "database_writes": 0,
                "points_promoted": 0, "rule": "german-street-spelling-audit-v1"}


def main():
    try:
        result = audit(os.environ.get("UEC_DATABASE_URL", ""))
    except Exception as error:
        print(json.dumps({"status": "failed", "error_type": type(error).__name__}))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
