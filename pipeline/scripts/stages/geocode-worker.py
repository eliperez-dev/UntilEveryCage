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


def run(database_url: str, provider_id: str, limit: int | None, delay: float, retries: int) -> int:
    adapter = get_adapter(provider_id)
    processed = 0
    with psycopg.connect(database_url) as connection:
        while limit is None or processed < limit:
            job = connection.execute("""
                SELECT job.job_id, job.source_record_id, job.provider_id, job.query, COALESCE(current.attempt_number, 0)
                FROM uec.geocode_jobs AS job
                LEFT JOIN uec.geocode_job_current AS current ON current.job_id = job.job_id
                WHERE job.provider_id = %s
                  AND (current.event_type IS NULL OR current.event_type = 'queued' OR (current.event_type = 'failed' AND current.retryable))
                  AND NOT EXISTS (
                      SELECT 1 FROM uec.public_access_restricted restricted
                      WHERE restricted.source_record_id = job.source_record_id
                  )
                ORDER BY job.created_at, job.job_id LIMIT 1
            """, (provider_id,)).fetchone()
            if not job:
                break
            job_id, source_record_id, _, query, prior_attempt = job
            attempt = prior_attempt + 1
            with connection.transaction():
                connection.execute("INSERT INTO uec.geocode_job_events (job_id, event_type, attempt_number, occurred_at) VALUES (%s, 'started', %s, %s)", (job_id, attempt, datetime.now(timezone.utc)))
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
                connection.execute("""
                    INSERT INTO uec.geocode_results (geocode_result_id, source_record_id, provider_id, query, provider_address_id, result, precision, match_method, status, attempt_number, retryable, response, queried_at)
                    VALUES (%s, %s, %s, %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (geocode_result_id) DO NOTHING
                """, (result_id, source_record_id, provider_id, query, outcome.provider_address_id, outcome.longitude, outcome.latitude, outcome.precision, outcome.match_method, outcome.status, attempt, outcome.retryable, json.dumps(outcome.response, ensure_ascii=False), queried_at))
                connection.execute("INSERT INTO uec.geocode_job_events (job_id, event_type, attempt_number, retryable, details, occurred_at) VALUES (%s, %s, %s, %s, %s, %s)", (job_id, outcome.status, attempt, outcome.retryable, json.dumps({"acceptance": outcome.acceptance}, ensure_ascii=False), queried_at))
            processed += 1
            print(f"job={job_id} attempt={attempt} status={outcome.status}", flush=True)
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
    args = parser.parse_args()
    print(f"Processed {run(args.database_url, args.provider, args.limit, args.delay, args.retries)} geocoding jobs")
