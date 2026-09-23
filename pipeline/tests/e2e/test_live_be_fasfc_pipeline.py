"""Opt-in live FASFC E2E; never runs unless explicitly enabled by an operator."""
import os
import contextlib
import io
import json
import subprocess
import unittest
from pathlib import Path

import psycopg

from pipeline.tests.e2e.fixture import E2EEnvironment, _sanitize_diagnostics
from pipeline.refresh_private import main
from pipeline.common.graph_persistence import import_graph_candidates


ROOT = Path(__file__).resolve().parents[3]


class BelgiumLivePipelineE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.environ.get("UEC_RUN_LIVE_BE_FASFC") != "1" and os.environ.get("UEC_RUN_LIVE_BE_FASFC_REPLAY") != "1":
            raise unittest.SkipTest("set UEC_RUN_LIVE_BE_FASFC=1 for live refresh or UEC_RUN_LIVE_BE_FASFC_REPLAY=1 for a saved-handoff replay")
        cls.environment = E2EEnvironment()
        cls.environment = cls._start_database_only(cls.environment)

    @classmethod
    def _start_database_only(cls, environment):
        try:
            startup = subprocess.run(environment.command("up", "-d", "--wait"), cwd=ROOT, capture_output=True, text=True, env=environment.compose_env())
            if startup.returncode:
                raise RuntimeError("disposable Postgres compose startup failed")
            for _ in range(120):
                ready = environment._database_ready()
                if ready.returncode == 0 and ready.stdout.strip():
                    break
                import time
                time.sleep(.25)
            else:
                raise RuntimeError("disposable Postgres did not become ready")
            for migration in sorted((ROOT / "pipeline/migrations").glob("*.sql")):
                raw = migration.read_bytes()
                try:
                    sql = raw.decode("utf-8-sig")
                except UnicodeDecodeError:
                    sql = raw.decode("cp1252")
                result = subprocess.run(environment.command("exec", "-T", "postgres", "psql", "-v", "ON_ERROR_STOP=1", "-U", "uec", "-d", "uec"), input=sql, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", env=environment.compose_env())
                if result.returncode:
                    raise RuntimeError(f"migration failed: {migration.name}: {_sanitize_diagnostics(result.stderr)}")
            with psycopg.connect(environment.database_url) as db:
                marker = db.execute("SELECT marker FROM uec.disposable_import_guard WHERE database_name=current_database() AND role_name=current_user").fetchone()
                if marker != ("uec-e2e-disposable-v1",):
                    raise RuntimeError("disposable database marker is missing")
            return environment
        except Exception:
            environment.stop()
            raise

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "environment", None):
            cls.environment.stop()

    def test_live_acquisition_to_private_candidate_import(self):
        if os.environ.get("UEC_RUN_LIVE_BE_FASFC") != "1":
            self.skipTest("fresh live network run not requested")
        os.environ["UEC_DATABASE_URL"] = self.environment.database_url
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = main([
                "--source", "be.locations", "--mode", "live-acquisition",
                "--authorize-live-source", "be.locations",
                "--terms-review", "be.locations=data/terms-reviews/be.locations.json",
                "--output-root", "data/staging/private-refresh",
                "--retries", "1", "--import-candidates", "--disposable-db",
                "--database-url-env", "UEC_DATABASE_URL",
            ])
        self.assertEqual(result, 0)
        payload = json.loads(output.getvalue())
        item = payload["results"][0]
        summary = item["summary"]
        imported = summary["candidate_import"]
        self.assertEqual(item["acquisition_classification"], "live")
        self.assertGreater(summary["input_rows"], 0)
        self.assertGreater(summary["in_scope_normalized_observations"], 0)
        self.assertEqual(summary["candidate_observation_rows"], imported["item_count"])
        self.assertEqual(imported["status"], "completed")
        run_root = Path("data/staging/private-refresh") / payload["run_id"]
        plan = json.loads((run_root / "plan.json").read_text(encoding="utf-8"))
        acquisition_id = plan["options"]["acquisition_run_id"]
        artifacts_root = run_root / "sources/be.locations/acquisition"
        self.assertGreater((artifacts_root / "be.locations" / acquisition_id / "operators.csv").stat().st_size, 0)
        self.assertGreater((artifacts_root / "be.activity-codes" / acquisition_id / "activity-codes.csv").stat().st_size, 0)
        replay = import_graph_candidates(self.environment.database_url, run_root / "sources/be.locations/candidate-handoff", disposable_db=True)
        self.assertEqual(replay["status"], "already_present")
        self.assertEqual(replay["already_present_count"], imported["item_count"])
        print(json.dumps({key: summary.get(key) for key in (
            "input_rows", "normalized_rows", "valid_source_activity_rows",
            "in_scope_normalized_observations", "quarantined_rows", "out_of_scope_rows",
            "deduplicated_source_scoped_facility_candidates", "candidate_observation_rows",
            "candidate_handoff_sha256", "operator_last_modified", "attribution")}, sort_keys=True))
        self.assertTrue(os.path.isdir("data/staging/private-refresh"))

    def test_saved_live_handoff_import_is_idempotent(self):
        if os.environ.get("UEC_RUN_LIVE_BE_FASFC_REPLAY") != "1":
            self.skipTest("saved live-handoff replay not requested")
        run_id = os.environ.get("UEC_BE_FASFC_RUN_ID", "refresh-dea0601b107406b6")
        handoff = Path("data/staging/private-refresh") / run_id / "sources/be.locations/candidate-handoff"
        self.assertTrue((handoff / "manifest.json").is_file())
        first = import_graph_candidates(self.environment.database_url, handoff, disposable_db=True)
        second = import_graph_candidates(self.environment.database_url, handoff, disposable_db=True)
        self.assertEqual(first["status"], "completed")
        expected = json.loads((handoff / "manifest.json").read_text(encoding="utf-8"))["normalized_rows"]
        self.assertEqual(first["inserted_count"], expected)
        self.assertEqual(second["status"], "already_present")
        self.assertEqual(second["already_present_count"], expected)


if __name__ == "__main__":
    unittest.main()
