#!/usr/bin/env python3
"""Run a provider-independent, append-only database geocoding worker."""

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


def _daily_started(connection, provider_id: str) -> int:
    return connection.execute("""
        SELECT count(*)
        FROM uec.geocode_job_events event
        JOIN uec.geocode_jobs job ON job.job_id = event.job_id
        WHERE job.provider_id = %s
          AND event.event_type = 'started'
          AND event.occurred_at >= date_trunc('day', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'
    """, (provider_id,)).fetchone()[0]


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
                    OR (current.event_type = 'failed' AND current.retryable)
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
        connection.execute("""
            INSERT INTO uec.geocode_job_events
                (job_id, event_type, attempt_number, worker_id, details, occurred_at)
            VALUES (%s, 'started', %s, %s, %s, %s)
        """, (
            job_id, attempt, worker_id,
            json.dumps({"lease_timeout_seconds": lease_timeout}),
            datetime.now(timezone.utc),
        ))
        return job_id, source_record_id, query, attempt


def _is_restricted(connection, source_record_id) -> bool:
    return connection.execute("""
        SELECT EXISTS (
            SELECT 1 FROM uec.public_access_restricted
            WHERE source_record_id = %s
        )
    """, (source_record_id,)).fetchone()[0]


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
    worker_id: str | None = None,
) -> int:
    if daily_budget < 1 or max_attempts < 1 or lease_timeout < 1 or retries < 1:
        raise ValueError("budgets, attempts, lease timeout, and retries must be positive")
    adapter = get_adapter(provider_id)
    worker_id = worker_id or f"geocoder-{uuid.uuid4().hex[:12]}"
    processed = 0
    with psycopg.connect(database_url) as connection:
        while limit is None or processed < limit:
            if _daily_started(connection, provider_id) >= daily_budget:
                print(f"provider={provider_id} status=daily_budget_reached processed={processed}", flush=True)
                break
            job = _claim_job(connection, provider_id, worker_id, max_attempts, lease_timeout)
            if not job:
                break
            job_id, source_record_id, query, attempt = job
            outcome = None
            for retry in range(retries):
                outcome = adapter.geocode(query)
                if not outcome.retryable or retry == retries - 1:
                    break
                time.sleep(delay * (retry + 1))
            assert outcome is not None
            queried_at = datetime.now(timezone.utc)
            result_id = uuid.uuid5(uuid.NAMESPACE_URL, f"urn:uec:geocode:{job_id}:{attempt}")
            with connection.transaction():
                if _is_restricted(connection, source_record_id):
                    connection.execute("""
                        INSERT INTO uec.geocode_job_events
                            (job_id, event_type, attempt_number, retryable, worker_id, details, occurred_at)
                        VALUES (%s, 'cancelled', %s, false, %s, %s, %s)
                    """, (job_id, attempt, worker_id, json.dumps({"reason": "restricted_during_attempt"}), queried_at))
                    processed += 1
                    print(f"provider={provider_id} status=cancelled_restricted processed={processed}", flush=True)
                    continue
                connection.execute("""
                    INSERT INTO uec.geocode_results (geocode_result_id, source_record_id, provider_id, query, provider_address_id, result, precision, match_method, status, attempt_number, retryable, response, queried_at)
                    VALUES (%s, %s, %s, %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (geocode_result_id) DO NOTHING
                """, (result_id, source_record_id, provider_id, query, outcome.provider_address_id, outcome.longitude, outcome.latitude, outcome.precision, outcome.match_method, outcome.status, attempt, outcome.retryable, json.dumps(outcome.response, ensure_ascii=False), queried_at))
                connection.execute("INSERT INTO uec.geocode_job_events (job_id, event_type, attempt_number, retryable, worker_id, details, occurred_at) VALUES (%s, %s, %s, %s, %s, %s, %s)", (job_id, outcome.status, attempt, outcome.retryable, worker_id, json.dumps({"acceptance": outcome.acceptance}, ensure_ascii=False), queried_at))
            processed += 1
            print(f"provider={provider_id} status={outcome.status} processed={processed}", flush=True)
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
    parser.add_argument("--worker-id", default=os.environ.get("UEC_GEOCODE_WORKER_ID"))
    args = parser.parse_args()
    count = run(
        args.database_url, args.provider, args.limit, args.delay, args.retries,
        daily_budget=args.daily_budget, max_attempts=args.max_attempts,
        lease_timeout=args.lease_timeout, worker_id=args.worker_id,
    )
    print(f"provider={args.provider} status=complete processed={count}")
