#!/usr/bin/env python3
"""Stage a bounded LocationIQ fallback batch; optionally drain only that batch."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys

import psycopg

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from pipeline.geocoding.private_profiles import profile_by_id
from pipeline.geocoding.locationiq import LocationIqAdapter

PROFILE = "locationiq-de-bltu"
DATABASE = "uec_launch_sources_test_20261025"
COHORTS = ("all", "unqueried", "previous-provider-unmapped")


def activate(database_url: str, *, limit: int = 24, cohort: str = "all",
             allow_parallel_primary: bool = False):
    if not 1 <= limit <= 5000:
        raise ValueError("fallback batch must contain 1 to 5000 records")
    if cohort not in COHORTS:
        raise ValueError("unsupported address cohort")
    prior_result_required = {"all": None, "unqueried": False,
                             "previous-provider-unmapped": True}[cohort]
    profile = profile_by_id(PROFILE)
    if profile is None or profile.get("provider_id") != "locationiq":
        raise ValueError("LocationIQ profile is not enabled")
    with psycopg.connect(database_url) as connection, connection.transaction():
        if connection.execute("SELECT current_database()").fetchone()[0] != DATABASE:
            raise ValueError("database_identity_invalid")
        if not allow_parallel_primary:
            budget = connection.execute("""SELECT reserved_requests >= daily_limit
                FROM uec.geocode_provider_budgets WHERE provider_id='geoapify'
                AND budget_date=(now() AT TIME ZONE 'UTC')::date""").fetchone()
            if not budget or not budget[0]:
                raise ValueError("primary_provider_daily_allowance_not_exhausted")
        rows = connection.execute("""
            SELECT candidate.candidate_id,candidate.snapshot_sha256,candidate.source_group_key,
                   original.source_record_id,location.location_evidence->>'address',
                   COALESCE(location.location_evidence->>'postal_code',
                       (regexp_match(COALESCE(location.location_evidence->>'city',candidate.city),'^([0-9]{5})[[:space:]]+'))[1]),
                   regexp_replace(COALESCE(location.location_evidence->>'city',candidate.city),'^[0-9]{5}[[:space:]]+',''),
                   location.location_evidence->>'region'
            FROM real_preview.candidates candidate
            JOIN real_preview.candidate_private_location_evidence location ON location.candidate_id=candidate.candidate_id
            JOIN LATERAL (
                SELECT job.source_record_id FROM real_preview.geocode_targets target
                JOIN uec.geocode_jobs job ON job.job_id=target.job_id AND job.provider_id='geoapify'
                WHERE target.candidate_id=candidate.candidate_id AND target.snapshot_sha256=candidate.snapshot_sha256
                  AND EXISTS (SELECT 1 FROM uec.geocode_job_events queued WHERE queued.job_id=job.job_id
                      AND queued.event_type='queued' AND queued.details->>'profile_id'='geoapify-de-bltu')
                ORDER BY target.created_at,job.job_id LIMIT 1
            ) original ON true
            WHERE candidate.source_id='de.locations' AND candidate.country_code='DE'
              AND candidate.snapshot_sha256=(SELECT run.snapshot_sha256 FROM real_preview.source_preview_runs run
                  WHERE run.source_id='de.locations' ORDER BY run.created_at DESC,run.run_id DESC LIMIT 1)
              AND candidate.default_map_scope AND candidate.location_class <> 'numeric_source_coordinate'
              AND candidate.display_latitude IS NULL AND candidate.display_longitude IS NULL
              AND NULLIF(trim(location.location_evidence->>'address'),'') IS NOT NULL
              AND NULLIF(trim(COALESCE(location.location_evidence->>'city',candidate.city)),'') IS NOT NULL
              AND COALESCE(location.location_evidence->>'postal_code',
                  (regexp_match(COALESCE(location.location_evidence->>'city',candidate.city),'^([0-9]{5})[[:space:]]+'))[1]) ~ '^[0-9]{5}$'
              AND COALESCE(location.location_evidence->>'country_code','DE')='DE'
              AND NOT EXISTS (SELECT 1 FROM uec.public_access_restricted restricted
                  WHERE restricted.source_record_id=original.source_record_id)
              AND NOT EXISTS (SELECT 1 FROM real_preview.geocode_targets target
                  JOIN uec.geocode_jobs job ON job.job_id=target.job_id AND job.provider_id='locationiq'
                  WHERE target.candidate_id=candidate.candidate_id AND target.snapshot_sha256=candidate.snapshot_sha256)
              AND NOT EXISTS (SELECT 1 FROM real_preview.enrichment_state_events state
                  WHERE state.candidate_id=candidate.candidate_id AND state.state_code='restricted')
              AND (%s::boolean IS NULL OR EXISTS (
                  SELECT 1 FROM uec.geocode_results result
                  WHERE result.source_record_id=original.source_record_id
                    AND result.provider_id='geoapify') = %s::boolean)
            ORDER BY EXISTS (SELECT 1 FROM uec.geocode_results result
                WHERE result.source_record_id=original.source_record_id AND result.provider_id='geoapify'),
                candidate.candidate_id LIMIT %s FOR UPDATE OF candidate SKIP LOCKED
        """, (prior_result_required, prior_result_required, limit)).fetchall()
        job_ids = []
        rejected_queries = 0
        for candidate, snapshot, source_key, source_record, street, postal, city, region in rows:
            query = ", ".join(part.strip() for part in (street, postal, city, region, "Germany") if part and part.strip())
            if LocationIqAdapter._parse_query(query) is None:
                rejected_queries += 1
                continue
            job = connection.execute("""INSERT INTO uec.geocode_jobs(source_record_id,provider_id,query)
                VALUES(%s,'locationiq',%s) ON CONFLICT(source_record_id,provider_id,query) DO NOTHING
                RETURNING job_id""", (source_record, query)).fetchone()
            if job is None:
                job = connection.execute("SELECT job_id FROM uec.geocode_jobs WHERE source_record_id=%s AND provider_id='locationiq' AND query=%s",
                                         (source_record, query)).fetchone()
            job_id = job[0]
            connection.execute("""INSERT INTO real_preview.geocode_targets
                (job_id,candidate_id,snapshot_sha256,source_id,source_record_key)
                VALUES(%s,%s,%s,'de.locations',%s) ON CONFLICT DO NOTHING""", (job_id,candidate,snapshot,source_key))
            connection.execute("""INSERT INTO uec.geocode_job_events(job_id,event_type,attempt_number,retryable,details)
                SELECT %s,'queued',1,false,%s::jsonb WHERE NOT EXISTS
                  (SELECT 1 FROM uec.geocode_job_events WHERE job_id=%s)""",
                (job_id,json.dumps({"processing_mode":"private_locationiq_source_profile","profile_id":PROFILE,
                                   "selection_cohort":cohort,
                                   "fallback_from_provider":"geoapify",
                                   "fallback_reason":("operator_authorized_parallel_provider" if allow_parallel_primary
                                                      else "primary_daily_allowance_exhausted")}),job_id))
            connection.execute("""INSERT INTO real_preview.enrichment_state_events
                (candidate_id,snapshot_sha256,source_id,source_record_key,state_code,reason_code)
                VALUES(%s,%s,'de.locations',%s,'queued','locationiq_de_bltu_fallback')""", (candidate,snapshot,source_key))
            job_ids.append(job_id)
        return {"provider":"locationiq","source":"de.locations","cohort":cohort,"jobs_staged":len(job_ids),
                "invalid_query_formats_skipped":rejected_queries,"provider_calls":0}, tuple(job_ids)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=24)
    parser.add_argument("--cohort", choices=COHORTS, default="all")
    parser.add_argument("--run-worker", action="store_true")
    parser.add_argument("--provider-account", choices=("primary","secondary"), default="primary")
    parser.add_argument("--allow-parallel-primary", action="store_true",
                        help="Explicit operator opt-in; partition address batches between providers before running workers")
    args = parser.parse_args()
    database_url = os.environ.get("UEC_DATABASE_URL")
    key_env = "LOCATIONIQ_SECONDARY_API_KEY" if args.provider_account == "secondary" else "LOCATIONIQ_API_KEY"
    if not database_url or not os.environ.get(key_env, "").strip():
        print(json.dumps({"status":"blocked","reason":"database_or_locationiq_key_missing"}))
        return 2
    try:
        summary, jobs = activate(database_url, limit=args.limit, cohort=args.cohort,
                                 allow_parallel_primary=args.allow_parallel_primary)
        print(json.dumps(summary), flush=True)
        if args.run_worker and jobs:
            spec = importlib.util.spec_from_file_location("locationiq_worker", Path(__file__).with_name("geocode-worker.py"))
            worker = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(worker)
            processed = worker.run(database_url,"locationiq",len(jobs),0,1,daily_budget=5000,
                                   max_attempts=2,
                                   provider_interval=1.05,private_source_profile_id=PROFILE,job_ids=jobs,
                                   provider_account=args.provider_account)
            print(json.dumps({"provider":"locationiq","status":"complete","processed":processed}))
        return 0
    except Exception as error:
        # Do not print exception text: provider/connection errors may contain secrets.
        print(json.dumps({"status":"failed","error_type":type(error).__name__,
                          "sqlstate":getattr(error,"sqlstate",None)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
