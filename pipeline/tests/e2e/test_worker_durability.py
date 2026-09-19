"""Disposable database lifecycle tests for the durable geocoding worker."""

import importlib.util
import json
import os
import shutil
import subprocess
import threading
import time
import unittest
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
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
    worker_image = None

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
        if cls.worker_image:
            subprocess.run(["docker", "rmi", "--force", cls.worker_image], capture_output=True, text=True, check=False)
        cls.env.stop()

    @classmethod
    def _build_worker_image(cls):
        if cls.worker_image:
            return cls.worker_image
        if shutil.which("docker") is None:
            raise unittest.SkipTest("docker CLI is unavailable")
        cls.worker_image = f"uec-worker-e2e-{uuid.uuid4().hex[:10]}"
        result = subprocess.run(
            ["docker", "build", "--file", "Dockerfile.worker", "--tag", cls.worker_image, "."],
            cwd=ROOT.parent,
            capture_output=True,
            text=True,
            timeout=240,
            check=False,
        )
        if result.returncode:
            raise AssertionError(f"worker image build failed:\n{result.stdout[-4000:]}\n{result.stderr[-4000:]}")
        return cls.worker_image

    @staticmethod
    def _provider_server(*, hold_second=False):
        state = {"calls": 0, "lock": threading.Lock(), "second_started": threading.Event(), "release_second": threading.Event()}

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802 - BaseHTTPRequestHandler API
                with state["lock"]:
                    state["calls"] += 1
                    call_number = state["calls"]
                if hold_second and call_number == 2:
                    state["second_started"].set()
                    state["release_second"].wait(30)
                body = json.dumps({"status": "ok"}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                try:
                    self.wfile.write(body)
                except OSError:
                    pass

            def log_message(self, _format, *_args):
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        return server, thread, state

    @staticmethod
    def _wait_for(predicate, timeout=20):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return True
            time.sleep(0.1)
        return False

    def _container_database_url(self):
        return self.env.database_url.replace("localhost", "host.docker.internal")

    def _result_count(self, record_id, provider):
        with psycopg.connect(self.env.database_url) as db:
            return db.execute(
                "SELECT count(*) FROM uec.geocode_results WHERE source_record_id=%s AND provider_id=%s",
                (record_id, provider),
            ).fetchone()[0]

    def _docker_worker_command(self, image, database_url, provider_url, *, limit=1, lease_timeout=900):
        harness = (ROOT / "tests" / "e2e" / "docker_worker_sitecustomize.py").resolve()
        volume = f"{str(harness).replace(chr(92), '/') }:/app/sitecustomize.py:ro"
        return [
            "docker", "run", "--rm", "--add-host", "host.docker.internal:host-gateway",
            "--volume", volume,
            "--env", f"UEC_DATABASE_URL={database_url}",
            "--env", f"UEC_SYNTHETIC_PROVIDER_URL={provider_url}",
            "--env", "PYTHONPATH=/app",
            image, "--provider", "synthetic-docker", "--limit", str(limit),
            "--daily-budget", "10", "--retries", "3", "--delay", "0",
            "--provider-interval", "0", "--lease-timeout", str(lease_timeout),
            "--worker-id", "docker-worker",
        ]

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

    def test_retryable_provider_attempts_are_each_charged_in_database(self):
        job_id, record_id = self._queue(provider="synthetic-retry")
        calls = []

        class RetryAdapter:
            def geocode(self, _query):
                calls.append(len(calls) + 1)
                if len(calls) == 1:
                    return GeocodeOutcome("failed", "temporary", None, None, None, None, "fixture", True, {"error": "temporary"})
                return GeocodeOutcome("unresolved", "fixture", None, None, None, None, "fixture", False, {})

        with patch.object(WORKER, "get_adapter", return_value=RetryAdapter()):
            WORKER.run(
                self.env.database_url, "synthetic-retry", 1, 0, 3,
                daily_budget=3, provider_interval=0, worker_id="retry-worker",
            )
        with psycopg.connect(self.env.database_url) as db:
            reservation_count = db.execute(
                "SELECT count(*) FROM uec.geocode_request_reservations WHERE job_id=%s",
                (job_id,),
            ).fetchone()[0]
            event = db.execute(
                "SELECT event_type FROM uec.geocode_job_current WHERE job_id=%s",
                (job_id,),
            ).fetchone()[0]
            result_count = db.execute(
                "SELECT count(*) FROM uec.geocode_results WHERE source_record_id=%s AND provider_id='synthetic-retry'",
                (record_id,),
            ).fetchone()[0]
        self.assertEqual(calls, [1, 2])
        self.assertEqual(reservation_count, 2)
        self.assertEqual(event, "unresolved")
        self.assertEqual(result_count, 1)

    def test_restriction_added_while_provider_paused_discards_final_result(self):
        job_id, record_id = self._queue(provider="synthetic-restriction")
        provider_started = threading.Event()
        release_provider = threading.Event()
        errors = []

        class PausingAdapter:
            calls = 0

            def geocode(self, _query):
                self.calls += 1
                provider_started.set()
                if not release_provider.wait(10):
                    raise AssertionError("synthetic provider was not released")
                return GeocodeOutcome("accepted", "fixture", 55.0, 12.0, "fixture", "point", "fixture", False, {})

        def run_worker():
            try:
                WORKER.run(
                    self.env.database_url, "synthetic-restriction", 1, 0, 1,
                    daily_budget=3, provider_interval=0, worker_id="restriction-worker",
                )
            except BaseException as error:
                errors.append(error)

        with patch.object(WORKER, "get_adapter", return_value=PausingAdapter()):
            thread = threading.Thread(target=run_worker)
            thread.start()
            self.assertTrue(provider_started.wait(10))
            with psycopg.connect(self.env.database_url) as db:
                db.execute(
                    "INSERT INTO uec.record_access_events "
                    "(source_record_id,action,reason_category,policy_version,maintainer) "
                    "VALUES (%s,'public_access_revoked','privacy','e2e-worker','synthetic-test')",
                    (record_id,),
                )
            release_provider.set()
            thread.join(10)
            self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        with psycopg.connect(self.env.database_url) as db:
            event = db.execute(
                "SELECT event_type FROM uec.geocode_job_current WHERE job_id=%s",
                (job_id,),
            ).fetchone()[0]
            result_count = db.execute(
                "SELECT count(*) FROM uec.geocode_results WHERE source_record_id=%s AND provider_id='synthetic-restriction'",
                (record_id,),
            ).fetchone()[0]
        self.assertEqual(event, "cancelled")
        self.assertEqual(result_count, 0)

    def test_active_restriction_before_claim_blocks_provider_and_budget(self):
        job_id, record_id = self._queue(provider="synthetic-preblocked")
        calls = []

        with psycopg.connect(self.env.database_url) as db:
            db.execute(
                "INSERT INTO uec.record_access_events "
                "(source_record_id,action,reason_category,policy_version,maintainer) "
                "VALUES (%s,'public_access_revoked','privacy','e2e-worker','synthetic-test')",
                (record_id,),
            )

        class MustNotCallAdapter:
            def geocode(self, _query):
                calls.append(True)
                raise AssertionError("an actively restricted queued job must not call a provider")

        with patch.object(WORKER, "get_adapter", return_value=MustNotCallAdapter()):
            processed = WORKER.run(
                self.env.database_url, "synthetic-preblocked", 1, 0, 1,
                daily_budget=1, provider_interval=0, worker_id="preblocked-worker",
            )
        with psycopg.connect(self.env.database_url) as db:
            event = db.execute(
                "SELECT event_type FROM uec.geocode_job_current WHERE job_id=%s", (job_id,)
            ).fetchone()[0]
            reservation_count = db.execute(
                "SELECT count(*) FROM uec.geocode_request_reservations WHERE job_id=%s", (job_id,)
            ).fetchone()[0]
        self.assertEqual(processed, 0)
        self.assertEqual(calls, [])
        self.assertEqual(event, "queued")
        self.assertEqual(reservation_count, 0)

    def test_real_worker_image_drains_synthetic_queue_and_exits_without_private_logs(self):
        job_id, record_id = self._queue(provider="synthetic-docker")
        server, server_thread, state = self._provider_server()
        image = self._build_worker_image()
        provider_url = f"http://host.docker.internal:{server.server_port}/geocode"
        try:
            result = subprocess.run(
                self._docker_worker_command(image, self._container_database_url(), provider_url),
                cwd=ROOT.parent,
                capture_output=True,
                text=True,
                timeout=90,
                check=False,
            )
        finally:
            server.shutdown()
            server_thread.join(10)
            server.server_close()
        self.assertEqual(result.returncode, 0, result.stderr[-4000:])
        self.assertEqual(state["calls"], 1)
        self.assertNotIn("synthetic query", result.stdout)
        self.assertNotIn("GEOAPIFY_API_KEY", result.stdout + result.stderr)
        with psycopg.connect(self.env.database_url) as db:
            self.assertEqual(
                db.execute("SELECT event_type FROM uec.geocode_job_current WHERE job_id=%s", (job_id,)).fetchone()[0],
                "accepted",
            )
            self.assertEqual(
                db.execute("SELECT count(*) FROM uec.geocode_results WHERE source_record_id=%s", (record_id,)).fetchone()[0],
                1,
            )

    def test_process_kill_preserves_completed_result_and_restart_reclaims_second_job(self):
        first_job, first_record = self._queue(provider="synthetic-docker")
        second_job, second_record = self._queue(provider="synthetic-docker")
        server, server_thread, state = self._provider_server(hold_second=True)
        image = self._build_worker_image()
        provider_url = f"http://host.docker.internal:{server.server_port}/geocode"
        container_name = f"uec-worker-kill-{uuid.uuid4().hex[:8]}"
        command = self._docker_worker_command(image, self._container_database_url(), provider_url, limit=2, lease_timeout=1)
        command[2:2] = ["--detach", "--name", container_name]
        try:
            started = subprocess.run(command, cwd=ROOT.parent, capture_output=True, text=True, timeout=30, check=False)
            self.assertEqual(started.returncode, 0, started.stderr[-2000:])
            self.assertTrue(self._wait_for(lambda: self._result_count(first_record, "synthetic-docker") == 1, 20))
            self.assertTrue(state["second_started"].wait(20))
            killed = subprocess.run(["docker", "kill", container_name], capture_output=True, text=True, check=False)
            self.assertEqual(killed.returncode, 0, killed.stderr[-2000:])
            with psycopg.connect(self.env.database_url) as db:
                second_event = db.execute(
                    "SELECT event_type FROM uec.geocode_job_current WHERE job_id=%s", (second_job,)
                ).fetchone()[0]
            self.assertEqual(self._result_count(first_record, "synthetic-docker"), 1)
            self.assertEqual(second_event, "started")
            time.sleep(1.2)
            state["release_second"].set()
            restart = subprocess.run(
                self._docker_worker_command(image, self._container_database_url(), provider_url, limit=1, lease_timeout=1),
                cwd=ROOT.parent,
                capture_output=True,
                text=True,
                timeout=90,
                check=False,
            )
            self.assertEqual(restart.returncode, 0, restart.stderr[-4000:])
            self.assertEqual(self._result_count(first_record, "synthetic-docker"), 1)
            self.assertEqual(self._result_count(second_record, "synthetic-docker"), 1)
        finally:
            state["release_second"].set()
            subprocess.run(["docker", "rm", "--force", container_name], capture_output=True, text=True, check=False)
            server.shutdown()
            server_thread.join(10)
            server.server_close()


if __name__ == "__main__":
    unittest.main()
