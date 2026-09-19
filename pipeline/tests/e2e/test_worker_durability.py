"""Disposable database lifecycle tests for the durable geocoding worker."""

import importlib.util
import os
import threading
import time
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import psycopg
from pipeline.geocoding.base import GeocodeOutcome

try:
    from .fixture import E2EEnvironment
except ImportError:
    from fixture import E2EEnvironment


ROOT = Path(__file__).parents[2]
SPEC = importlib.util.spec_from_file_location("durable_geocode_worker", ROOT / "scripts/stages/geocode-worker.py")
WORKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(WORKER)


class WorkerDurabilityE2ETests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.environ.get("UEC_RUN_E2E") != "1":
            raise unittest.SkipTest("set UEC_RUN_E2E=1 to run Docker-backed worker lifecycle tests")
        cls.env = E2EEnvironment().start(wait_for_ready=False)
        cls.source_id = "e2e.worker.durability"
        with psycopg.connect(cls.env.database_url) as db:
            with db.transaction():
                db.execute(
                    "INSERT INTO uec.sources (source_id,country_code,name,official_url,access_method) "
                    "VALUES (%s,'US','Synthetic worker source','https://example.invalid/worker','fixture') "
                    "ON CONFLICT (source_id) DO NOTHING",
                    (cls.source_id,),
                )

    @classmethod
    def tearDownClass(cls):
        cls.env.stop()

    def _queue(self, provider="synthetic-worker"):
        now = datetime.now(timezone.utc)
        record_id, job_id, artifact_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        with psycopg.connect(self.env.database_url) as db:
            with db.transaction():
                db.execute(
                    "INSERT INTO uec.raw_artifacts (artifact_id,storage_key,sha256,byte_size,retrieved_at) "
                    "VALUES (%s,%s,%s,1,%s)",
                    (artifact_id, f"e2e/worker/{artifact_id}", uuid.uuid4().hex * 2, now),
                )
                db.execute(
                    "INSERT INTO uec.source_records "
                    "(source_record_id,source_id,source_record_key,artifact_id,raw_fields,parsed_at) "
                    "VALUES (%s,%s,%s,%s,'{}',%s)",
                    (record_id, self.source_id, str(record_id), artifact_id, now),
                )
                db.execute(
                    "INSERT INTO uec.geocode_jobs (job_id,source_record_id,provider_id,query) "
                    "VALUES (%s,%s,%s,'synthetic query')",
                    (job_id, record_id, provider),
                )
                db.execute(
                    "INSERT INTO uec.geocode_job_events (job_id,event_type,attempt_number) "
                    "VALUES (%s,'queued',1)",
                    (job_id,),
                )
        return job_id, record_id

    def test_claim_is_visible_before_paused_provider_returns(self):
        job_id, _ = self._queue()
        provider_started = threading.Event()
        release_provider = threading.Event()

        class PausingAdapter:
            def geocode(self, _query):
                provider_started.set()
                if not release_provider.wait(10):
                    raise AssertionError("synthetic provider was not released")
                return GeocodeOutcome("unresolved", "fixture", None, None, None, None, "fixture", False, {})

        adapter = PausingAdapter()
        errors = []

        def run_worker():
            try:
                WORKER.run(
                    self.env.database_url, "synthetic-worker", 1, 0, 1,
                    daily_budget=5, provider_interval=0, worker_id="paused-worker",
                )
            except BaseException as error:  # surface thread failures to unittest
                errors.append(error)

        with patch.object(WORKER, "get_adapter", return_value=adapter):
            thread = threading.Thread(target=run_worker)
            thread.start()
            self.assertTrue(provider_started.wait(10))
            with psycopg.connect(self.env.database_url) as db:
                event = db.execute(
                    "SELECT event_type,worker_id FROM uec.geocode_job_current WHERE job_id=%s",
                    (job_id,),
                ).fetchone()
            self.assertEqual(event, ("started", "paused-worker"))
            release_provider.set()
            thread.join(10)
            self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])

    def test_reclaimed_lease_fences_late_first_worker_result(self):
        job_id, record_id = self._queue(provider="synthetic-fence")
        first_started = threading.Event()
        release_first = threading.Event()

        class FencingAdapter:
            calls = 0

            def geocode(self, _query):
                self.calls += 1
                if self.calls == 1:
                    first_started.set()
                    if not release_first.wait(10):
                        raise AssertionError("synthetic first provider call was not released")
                return GeocodeOutcome("accepted", "fixture", 55.0, 12.0, "fixture", "point", "fixture", False, {})

        adapter = FencingAdapter()
        errors = []

        def run_worker(worker_id):
            try:
                WORKER.run(
                    self.env.database_url, "synthetic-fence", 1, 0, 1,
                    daily_budget=5, provider_interval=0, lease_timeout=1, worker_id=worker_id,
                )
            except BaseException as error:
                errors.append((worker_id, error))

        with patch.object(WORKER, "get_adapter", return_value=adapter):
            first = threading.Thread(target=run_worker, args=("first-worker",))
            first.start()
            self.assertTrue(first_started.wait(10))
            time.sleep(1.2)
            second = threading.Thread(target=run_worker, args=("second-worker",))
            second.start()
            second.join(10)
            self.assertFalse(second.is_alive())
            release_first.set()
            first.join(10)
            self.assertFalse(first.is_alive())
        self.assertEqual(errors, [])
        with psycopg.connect(self.env.database_url) as db:
            result_count = db.execute(
                "SELECT count(*) FROM uec.geocode_results WHERE source_record_id=%s AND provider_id='synthetic-fence'",
                (record_id,),
            ).fetchone()[0]
            events = db.execute(
                "SELECT event_type,worker_id FROM uec.geocode_job_events WHERE job_id=%s ORDER BY occurred_at,event_id",
                (job_id,),
            ).fetchall()
        self.assertEqual(result_count, 1)
        self.assertEqual(events[-1], ("accepted", "second-worker"))

    def test_two_workers_share_one_remaining_request_allowance(self):
        self._queue(provider="synthetic-budget")
        self._queue(provider="synthetic-budget")
        calls = 0
        calls_lock = threading.Lock()

        class CountingAdapter:
            def geocode(self, _query):
                nonlocal calls
                with calls_lock:
                    calls += 1
                return GeocodeOutcome("unresolved", "fixture", None, None, None, None, "fixture", False, {})

        def run_worker(worker_id):
            try:
                WORKER.run(
                    self.env.database_url, "synthetic-budget", 1, 0, 1,
                    daily_budget=1, provider_interval=0, worker_id=worker_id,
                )
            except BaseException as error:
                errors.append((worker_id, error))

        errors = []
        with patch.object(WORKER, "get_adapter", return_value=CountingAdapter()):
            workers = [threading.Thread(target=run_worker, args=(f"budget-{n}",)) for n in (1, 2)]
            for worker in workers:
                worker.start()
            for worker in workers:
                worker.join(10)
                self.assertFalse(worker.is_alive())
        self.assertEqual(errors, [])
        with psycopg.connect(self.env.database_url) as db:
            reservations = db.execute(
                "SELECT count(*) FROM uec.geocode_request_reservations "
                "WHERE provider_id='synthetic-budget' AND budget_date=(now() AT TIME ZONE 'UTC')::date"
            ).fetchone()[0]
        self.assertEqual(calls, 1)
        self.assertEqual(reservations, 1)


if __name__ == "__main__":
    unittest.main()
