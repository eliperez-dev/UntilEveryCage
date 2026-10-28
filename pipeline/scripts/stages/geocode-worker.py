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
from pipeline.geocoding.private_profiles import profile_by_id
from pipeline.geocoding.accounts import account_for_provider

AU_NPI_AUTH_REQUEUE_REASON = "operator_authorized_geoapify_key_recovery"


def _claim_job(
    connection,
    provider_id: str,
    worker_id: str,
    max_attempts: int,
    lease_timeout: int,
    au_npi_pilot: bool = False,
    au_npi_auth_recovery: bool = False,
    private_source_profile_id: str | None = None,
    job_ids: tuple[uuid.UUID, ...] | None = None,
    _claim_retries: int = 8,
):
    stale_claim = False
    with connection.transaction():
        job = connection.execute("""
            SELECT job.job_id, job.source_record_id, job.query,
                   COALESCE(current.attempt_number, 0), current.event_type
            FROM uec.geocode_jobs AS job
            JOIN LATERAL (
                SELECT event.event_type, event.attempt_number, event.retryable,
                       event.details, event.occurred_at, event.next_attempt_at
                  FROM uec.geocode_job_events AS event
                 WHERE event.job_id = job.job_id
                 ORDER BY event.occurred_at DESC, event.event_id DESC
                 LIMIT 1
            ) AS current ON TRUE
            WHERE job.provider_id = %s
              AND (
                    COALESCE(current.attempt_number, 0) < %s
                    OR (%s::boolean AND NOT %s::boolean
                        AND current.event_type = 'queued' AND current.attempt_number = 1)
                    OR (%s::boolean AND current.event_type = 'queued'
                        AND current.attempt_number = 2
                        AND current.details->>'recovery_reason' = 'operator_authorized_geoapify_key_recovery')
              )
              AND (
                    (NOT %s::boolean AND current.event_type IS NULL)
                    OR (current.event_type = 'queued' AND (
                        NOT %s::boolean
                        OR (current.attempt_number = 2
                            AND current.details->>'recovery_reason' = 'operator_authorized_geoapify_key_recovery')
                    ))
                    OR (NOT %s::boolean AND (
                        (current.event_type = 'failed' AND current.retryable
                         AND (current.next_attempt_at IS NULL OR current.next_attempt_at <= now()))
                        OR (current.event_type = 'started'
                            AND current.occurred_at < now() - (%s * interval '1 second'))
                    ))
              )
              AND NOT EXISTS (
                  SELECT 1 FROM uec.public_access_restricted restricted
                  WHERE restricted.source_record_id = job.source_record_id
              )
              AND (
                    NOT %s::boolean
                    OR EXISTS (
                        SELECT 1
                        FROM real_preview.geocode_targets target
                        JOIN real_preview.candidates candidate ON candidate.candidate_id=target.candidate_id
                        WHERE target.job_id=job.job_id
                          AND target.source_id='au.npi.facilities'
                          AND candidate.source_id='au.npi.facilities'
                          AND candidate.country_code='AU'
                          AND candidate.location_class='city_postal'
                          AND target.snapshot_sha256=candidate.snapshot_sha256
                          AND candidate.snapshot_sha256=COALESCE(
                              (SELECT run.snapshot_sha256 FROM real_preview.source_preview_runs run
                               WHERE run.source_id='au.npi.facilities'
                               ORDER BY run.created_at DESC,run.run_id DESC LIMIT 1),
                              (SELECT manifest.snapshot_sha256 FROM real_preview.source_manifests manifest
                               WHERE manifest.source_id='au.npi.facilities'
                               ORDER BY manifest.retrieved_at DESC,manifest.snapshot_sha256 DESC LIMIT 1)
                          )
                    )
              )
              AND (
                    %s::text IS NULL OR EXISTS (
                        SELECT 1
                        FROM real_preview.geocode_targets target
                        JOIN real_preview.candidates candidate ON candidate.candidate_id=target.candidate_id
                        JOIN uec.geocode_job_events queued ON queued.job_id=job.job_id
                          AND queued.event_type='queued'
                          AND queued.details->>'processing_mode' IN (
                              'private_geoapify_source_profile', 'private_locationiq_source_profile')
                          AND queued.details->>'profile_id'=%s
                        WHERE target.job_id=job.job_id
                          AND target.source_id=%s AND candidate.source_id=%s
                          AND candidate.country_code=%s
                          AND target.snapshot_sha256=candidate.snapshot_sha256
                          AND NOT EXISTS (
                              SELECT 1 FROM real_preview.geocode_display_evidence evidence
                              JOIN uec.geocode_results result USING (geocode_result_id)
                              WHERE evidence.candidate_id=candidate.candidate_id
                                AND result.status='accepted' AND result.provider_id<>job.provider_id
                                AND evidence.display_precision='provider_address_point_high_confidence'
                                AND evidence.display_latitude=candidate.display_latitude
                                AND evidence.display_longitude=candidate.display_longitude
                                AND evidence.display_geometry_source=candidate.display_geometry_source
                          )
                          AND candidate.snapshot_sha256=COALESCE(
                              (SELECT run.snapshot_sha256 FROM real_preview.source_preview_runs run
                               WHERE run.source_id=%s
                               ORDER BY run.created_at DESC,run.run_id DESC LIMIT 1),
                              (SELECT manifest.snapshot_sha256 FROM real_preview.source_manifests manifest
                               WHERE manifest.source_id=%s
                               ORDER BY manifest.retrieved_at DESC,manifest.snapshot_sha256 DESC LIMIT 1)
                          )
                    )
              )
              AND (%s::uuid[] IS NULL OR job.job_id = ANY(%s::uuid[]))
            ORDER BY job.created_at, job.job_id
            FOR UPDATE OF job SKIP LOCKED
            LIMIT 1
        """, (
            provider_id, max_attempts, au_npi_pilot, au_npi_auth_recovery,
            au_npi_auth_recovery, au_npi_pilot, au_npi_auth_recovery,
            au_npi_pilot, lease_timeout, au_npi_pilot,
            private_source_profile_id, private_source_profile_id,
            profile_by_id(private_source_profile_id)["source_id"] if private_source_profile_id else None,
            profile_by_id(private_source_profile_id)["source_id"] if private_source_profile_id else None,
            profile_by_id(private_source_profile_id)["country_code"] if private_source_profile_id else None,
            profile_by_id(private_source_profile_id)["source_id"] if private_source_profile_id else None,
            profile_by_id(private_source_profile_id)["source_id"] if private_source_profile_id else None,
            list(job_ids) if job_ids is not None else None,
            list(job_ids) if job_ids is not None else None,
        )).fetchone()
        if not job:
            return None
        job_id, source_record_id, query, prior_attempt, prior_event_type = job
        # The candidate query joins a view whose snapshot can predate another
        # worker's just-committed started event.  The job row is now locked, so
        # a direct current-event read is both fresh and stable through our
        # started-event insert.  Never let a stale candidate reserve the same
        # job/attempt twice.
        current = connection.execute("""
            SELECT event_type, attempt_number
              FROM uec.geocode_job_events
             WHERE job_id = %s
             ORDER BY occurred_at DESC, event_id DESC
             LIMIT 1
        """, (job_id,)).fetchone()
        if current != (prior_event_type, prior_attempt):
            stale_claim = True
        else:
            # Queue events use attempt_number=1 in the existing event contract.
            # Queue attempt 1 is the initial pilot state. The opt-in recovery event
            # is explicitly queued at attempt 2 and consumes a distinct reservation.
            attempt = prior_attempt if au_npi_pilot and prior_event_type == "queued" else prior_attempt + 1
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
            return job_id, source_record_id, query, attempt, lease_token, prior_event_type
    if stale_claim and _claim_retries > 1:
        return _claim_job(
            connection, provider_id, worker_id, max_attempts, lease_timeout,
            au_npi_pilot, au_npi_auth_recovery, private_source_profile_id,
            job_ids,
            _claim_retries - 1,
        )
    return None


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
    au_npi_pilot: bool = False,
    provider_account: str | None = None,
):
    """Commit one shared provider/day reservation before outbound work.

    The budget row is locked by the UPDATE. A failed UPDATE means either the
    allowance or the shared rate interval is exhausted; no provider call may
    happen in that case.
    """
    with connection.transaction():
        if provider_id == "locationiq":
            return connection.execute("""SELECT reservation_id,reason
                FROM uec.reserve_geocode_account_request(%s,%s,%s,%s,%s,%s,%s)""",
                (provider_id,account_for_provider(provider_id,provider_account),job_id,
                 attempt,retry_number,daily_budget,provider_interval)).fetchone()
        today = connection.execute("SELECT (now() AT TIME ZONE 'UTC')::date").fetchone()[0]
        connection.execute("""
            INSERT INTO uec.geocode_provider_budgets
                (provider_id, budget_date, daily_limit)
            VALUES (%s, %s, %s)
            ON CONFLICT (provider_id, budget_date) DO UPDATE
                SET daily_limit = CASE WHEN %s
                    THEN LEAST(uec.geocode_provider_budgets.daily_limit, EXCLUDED.daily_limit)
                    ELSE uec.geocode_provider_budgets.daily_limit END
        """, (provider_id, today, daily_budget, au_npi_pilot))
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
    au_npi_pilot: bool = False,
    au_npi_auth_recovery: bool = False,
    private_source_profile_id: str | None = None,
    job_ids: tuple[uuid.UUID, ...] | None = None,
    provider_account: str | None = None,
) -> int:
    selected_account = account_for_provider(provider_id,provider_account)
    if daily_budget < 1 or max_attempts < 1 or lease_timeout < 1 or retries < 1 or provider_interval < 0:
        raise ValueError("budgets, attempts, lease timeout, retries, and provider interval must be valid")
    if au_npi_pilot and provider_id != "geoapify":
        raise ValueError("AU NPI pilot requires Geoapify")
    if au_npi_auth_recovery and not au_npi_pilot:
        raise ValueError("AU NPI authentication recovery requires the explicit pilot mode")
    if private_source_profile_id and (au_npi_pilot or au_npi_auth_recovery):
        raise ValueError("private source profile mode is separate from the AU pilot")
    if private_source_profile_id:
        profile = profile_by_id(private_source_profile_id)
        if profile is None or profile.get("provider_id", "geoapify") != provider_id:
            raise ValueError("enabled private source profile for this provider required")
    if provider_id == "locationiq" and (
            private_source_profile_id not in {
                "locationiq-de-bltu", "locationiq-nz-mpi-rmp",
                "locationiq-gb-fsa-approved-establishments", "locationiq-gb-fss-approved-establishments",
                "locationiq-es-aesan-rgseaa", "locationiq-es-cat-feed-sandach",
            } or limit is None
            or limit > 5000 or daily_budget > 5000 or provider_interval < 1.05):
        raise ValueError("LocationIQ requires an allowlisted country profile, a finite limit and free-plan rate/quota bounds")
    if job_ids is not None:
        if not job_ids or len(set(job_ids)) != len(job_ids) or any(not isinstance(value, uuid.UUID) for value in job_ids):
            raise ValueError("job_ids must be a non-empty sequence of unique UUIDs")
        if limit is None or limit > len(job_ids):
            raise ValueError("job_ids require a finite limit no larger than the allowlist")
    if au_npi_pilot and (
        limit is None or limit > 24 or provider_interval < 1.0 or retries > 1
        or max_attempts != (2 if au_npi_auth_recovery else 1)
    ):
        raise ValueError("AU NPI pilot is bounded to 24 jobs per invocation, one shared request per second, and one attempt per job except explicit auth recovery")
    adapter_options = {"provider_account": selected_account} if selected_account else {}
    adapter = get_adapter(provider_id, au_npi_pilot=au_npi_pilot,
                          private_source_profile_id=private_source_profile_id, **adapter_options)
    worker_id = worker_id or f"geocoder-{uuid.uuid4().hex[:12]}"
    processed = 0
    # Every state transition below has an explicit transaction block.  Keep
    # the connection itself in autocommit mode so read checks cannot retain an
    # implicit transaction (and a provider-budget row lock) across HTTP work.
    with psycopg.connect(database_url, autocommit=True) as connection:
        while limit is None or processed < limit:
            job = _claim_job(
                connection, provider_id, worker_id, max_attempts, lease_timeout,
                au_npi_pilot, au_npi_auth_recovery,
                private_source_profile_id,
                job_ids,
            )
            if not job:
                break
            job_id, source_record_id, query, attempt, lease_token, _prior_event_type = job
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
                    daily_budget, provider_interval, au_npi_pilot,
                    **({"provider_account": selected_account} if selected_account else {}),
                )
                # Contending workers retain their lease and wait for the
                # shared admission slot.  Rate-slot waiting is neither a
                # provider call nor an attempt/retry, so it must not strand a
                # job by recording a retryable terminal event.
                while reservation_id is None and reservation_reason == "rate_limited":
                    time.sleep(max(provider_interval, 0.1))
                    if _is_restricted(connection, source_record_id):
                        status = _finish_restricted(connection, job_id, attempt, worker_id, lease_token)
                        break
                    reservation_id, reservation_reason = _reserve_request(
                        connection, provider_id, job_id, attempt, retry_number,
                        daily_budget, provider_interval, au_npi_pilot,
                        **({"provider_account": selected_account} if selected_account else {}),
                    )
                if status == "cancelled_restricted":
                    break
                if reservation_id is None:
                    if reservation_reason == "budget":
                        status = _defer_job(
                            connection, job_id, attempt, worker_id, lease_token,
                            "request_budget_exhausted", 86400,
                        )
                        budget_blocked = True
                    else:
                        raise RuntimeError("provider_reservation_state_invalid")
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
            if outcome is not None and outcome.acceptance in {
                    "authentication_rejected", "provider_rate_limited"}:
                break
            if limit is None or processed < limit:
                time.sleep(delay)
    return processed


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.environ.get("UEC_DATABASE_URL", "postgresql://uec:uec-local-development-only@localhost:5433/uec"))
    parser.add_argument("--provider", default="dawa")
    parser.add_argument("--provider-account", choices=("primary", "secondary"),
                        help="LocationIQ account alias; chooses its separate quota and private key")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--daily-budget", type=int, default=2800)
    parser.add_argument("--max-attempts", type=int, default=5)
    parser.add_argument("--lease-timeout", type=int, default=900, help="Seconds before an abandoned started event can be reclaimed")
    parser.add_argument("--provider-interval", type=float, default=1.0, help="Minimum shared seconds between provider reservations")
    parser.add_argument("--au-npi-pilot", action="store_true", help="Enable only the bounded AU NPI Geoapify matching/display policy")
    parser.add_argument("--au-npi-auth-recovery", action="store_true", help="Permit only queued attempt-2 events carrying the explicit AU NPI authentication recovery marker")
    parser.add_argument("--private-source-profile", help="Explicitly process only the named enabled private provider/source profile")
    parser.add_argument("--job-id", action="append", help="Optional exact job UUID allowlist; repeat to select multiple jobs")
    parser.add_argument("--worker-id", default=os.environ.get("UEC_GEOCODE_WORKER_ID"))
    args = parser.parse_args()
    count = run(
        args.database_url, args.provider, args.limit, args.delay, args.retries,
        daily_budget=args.daily_budget, max_attempts=args.max_attempts,
        lease_timeout=args.lease_timeout, provider_interval=args.provider_interval,
        worker_id=args.worker_id, au_npi_pilot=args.au_npi_pilot,
        au_npi_auth_recovery=args.au_npi_auth_recovery,
        private_source_profile_id=args.private_source_profile,
        job_ids=tuple(uuid.UUID(value) for value in args.job_id) if args.job_id else None,
        provider_account=args.provider_account,
    )
    print(f"provider={args.provider} status=complete processed={count}")
