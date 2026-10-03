#!/usr/bin/env python3
"""Append a bounded attempt-2 queue event for current AU NPI auth failures.

This does not make provider calls, reset budgets, or alter prior jobs/results.
Run only after independently confirming the saved Geoapify key is corrected.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import psycopg


PILOT_SIZE = 24
SOURCE_ID = "au.npi.facilities"
PROVIDER_ID = "geoapify"
RECOVERY_REASON = "operator_authorized_geoapify_key_recovery"


def validate_options(limit: int, key_configured: bool, key_verified: bool) -> None:
    if limit < 1 or limit > PILOT_SIZE:
        raise ValueError("recovery limit must be between 1 and 24")
    if not key_configured:
        raise ValueError("GEOAPIFY_API_KEY is not configured")
    if not key_verified:
        raise ValueError("explicit corrected-key confirmation is required")


def requeue(database_url: str, limit: int, *, key_configured: bool, key_verified: bool) -> dict[str, int | str]:
    validate_options(limit, key_configured, key_verified)
    with psycopg.connect(database_url) as connection:
        with connection.transaction():
            budget_date = connection.execute(
                "SELECT (now() AT TIME ZONE 'UTC')::date"
            ).fetchone()[0]
            budget = connection.execute(
                """SELECT daily_limit, reserved_requests
                     FROM uec.geocode_provider_budgets
                    WHERE provider_id=%s AND budget_date=%s
                    FOR UPDATE""",
                (PROVIDER_ID, budget_date),
            ).fetchone()
            # No row at a new UTC date means this date has no reservations yet;
            # the worker creates and atomically enforces the bounded ledger row
            # before each provider call. Never create/reset it during requeue.
            remaining = PILOT_SIZE if budget is None else max(
                0, min(PILOT_SIZE, budget[0]) - budget[1]
            )
            if remaining < limit:
                raise RuntimeError("daily Geoapify pilot budget cannot cover the requested recovery batch")

            targets = connection.execute(
                """WITH latest AS (
                       SELECT COALESCE(
                           (SELECT run.snapshot_sha256 FROM real_preview.source_preview_runs run
                            WHERE run.source_id=%s ORDER BY run.created_at DESC,run.run_id DESC LIMIT 1),
                           (SELECT manifest.snapshot_sha256 FROM real_preview.source_manifests manifest
                            WHERE manifest.source_id=%s ORDER BY manifest.retrieved_at DESC,
                                  manifest.snapshot_sha256 DESC LIMIT 1)
                       ) AS snapshot_sha256
                   )
                   SELECT job.job_id
                     FROM real_preview.geocode_targets target
                     JOIN real_preview.candidates candidate
                       ON candidate.candidate_id=target.candidate_id
                     JOIN uec.geocode_jobs job ON job.job_id=target.job_id
                     JOIN uec.geocode_job_current current ON current.job_id=job.job_id
                     JOIN uec.geocode_results result
                       ON result.source_record_id=job.source_record_id
                      AND result.provider_id=job.provider_id
                      AND result.query=job.query
                      AND result.attempt_number=current.attempt_number
                     CROSS JOIN latest
                    WHERE target.source_id=%s
                      AND target.snapshot_sha256=latest.snapshot_sha256
                      AND candidate.source_id=%s
                      AND candidate.snapshot_sha256=latest.snapshot_sha256
                      AND candidate.country_code='AU'
                      AND candidate.location_class='city_postal'
                      AND job.provider_id=%s
                      AND current.event_type='failed'
                      AND current.attempt_number=1
                      AND current.retryable=false
                      AND result.status='failed'
                      AND result.attempt_number=1
                      AND result.response->>'error'='authentication_rejected'
                      AND NOT EXISTS (
                          SELECT 1 FROM uec.public_access_restricted restricted
                          WHERE restricted.source_record_id=job.source_record_id
                      )
                    ORDER BY candidate.candidate_id
                    FOR UPDATE OF job SKIP LOCKED
                    LIMIT %s""",
                (SOURCE_ID, SOURCE_ID, SOURCE_ID, SOURCE_ID, PROVIDER_ID, limit),
            ).fetchall()

            details = json.dumps(
                {
                    "recovery_reason": RECOVERY_REASON,
                    "prior_outcome": "authentication_rejected",
                    "prior_attempt_number": 1,
                },
                separators=(",", ":"),
            )
            for (job_id,) in targets:
                connection.execute(
                    """INSERT INTO uec.geocode_job_events
                           (job_id,event_type,attempt_number,retryable,details)
                       VALUES (%s,'queued',2,false,%s)""",
                    (job_id, details),
                )
            return {
                "budget_date": str(budget_date),
                "remaining_budget": remaining,
                "requeued": len(targets),
            }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.environ.get("UEC_DATABASE_URL"))
    parser.add_argument("--limit", type=int, required=True, help="Maximum current-snapshot targets; use 1 for the first validation")
    parser.add_argument(
        "--confirm-key-verified",
        action="store_true",
        required=True,
        help="Confirm the corrected User key was independently verified outside this command",
    )
    args = parser.parse_args()
    if not args.database_url:
        print("requeue_blocked: UEC_DATABASE_URL is not configured", file=sys.stderr)
        return 2
    try:
        result = requeue(
            args.database_url,
            args.limit,
            key_configured=bool(os.environ.get("GEOAPIFY_API_KEY", "").strip()),
            key_verified=args.confirm_key_verified,
        )
    except Exception as error:
        print(f"requeue_blocked: {type(error).__name__}; no provider calls made", file=sys.stderr)
        return 1
    print(
        f"provider=geoapify source={SOURCE_ID} budget_date={result['budget_date']} "
        f"remaining_budget={result['remaining_budget']} requeued={result['requeued']} provider_calls=0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
