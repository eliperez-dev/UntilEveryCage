"""Disposable DB E2E for the separate Italy ABP source through the shared runner."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import psycopg

from pipeline.common.refresh_runner import RefreshCatalog, RefreshRunner
from pipeline.contracts.refresh import RefreshRequest

from .fixture import E2EEnvironment


ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "pipeline/sources/italy/fixtures/synthetic_1069.csv"
IMPORTER = ROOT / "pipeline/scripts/maintenance/import-candidate.py"


class Italy1069CandidateImportE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.environ.get("UEC_RUN_E2E") != "1":
            raise unittest.SkipTest("set UEC_RUN_E2E=1 to run Docker-backed Italy ABP E2E")
        cls.env = E2EEnvironment()
        cls.env.test_release_id = "candidate-it1069-e2e"
        cls.env = cls.env.start()
        cls.temp = tempfile.TemporaryDirectory(prefix="uec-it1069-e2e-")
        cls.root = Path(cls.temp.name)

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "temp", None):
            cls.temp.cleanup()
        if getattr(cls, "env", None):
            cls.env.stop()

    def make_runner(self, output: Path) -> RefreshRunner:
        def importer(source_dir: Path, database_url: str):
            manifests = list(source_dir.rglob("candidate-handoff/manifest.json"))
            self.assertTrue(manifests)
            manifest_path = max(manifests, key=lambda path: path.stat().st_mtime_ns)
            normalized = manifest_path.parent / "normalized" / "records.jsonl"
            command = [sys.executable, str(IMPORTER), "--manifest", str(manifest_path),
                       "--normalized", str(normalized), "--raw", str(FIXTURE),
                       "--release-id", "candidate-it1069-e2e", "--database-url", database_url,
                       "--disposable-db"]
            result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            match = re.search(r"imported (\d+) candidate rows", result.stdout)
            self.assertIsNotNone(match, result.stdout)
            return {"status": "imported", "inserted": int(match.group(1)),
                    "candidate_release_state": "candidate-unpromoted"}

        return RefreshRunner(RefreshCatalog(), candidate_importer=importer)

    def run_import(self, runner: RefreshRunner, output: Path, *, mode="fixture", artifact=None):
        return runner.run(RefreshRequest(source_ids=("it.1069-2009",), mode=mode,
            artifact_paths={"it.1069-2009": str(artifact)} if artifact else {},
            output_root=output, import_candidates=True, database_url=self.env.database_url))

    def test_runner_import_rerun_and_schema_failure_preserve_candidate_state(self):
        output = self.root / "runner"
        runner = self.make_runner(output)
        first = self.run_import(runner, output)
        second = self.run_import(runner, output)
        self.assertEqual(first["counts"]["succeeded"], 1)
        self.assertEqual(second["counts"]["succeeded"], 1)
        self.assertEqual(first["results"][0]["summary"]["candidate_import"]["inserted"], 2)
        self.assertEqual(second["results"][0]["summary"]["candidate_import"]["inserted"], 0)
        self.assertFalse(first["results"][0]["publication"]["published"])
        bad = self.root / "wrong-schema.csv"
        bad.write_text("id,name\nSYNTH,not-an-upstream-schema\n", encoding="utf-8")
        bad_bytes = bad.read_bytes()
        (self.root / "acquisition-metadata.json").write_text(json.dumps({
            "source_url": "https://example.invalid/synthetic-abp.csv",
            "retrieved_at_utc": "2026-01-02T00:00:00Z",
            "sha256": hashlib.sha256(bad_bytes).hexdigest(), "byte_size": len(bad_bytes),
            "terms_review_reference": "synthetic-test-reference",
        }), encoding="utf-8")
        result = self.run_import(runner, output, mode="local-artifact", artifact=bad)
        self.assertEqual(result["counts"]["failed"], 1)
        self.assertEqual(result["results"][0]["acquisition_classification"], "schema-drift")
        with psycopg.connect(self.env.database_url) as db:
            records, facilities, observations, releases = db.execute(
                """SELECT (SELECT count(*) FROM uec.source_records WHERE source_id='it.1069-2009'),
                          (SELECT count(*) FROM uec.facilities),
                          (SELECT count(*) FROM uec.observations),
                          (SELECT count(*) FROM uec.releases WHERE release_id='candidate-it1069-e2e')"""
            ).fetchone()
        self.assertEqual((records, facilities, observations, releases), (2, 2, 2, 1))
