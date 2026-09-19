#!/usr/bin/env python3
"""Run a provider-independent, append-only database geocoding worker.

Claims, request reservations, and outcomes are separate short transactions.
The worker never keeps a database transaction open while calling a provider.
"""

import argparse
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from pipeline.geocoding.registry import get_adapter
from pipeline.geocoding.base import GeocodeOutcome


def _claim_job(connection, provider_id: str, worker_id: str, max_attempts: int, lease_timeout: int):
    with connection.transaction():
        job = connection.execute("""
            SELECT job.job_id, job.source_record_id, job.query,
                   COALESCE(current.attempt_number, 0)
            FROM uec.geocode_jobs AS job
            LEFT JOIN uec.geocode_job_current AS current ON current.job_id = job.job_id
            WHERE job.provider_id = %s
              AND COALESCE(current.attempt_number, 0) < %s
              AND (
                    current.event_type IS NULL
                    OR current.event_type = 'queued'
                    OR (current.event_type = 'failed' AND current.retryable
                        AND (current.next_attempt_at IS NULL OR current.next_attempt_at <= now()))
                    OR (current.event_type = 'started'
                        AND current.occurred_at < now() - (%s * interval '1 second'))
              )
              AND NOT EXISTS (
                  SELECT 1 FROM uec.public_access_restricted restricted
                  WHERE restricted.source_record_id = job.source_record_id
              )
            ORDER BY job.created_at, job.job_id
            FOR UPDATE OF job SKIP LOCKED
            LIMIT 1
        """, (provider_id, max_attempts, lease_timeout)).fetchone()
        if not job:
            return None
        job_id, source_record_id, query, prior_attempt = job
        attempt = prior_attempt + 1
        lease_token = uuid.uuid4()
        connection.execute("""
            INSERT INTO uec.geocode_job_events
                (job_id, event_type, attempt_number, worker_id, lease_token, details, occurred_at)
            VALUES (%s, 'started', %s, %s, %s, %s, %s)
        """, (
            job_id, attempt, worker_id, lease_token,
            json.dumps({"lease_timeout_seconds": lease_timeout}),
            datetime.now(timezone.utc),
        ))
        return job_id, source_record_id, query, attempt, lease_token


def _is_restricted(connection, source_record_id) -> bool:
    with connection.transaction():
        return connection.execute("""
            SELECT EXISTS (
                SELECT 1 FROM uec.public_access_restricted
                WHERE source_record_id = %s
            )
        """, (source_record_id,)).fetchone()[0]


def _reserve_request(
    connection,
    provider_id: str,
    job_id,
    attempt: int,
    retry_number: int,
    daily_budget: int,
    provider_interval: float,
):
    """Commit one shared provider/day reservation before outbound work.

    The budget row is locked by the UPDATE. A failed UPDATE means either the
    allowance or the shared rate interval is exhausted; no provider call may
    happen in that case.
    """
    with connection.transaction():
        today = connection.execute("SELECT (now() AT TIME ZONE 'UTC')::date").fetchone()[0]
        connection.execute("""
            INSERT INTO uec.geocode_provider_budgets
                (provider_id, budget_date, daily_limit)
            VALUES (%s, %s, %s)
            ON CONFLICT (provider_id, budget_date) DO NOTHING
        """, (provider_id, today, daily_budget))
        row = connection.execute("""
            UPDATE uec.geocode_provider_budgets
               SET reserved_requests = reserved_requests + 1,
                   last_reserved_at = clock_timestamp()
             WHERE provider_id = %s
               AND budget_date = %s
               AND reserved_requests < daily_limit
               AND (
                   %s <= 0
                   OR last_reserved_at IS NULL
                   OR last_reserved_at <= clock_timestamp() - (%s * interval '1 second')
               )
         RETURNING budget_date
        """, (provider_id, today, provider_interval, provider_interval)).fetchone()
        if not row:
            state = connection.execute("""
                SELECT reserved_requests >= daily_limit
                  FROM uec.geocode_provider_budgets
                 WHERE provider_id = %s AND budget_date = %s
            """, (provider_id, today)).fetchone()
            return None, ("budget" if state and state[0] else "rate_limited")
        reservation_id = uuid.uuid4()
        connection.execute("""
            INSERT INTO uec.geocode_request_reservations
                (reservation_id, provider_id, budget_date, job_id,
                 attempt_number, retry_number)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (reservation_id, provider_id, today, job_id, attempt, retry_number))
        return reservation_id, None


def _current_lease(connection, job_id):
    # Claim and completion transactions serialize on the immutable job row.
    # Locking only the latest event would allow a superseding claim to race
    # between the lease check and result insertion.
    connection.execute(
        "SELECT job_id FROM uec.geocode_jobs WHERE job_id = %s FOR UPDATE",
        (job_id,),
    )
    return connection.execute("""
        SELECT event_type, worker_id, lease_token
          FROM uec.geocode_job_events
         WHERE job_id = %s
         ORDER BY occurred_at DESC, event_id DESC
         LIMIT 1
         FOR UPDATE
    """, (job_id,)).fetchone()


def _finish_restricted(connection, job_id, attempt, worker_id, lease_token) -> str:
    with connection.transaction():
        current = _current_lease(connection, job_id)
        if not current or current[0] != "started" or current[1] != worker_id or current[2] != lease_token:
            return "stale_lease"
        connection.execute("""
            INSERT INTO uec.geocode_job_events
                (job_id, event_type, attempt_number, retryable, worker_id,
                 lease_token, details, occurred_at)
            VALUES (%s, 'cancelled', %s, false, %s, %s, %s, %s)
        """, (job_id, attempt, worker_id, lease_token,
               json.dumps({"reason": "restricted_before_provider"}), datetime.now(timezone.utc)))
        return "cancelled_restricted"


def _defer_job(connection, job_id, attempt, worker_id, lease_token, reason: str, delay_seconds: float) -> str:
    """Record a retryable deferred terminal event without making a provider call."""
    delay_seconds = max(delay_seconds, 0.1)
    with connection.transaction():
        current = _current_lease(connection, job_id)
        if not current or current[0] != "started" or current[1] != worker_id or current[2] != lease_token:
            return "stale_lease"
        connection.execute("""
            INSERT INTO uec.geocode_job_events
                (job_id, event_type, attempt_number, retryable, worker_id,
                 lease_token, details, next_attempt_at, occurred_at)
            VALUES (%s, 'failed', %s, true, %s, %s, %s,
                    now() + (%s * interval '1 second'), %s)
        """, (
            job_id, attempt, worker_id, lease_token,
            json.dumps({"reason": reason}), delay_seconds, datetime.now(timezone.utc),
        ))
        return "deferred"


def _persist_outcome(
    connection,
    job_id,
    source_record_id,
    provider_id: str,
    query: str,
    attempt: int,
    worker_id: str,
    lease_token,
    outcome: GeocodeOutcome,
) -> str:
    """Persist one result only while this worker still owns the lease."""
    with connection.transaction():
        current = _current_lease(connection, job_id)
        if not current or current[0] != "started" or current[1] != worker_id or current[2] != lease_token:
            return "stale_lease"
        if connection.execute("""
            SELECT EXISTS (
                SELECT 1 FROM uec.public_access_restricted
                WHERE source_record_id = %s
            )
        """, (source_record_id,)).fetchone()[0]:
            connection.execute("""
                INSERT INTO uec.geocode_job_events
                    (job_id, event_type, attempt_number, retryable, worker_id,
                     lease_token, details, occurred_at)
                VALUES (%s, 'cancelled', %s, false, %s, %s, %s, %s)
            """, (job_id, attempt, worker_id, lease_token,
                   json.dumps({"reason": "restricted_during_attempt"}), datetime.now(timezone.utc)))
            return "cancelled_restricted"
        queried_at = datetime.now(timezone.utc)
        result_id = uuid.uuid5(uuid.NAMESPACE_URL, f"urn:uec:geocode:{job_id}:{attempt}")
        connection.execute("""
            INSERT INTO uec.geocode_results
                (geocode_result_id, source_record_id, provider_id, query,
                 provider_address_id, result, precision, match_method, status,
                 attempt_number, retryable, response, queried_at)
            VALUES (%s, %s, %s, %s, %s,
                    CASE WHEN %s::double precision IS NULL OR %s::double precision IS NULL THEN NULL
                         ELSE ST_SetSRID(ST_MakePoint(%s::double precision, %s::double precision), 4326)::geography END,
                    %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (geocode_result_id) DO NOTHING
        """, (
            result_id, source_record_id, provider_id, query,
            outcome.provider_address_id, outcome.longitude, outcome.latitude,
            outcome.longitude, outcome.latitude, outcome.precision,
            outcome.match_method, outcome.status, attempt, outcome.retryable,
            json.dumps(outcome.response, ensure_ascii=False), queried_at,
        ))
        connection.execute("""
            INSERT INTO uec.geocode_job_events
                (job_id, event_type, attempt_number, retryable, worker_id,
                 lease_token, details, occurred_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (job_id, outcome.status, attempt, outcome.retryable, worker_id,
               lease_token, json.dumps({"acceptance": outcome.acceptance}, ensure_ascii=False), queried_at))
        return outcome.status


def run(
    database_url: str,
    provider_id: str,
    limit: int | None,
    delay: float,
    retries: int,
    *,
    daily_budget: int = 2800,
    max_attempts: int = 5,
    lease_timeout: int = 900,
    provider_interval: float = 1.0,
    worker_id: str | None = None,
) -> int:
    if daily_budget < 1 or max_attempts < 1 or lease_timeout < 1 or retries < 1 or provider_interval < 0:
        raise ValueError("budgets, attempts, lease timeout, retries, and provider interval must be valid")
    adapter = get_adapter(provider_id)
    worker_id = worker_id or f"geocoder-{uuid.uuid4().hex[:12]}"
    processed = 0
    with psycopg.connect(database_url) as connection:
        while limit is None or processed < limit:
            job = _claim_job(connection, provider_id, worker_id, max_attempts, lease_timeout)
            if not job:
                break
            job_id, source_record_id, query, attempt, lease_token = job
            if _is_restricted(connection, source_record_id):
                status = _finish_restricted(connection, job_id, attempt, worker_id, lease_token)
                if status != "stale_lease":
                    processed += 1
                    print(f"provider={provider_id} status={status} processed={processed}", flush=True)
                continue
            outcome = None
            status = "running"
            budget_blocked = False
            retry_number = 1
            while retry_number <= retries:
                if _is_restricted(connection, source_record_id):
                    outcome = None
                    status = _finish_restricted(connection, job_id, attempt, worker_id, lease_token)
                    break
                reservation_id, reservation_reason = _reserve_request(
                    connection, provider_id, job_id, attempt, retry_number,
                    daily_budget, provider_interval,
                )
                if reservation_id is None:
                    if reservation_reason == "rate_limited":
                        status = _defer_job(
                            connection, job_id, attempt, worker_id, lease_token,
                            "provider_rate_limited", max(provider_interval, 0.1),
                        )
                    else:
                        status = _defer_job(
                            connection, job_id, attempt, worker_id, lease_token,
                            "request_budget_exhausted", 86400,
                        )
                        budget_blocked = True
                    break
                # Restrictions can be added while the reservation transaction is
                # committing; recheck immediately before the external call.
                if _is_restricted(connection, source_record_id):
                    status = _finish_restricted(connection, job_id, attempt, worker_id, lease_token)
                    break
                try:
                    outcome = adapter.geocode(query)
                except Exception as error:  # provider details remain redacted
                    outcome = GeocodeOutcome(
                        "failed", "provider_exception", None, None, None, None,
                        "provider_exception", True, {"error": type(error).__name__},
                    )
                if not outcome.retryable or retry_number == retries:
                    break
                time.sleep(max(delay * retry_number, provider_interval))
                retry_number += 1
            if budget_blocked:
                print(f"provider={provider_id} status={status} processed={processed}", flush=True)
                break
            if outcome is not None and status not in ("stale_lease", "cancelled_restricted"):
                status = _persist_outcome(
                    connection, job_id, source_record_id, provider_id, query,
                    attempt, worker_id, lease_token, outcome,
                )
            if status == "stale_lease":
                print(f"provider={provider_id} status=stale_lease processed={processed}", flush=True)
                continue
            processed += 1
            print(f"provider={provider_id} status={status} processed={processed}", flush=True)
            if limit is None or processed < limit:
                time.sleep(delay)
    return processed


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.environ.get("UEC_DATABASE_URL", "postgresql://uec:uec-local-development-only@localhost:5433/uec"))
    parser.add_argument("--provider", default="dawa")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--daily-budget", type=int, default=2800)
    parser.add_argument("--max-attempts", type=int, default=5)
    parser.add_argument("--lease-timeout", type=int, default=900, help="Seconds before an abandoned started event can be reclaimed")
    parser.add_argument("--provider-interval", type=float, default=1.0, help="Minimum shared seconds between provider reservations")
    parser.add_argument("--worker-id", default=os.environ.get("UEC_GEOCODE_WORKER_ID"))
    args = parser.parse_args()
    count = run(
        args.database_url, args.provider, args.limit, args.delay, args.retries,
        daily_budget=args.daily_budget, max_attempts=args.max_attempts,
        lease_timeout=args.lease_timeout, provider_interval=args.provider_interval,
        worker_id=args.worker_id,
    )
    print(f"provider={args.provider} status=complete processed={count}")
