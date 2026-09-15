"""Guarded candidate-import/API checks for the Germany and Belgium adapters."""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
import urllib.request
from pathlib import Path

import psycopg

from .fixture import E2EEnvironment
from pipeline.common.orchestrator import run_private_lifecycle
from pipeline.contracts.adapter_contract import SourceArtifact
from pipeline.sources.belgium.adapter import BelgiumOperatorsAdapter
from pipeline.sources.germany.adapter import BltuAdapter

ROOT = Path(__file__).resolve().parents[3]
IMPORTER = ROOT / "pipeline/scripts/maintenance/import-candidate.py"


class GermanyBelgiumCandidateImportE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.environ.get("UEC_RUN_E2E") != "1":
            raise unittest.SkipTest("set UEC_RUN_E2E=1 to run Docker-backed E2E tests")
        cls.env = E2EEnvironment(); cls.env.test_release_id = "candidate-de-be-e2e"; cls.env = cls.env.start()
        cls.temp = tempfile.TemporaryDirectory(); root = Path(cls.temp.name)
        be_raw = ROOT / "pipeline/sources/belgium/fixtures/synthetic_operators.csv"
        be_codes = ROOT / "pipeline/sources/belgium/fixtures/synthetic_activity_codes.csv"
        de_raw = ROOT / "pipeline/germany/fixtures/synthetic_bltu.csv"
        be_adapter = BelgiumOperatorsAdapter(be_codes, SourceArtifact("https://example.invalid/be-codes.csv", "2026-09-14T00:00:00Z", hashlib.sha256(be_codes.read_bytes()).hexdigest(), be_codes.stat().st_size))
        entries = [("be", be_raw, be_adapter, "https://example.invalid/be-operators.csv"), ("de", de_raw, BltuAdapter(), "https://example.invalid/de-bltu.csv")]
        cls.commands = []
        for name, raw, adapter, url in entries:
            content = raw.read_bytes(); source_artifact = SourceArtifact(url, "2026-09-14T00:00:00Z", hashlib.sha256(content).hexdigest(), len(content), code_version=adapter.adapter_version, config_version=adapter.schema_version)
            status = run_private_lifecycle(raw, root / "runs" / name, source_artifact, adapter)
            if status["status"] != "candidate-ready":
                raise RuntimeError(status)
            lifecycle_dir = Path(status["run_dir"])
            cls.commands.append([sys.executable, str(IMPORTER), "--manifest", str(lifecycle_dir / "manifest.json"), "--normalized", str(lifecycle_dir / "normalized/records.jsonl"), "--raw", str(raw), "--release-id", "candidate-de-be-e2e", "--database-url", cls.env.database_url, "--disposable-db"])
        for command in cls.commands:
            first = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
            second = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
            if first.returncode or second.returncode:
                raise RuntimeError(f"candidate import failed: {first.stdout}\n{first.stderr}\n{second.stdout}\n{second.stderr}")

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "temp", None): cls.temp.cleanup()
        if getattr(cls, "env", None): cls.env.stop()

    def test_both_sources_are_idempotent_and_candidate_only(self):
        with psycopg.connect(self.env.database_url) as db:
            counts = dict(db.execute("SELECT source_id, count(*) FROM uec.source_records WHERE source_id IN ('be.locations','de.locations') GROUP BY source_id").fetchall())
            self.assertEqual(counts, {"be.locations": 3, "de.locations": 1})
            self.assertTrue(db.execute("SELECT test_only FROM uec.releases WHERE release_id='candidate-de-be-e2e'").fetchone()[0])
        base = f"http://127.0.0.1:{self.env.api_port}"
        with urllib.request.urlopen(base + "/api/v2/locations?profile=official") as response:
            self.assertEqual(json.loads(response.read())["data"], [])
        request = urllib.request.Request(base + "/api/dev/preview/test-release/locations?profile=official", headers={"X-UEC-Dev-Preview-Token": self.env.dev_preview_token})
        with urllib.request.urlopen(request) as response:
            body = json.loads(response.read())
        self.assertEqual({row["country_code"] for row in body["data"]}, {"BE", "DE"})
        self.assertTrue(body["meta"]["test_only"])
        self.assertTrue(all(row["latitude"] is None for row in body["data"]))
        self.assertNotIn("source_values", json.dumps(body))


if __name__ == "__main__":
    unittest.main()
