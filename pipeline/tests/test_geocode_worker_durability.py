import importlib.util
import unittest
import uuid
from pathlib import Path
from unittest.mock import Mock, patch

from pipeline.geocoding.base import GeocodeOutcome


ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location(
    "geocode_worker_durability", ROOT / "scripts/stages/geocode-worker.py"
)
WORKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(WORKER)

REQUEUE_PATH = ROOT / "scripts/stages/requeue-au-npi-geoapify-auth-failures.py"
REQUEUE_SPEC = importlib.util.spec_from_file_location("requeue_au_npi", REQUEUE_PATH)
REQUEUE = importlib.util.module_from_spec(REQUEUE_SPEC)
REQUEUE_SPEC.loader.exec_module(REQUEUE)


class GeocodeWorkerDurabilityTests(unittest.TestCase):
    def test_private_profile_claim_is_exact_source_country_profile_and_snapshot_scoped(self):
        class Transaction:
            def __enter__(self): return self
            def __exit__(self, *_): return False

        class Cursor:
            def fetchone(self): return None

        class Connection:
            def __init__(self): self.executed = []
            def transaction(self): return Transaction()
            def execute(self, query, params=None):
                self.executed.append((query, params))
                return Cursor()

        connection = Connection()
        result = WORKER._claim_job(
            connection, "geoapify", "synthetic-worker", 3, 900,
            private_source_profile_id="geoapify-gb-fss-approved-establishments",
        )
        self.assertIsNone(result)
        query, params = connection.executed[0]
        self.assertEqual(query.count("%s"), len(params))
        self.assertIn("private_geoapify_source_profile", query)
        self.assertIn("target.source_id=%s AND candidate.source_id=%s", query)
        self.assertIn("candidate.country_code=%s", query)
        self.assertIn("candidate.snapshot_sha256=COALESCE(", query)
        self.assertIn("fss_approved_establishments", params)
        self.assertIn("GB", params)

    def test_au_pilot_requires_explicitly_bounded_worker_options(self):
        for kwargs in (
            {"provider_id": "dawa", "limit": 24, "daily_budget": 24, "max_attempts": 1, "retries": 1, "provider_interval": 1},
            {"provider_id": "geoapify", "limit": None, "daily_budget": 24, "max_attempts": 1, "retries": 1, "provider_interval": 1},
            {"provider_id": "geoapify", "limit": 25, "daily_budget": 24, "max_attempts": 1, "retries": 1, "provider_interval": 1},
            {"provider_id": "geoapify", "limit": 24, "daily_budget": 24, "max_attempts": 2, "retries": 1, "provider_interval": 1},
            {"provider_id": "geoapify", "limit": 24, "daily_budget": 24, "max_attempts": 1, "retries": 2, "provider_interval": 1},
            {"provider_id": "geoapify", "limit": 24, "daily_budget": 24, "max_attempts": 1, "retries": 1, "provider_interval": 0.5},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                WORKER.run(
                    "postgresql://synthetic", kwargs.pop("provider_id"),  # worker validation precedes connection
                    kwargs.pop("limit"), 0, kwargs.pop("retries"),
                    daily_budget=kwargs.pop("daily_budget"),
                    max_attempts=kwargs.pop("max_attempts"),
                    provider_interval=kwargs.pop("provider_interval"),
                    au_npi_pilot=True,
                )
        connection = Mock()
        connection.__enter__ = Mock(return_value=connection)
        connection.__exit__ = Mock(return_value=False)
        with patch.object(WORKER.psycopg, "connect", return_value=connection), \
             patch.object(WORKER, "get_adapter", return_value=Mock()), \
             patch.object(WORKER, "_claim_job", return_value=None):
            self.assertEqual(
                WORKER.run(
                    "postgresql://synthetic", "geoapify", 24, 0, 1,
                    daily_budget=48, max_attempts=2, provider_interval=1,
                    au_npi_pilot=True, au_npi_auth_recovery=True,
                ),
                0,
            )

    def test_au_auth_recovery_claims_only_marked_current_snapshot_attempt_two(self):
        job_id = uuid.uuid4()
        source_record_id = uuid.uuid4()
        lease_token = uuid.uuid4()

        class Cursor:
            def fetchone(self):
                return (job_id, source_record_id, "synthetic query", 2, "queued")

        class Transaction:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

        class Connection:
            def __init__(self):
                self.executed = []

            def transaction(self):
                return Transaction()

            def execute(self, query, params=None):
                self.executed.append((query, params))
                if query.lstrip().startswith("SELECT job.job_id"):
                    return Cursor()
                return Cursor()

        connection = Connection()
        claimed = WORKER._claim_job(
            connection, "geoapify", "synthetic-worker", 2, 900,
            au_npi_pilot=True, au_npi_auth_recovery=True,
        )
        self.assertEqual(claimed[3], 2)
        self.assertEqual(connection.executed[1][1][1], 2)
        claim_sql, claim_params = connection.executed[0]
        self.assertIn("current.attempt_number = 2", claim_sql)
        self.assertIn("current.details->>'recovery_reason' = 'operator_authorized_geoapify_key_recovery'", claim_sql)
        self.assertIn("candidate.snapshot_sha256=COALESCE(", claim_sql)
        self.assertIn("NOT %s::boolean AND (", claim_sql)
        self.assertIn("current.event_type = 'queued' AND (", claim_sql)
        self.assertNotIn("OR (%s::boolean AND current.event_type = 'started'", claim_sql)
        self.assertTrue(claim_params[3])
        self.assertTrue(claim_params[6])

    def test_au_attempt_two_requires_explicit_recovery_mode_and_uses_new_reservation_identity(self):
        connection = Mock()
        connection.__enter__ = Mock(return_value=connection)
        connection.__exit__ = Mock(return_value=False)
        job = (uuid.uuid4(), uuid.uuid4(), "private synthetic query", 2, uuid.uuid4(), "queued")
        adapter = Mock()
        adapter.geocode.return_value = GeocodeOutcome(
            "unresolved", "unresolved", None, None, None, None, "fixture", False, {}
        )
        with patch.object(WORKER.psycopg, "connect", return_value=connection), \
             patch.object(WORKER, "get_adapter", return_value=adapter), \
             patch.object(WORKER, "_claim_job", side_effect=[job, None]), \
             patch.object(WORKER, "_is_restricted", return_value=False), \
             patch.object(WORKER, "_reserve_request", return_value=(uuid.uuid4(), None)) as reserve, \
             patch.object(WORKER, "_persist_outcome", return_value="unresolved"):
            processed = WORKER.run(
                "postgresql://synthetic", "geoapify", 1, 0, 1,
                daily_budget=24, max_attempts=2, provider_interval=1,
                worker_id="synthetic-worker", au_npi_pilot=True,
                au_npi_auth_recovery=True,
            )
        self.assertEqual(processed, 1)
        self.assertEqual(adapter.geocode.call_count, 1)
        self.assertEqual(reserve.call_args.args[3:5], (2, 1))
        durability = (ROOT / "migrations/040_geocode_worker_durability.sql").read_text()
        self.assertIn("UNIQUE (job_id, attempt_number, retry_number)", durability)

    def test_au_recovery_requeue_refuses_exhausted_budget_before_selecting_targets(self):
        connection = Mock()
        connection.__enter__ = Mock(return_value=connection)
        connection.__exit__ = Mock(return_value=False)
        connection.transaction.return_value.__enter__ = Mock(return_value=None)
        connection.transaction.return_value.__exit__ = Mock(return_value=False)
        connection.execute.side_effect = [Mock(fetchone=Mock(return_value=("2026-10-03",))),
                                          Mock(fetchone=Mock(return_value=(24, 24)))]
        with patch.object(REQUEUE.psycopg, "connect", return_value=connection):
            with self.assertRaisesRegex(RuntimeError, "budget"):
                REQUEUE.requeue("postgresql://synthetic", 1, key_configured=True, key_verified=True)
        self.assertEqual(connection.execute.call_count, 2)
        self.assertFalse(any("INSERT INTO uec.geocode_job_events" in call.args[0]
                             for call in connection.execute.call_args_list))

    def test_au_recovery_allows_new_utc_day_without_creating_or_resetting_budget(self):
        connection = Mock()
        connection.__enter__ = Mock(return_value=connection)
        connection.__exit__ = Mock(return_value=False)
        transaction = Mock()
        transaction.__enter__ = Mock(return_value=None)
        transaction.__exit__ = Mock(return_value=False)
        connection.transaction.return_value = transaction
        connection.execute.side_effect = [
            Mock(fetchone=Mock(return_value=("2026-10-04",))),
            Mock(fetchone=Mock(return_value=None)),
            Mock(fetchall=Mock(return_value=[])),
        ]
        with patch.object(REQUEUE.psycopg, "connect", return_value=connection):
            outcome = REQUEUE.requeue(
                "postgresql://synthetic", 1, key_configured=True, key_verified=True
            )
        self.assertEqual(outcome["remaining_budget"], 24)
        self.assertEqual(outcome["requeued"], 0)
        sql_statements = [call.args[0] for call in connection.execute.call_args_list]
        self.assertFalse(any("INSERT INTO uec.geocode_provider_budgets" in sql for sql in sql_statements))

    def test_au_recovery_appends_only_auth_failure_attempt_two_and_never_calls_provider(self):
        connection = Mock()
        connection.__enter__ = Mock(return_value=connection)
        connection.__exit__ = Mock(return_value=False)
        transaction = Mock()
        transaction.__enter__ = Mock(return_value=None)
        transaction.__exit__ = Mock(return_value=False)
        connection.transaction.return_value = transaction
        connection.execute.side_effect = [
            Mock(fetchone=Mock(return_value=("2026-10-04",))),
            Mock(fetchone=Mock(return_value=(48, 24))),
            Mock(fetchall=Mock(return_value=[(uuid.uuid4(),)])),
            Mock(),
        ]
        with patch.object(REQUEUE.psycopg, "connect", return_value=connection):
            outcome = REQUEUE.requeue(
                "postgresql://synthetic", 1, key_configured=True, key_verified=True
            )
        self.assertEqual(outcome["requeued"], 1)
        target_sql = connection.execute.call_args_list[2].args[0]
        self.assertIn("current.event_type='failed'", target_sql)
        self.assertIn("current.attempt_number=1", target_sql)
        self.assertIn("current.retryable=false", target_sql)
        self.assertIn("result.response->>'error'='authentication_rejected'", target_sql)
        self.assertIn("candidate.snapshot_sha256=latest.snapshot_sha256", target_sql)
        insert_sql, insert_params = connection.execute.call_args_list[3].args
        self.assertIn("VALUES (%s,'queued',2,false,%s)", insert_sql)
        self.assertIn(REQUEUE.RECOVERY_REASON, insert_params[1])

    def test_au_recovery_requeue_requires_explicit_verified_key(self):
        for configured, verified in ((False, True), (True, False)):
            with self.subTest(configured=configured, verified=verified):
                with self.assertRaises(ValueError):
                    REQUEUE.requeue(
                        "postgresql://synthetic", 1,
                        key_configured=configured, key_verified=verified,
                    )

    def test_migration_adds_lease_fence_and_atomic_request_ledger(self):
        migration = (ROOT / "migrations/040_geocode_worker_durability.sql").read_text()
        for required in (
            "lease_token UUID",
            "next_attempt_at TIMESTAMPTZ",
            "geocode_provider_budgets",
            "reserved_requests",
            "geocode_request_reservations",
            "geocode_request_reservations_append_only",
        ):
            self.assertIn(required, migration)

    def test_retryable_provider_attempts_each_consume_a_reservation(self):
        connection = Mock()
        connection.__enter__ = Mock(return_value=connection)
        connection.__exit__ = Mock(return_value=False)
        job = (uuid.uuid4(), uuid.uuid4(), "private synthetic query", 1, uuid.uuid4(), "queued")
        reservations = [(uuid.uuid4(), None), (uuid.uuid4(), None)]
        adapter = Mock()
        adapter.geocode.side_effect = [
            GeocodeOutcome("failed", "temporary", None, None, None, None, "fixture", True, {"error": "temporary"}),
            GeocodeOutcome("unresolved", "unresolved", None, None, None, None, "fixture", False, {}),
        ]
        with patch.object(WORKER.psycopg, "connect", return_value=connection), \
             patch.object(WORKER, "get_adapter", return_value=adapter), \
             patch.object(WORKER, "_claim_job", side_effect=[job, None]), \
             patch.object(WORKER, "_is_restricted", return_value=False), \
             patch.object(WORKER, "_reserve_request", side_effect=reservations) as reserve, \
             patch.object(WORKER, "_persist_outcome", return_value="unresolved") as persist:
            processed = WORKER.run(
                "postgresql://synthetic", "fixture", 1, 0, 2,
                daily_budget=2, provider_interval=0, worker_id="synthetic-worker",
            )
        self.assertEqual(processed, 1)
        self.assertEqual(adapter.geocode.call_count, 2)
        self.assertEqual(reserve.call_count, 2)
        persist.assert_called_once()

    def test_stale_result_is_counted_without_persisting_payload(self):
        connection = Mock()
        connection.__enter__ = Mock(return_value=connection)
        connection.__exit__ = Mock(return_value=False)
        job = (uuid.uuid4(), uuid.uuid4(), "private synthetic query", 1, uuid.uuid4(), "queued")
        adapter = Mock()
        adapter.geocode.return_value = GeocodeOutcome(
            "accepted", "accepted_single_point", 55.0, 12.0, "fixture", "point", "fixture", False, {}
        )
        with patch.object(WORKER.psycopg, "connect", return_value=connection), \
             patch.object(WORKER, "get_adapter", return_value=adapter), \
             patch.object(WORKER, "_claim_job", side_effect=[job, None]), \
             patch.object(WORKER, "_is_restricted", return_value=False), \
             patch.object(WORKER, "_reserve_request", return_value=(uuid.uuid4(), None)), \
             patch.object(WORKER, "_persist_outcome", return_value="stale_lease") as persist:
            processed = WORKER.run(
                "postgresql://synthetic", "fixture", 1, 0, 1,
                provider_interval=0, worker_id="synthetic-worker",
            )
        self.assertEqual(processed, 0)
        self.assertEqual(adapter.geocode.call_count, 1)
        persist.assert_called_once()

    def test_rate_contention_is_deferred_without_provider_retry_or_busy_wait(self):
        connection = Mock()
        connection.__enter__ = Mock(return_value=connection)
        connection.__exit__ = Mock(return_value=False)
        job = (uuid.uuid4(), uuid.uuid4(), "private synthetic query", 1, uuid.uuid4(), "queued")
        adapter = Mock()
        with patch.object(WORKER.psycopg, "connect", return_value=connection), \
             patch.object(WORKER, "get_adapter", return_value=adapter), \
             patch.object(WORKER, "_claim_job", side_effect=[job, None]), \
             patch.object(WORKER, "_is_restricted", return_value=False), \
             patch.object(WORKER, "_reserve_request", return_value=(None, "rate_limited")) as reserve, \
             patch.object(WORKER, "_defer_job", return_value="deferred") as defer:
            processed = WORKER.run(
                "postgresql://synthetic", "fixture", 1, 0, 3,
                daily_budget=2, provider_interval=2, worker_id="synthetic-worker",
            )
        self.assertEqual(processed, 1)
        adapter.geocode.assert_not_called()
        reserve.assert_called_once()
        self.assertEqual(reserve.call_args.args[4], 1)
        defer.assert_called_once()
        self.assertEqual(defer.call_args.args[5], "provider_rate_limited")

    def test_worker_output_and_provider_errors_are_redacted(self):
        source = (ROOT / "scripts/stages/geocode-worker.py").read_text()
        self.assertNotIn("query={", source)
        self.assertNotIn("source_record_id=", source)
        self.assertIn("type(error).__name__", source)
        self.assertNotIn("print(query", source)

    def test_worker_image_is_separate_and_pinned(self):
        dockerfile = (ROOT.parent / "Dockerfile.worker").read_text()
        requirements = (ROOT.parent / "pipeline/worker-requirements.txt").read_text()
        self.assertIn("FROM python:3.12.8-slim-bookworm", dockerfile)
        self.assertIn("COPY pipeline /app/pipeline", dockerfile)
        self.assertIn("psycopg[binary]==3.2.9", requirements)


if __name__ == "__main__":
    unittest.main()
