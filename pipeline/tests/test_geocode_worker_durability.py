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


class GeocodeWorkerDurabilityTests(unittest.TestCase):
    def test_migration_adds_lease_fence_and_atomic_request_ledger(self):
        migration = (ROOT / "migrations/040_geocode_worker_durability.sql").read_text()
        for required in (
            "lease_token UUID",
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
        job = (uuid.uuid4(), uuid.uuid4(), "private synthetic query", 1, uuid.uuid4())
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
        job = (uuid.uuid4(), uuid.uuid4(), "private synthetic query", 1, uuid.uuid4())
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
