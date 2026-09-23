"""Disposable PostGIS exercise for synthetic SA EPA licence/activity records."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import psycopg

from pipeline.common.refresh_runner import RefreshCatalog, RefreshRunner
from pipeline.contracts.refresh import RefreshRequest
from pipeline.sources.australia.sa_epa import SOURCE_URL
from .fixture import E2EEnvironment

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "pipeline/sources/australia/fixtures/sa_epa_activities.geojson"
IMPORTER = ROOT / "pipeline/scripts/maintenance/import-candidate.py"


class SaEpaCandidateImportE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.environ.get("UEC_RUN_E2E") != "1":
            raise unittest.SkipTest("set UEC_RUN_E2E=1 to run Docker-backed E2E tests")
        cls.env = E2EEnvironment()
        cls.env.test_release_id = "candidate-sa-epa-e2e"
        cls.env = cls.env.start()
        cls.temp = tempfile.TemporaryDirectory(dir=ROOT)
        root = Path(cls.temp.name)
        raw = FIXTURE.read_bytes()
        cls.artifact = root / "sa-epa-activities.geojson"
        shutil.copyfile(FIXTURE, cls.artifact)
        cls.catalog = RefreshCatalog()

        def importer(source_dir: Path, database_url: str):
            manifest = next(source_dir.rglob("candidate-handoff/manifest.json"), None)
            if manifest is None:
                raise RuntimeError("private candidate handoff is missing")
            handoff = manifest.parent
            command = [sys.executable, str(IMPORTER), "--manifest", str(manifest),
                "--normalized", str(handoff / "normalized/records.jsonl"), "--raw", str(cls.artifact),
                "--release-id", cls.env.test_release_id, "--database-url", database_url, "--disposable-db"]
            result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
            if result.returncode:
                tail = (result.stderr or result.stdout).splitlines()
                cls.import_diagnostic = {"returncode": result.returncode, "last_line": tail[-1][-240:] if tail else "no output"}
                raise RuntimeError(f"candidate import failed:\n{result.stdout}\n{result.stderr}")
            match = re.search(r"imported (\d+) candidate rows", result.stdout)
            if not match:
                raise RuntimeError(f"candidate import result was not an aggregate count: {result.stdout}")
            return {"status": "imported", "inserted": int(match.group(1))}

        cls.runner = RefreshRunner(cls.catalog, candidate_importer=importer)
        cls.request = RefreshRequest(source_ids=("au.sa.epa.licensed-activities",), mode="local-artifact",
            artifact_paths={"au.sa.epa.licensed-activities": str(cls.artifact)}, output_root=root / "runner",
            import_candidates=True, database_url=cls.env.database_url,
            options={"artifact_metadata": {"source_url": SOURCE_URL, "retrieved_at_utc": "2026-09-16T00:00:00Z",
                "sha256": hashlib.sha256(raw).hexdigest(), "byte_size": len(raw), "effective_date": "2026-09-16"}})
        cls.first = cls.runner.run(cls.request)
        cls.second = cls.runner.run(cls.request)

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "temp", None):
            cls.temp.cleanup()
        if getattr(cls, "env", None):
            cls.env.stop()

    def test_activity_children_import_idempotently_under_two_licences(self):
        self.assertEqual(self.first["counts"]["succeeded"], 1,
            json.dumps({"results": self.first["results"], "import": getattr(self, "import_diagnostic", None)}, sort_keys=True))
        self.assertEqual(self.first["results"][0]["summary"]["candidate_import"]["inserted"], 2)
        self.assertEqual(self.second["results"][0]["summary"]["candidate_import"]["inserted"], 0)
        self.assertFalse(self.first["results"][0]["publication"]["published"])
        with psycopg.connect(self.env.database_url) as db:
            source_rows = db.execute("SELECT count(*) FROM uec.source_records WHERE source_id='au.sa.epa.licensed-activities'").fetchone()[0]
            facilities = db.execute("SELECT count(DISTINCT f.facility_id) FROM uec.facilities f JOIN uec.observations o USING(facility_id) JOIN uec.source_records r USING(source_record_id) WHERE r.source_id='au.sa.epa.licensed-activities'").fetchone()[0]
            observations = db.execute("SELECT count(*) FROM uec.observations o JOIN uec.source_records r USING(source_record_id) WHERE r.source_id='au.sa.epa.licensed-activities'").fetchone()[0]
            reruns = db.execute("SELECT count(*) FROM uec.acquisition_runs WHERE source_id='au.sa.epa.licensed-activities'").fetchone()[0]
            releases = db.execute("SELECT count(*) FROM uec.releases WHERE release_id=%s", (self.env.test_release_id,)).fetchone()[0]
            self.assertEqual((source_rows, facilities, observations, reruns, releases), (2, 2, 2, 2, 1))
            self.assertTrue(db.execute("SELECT test_only FROM uec.releases WHERE release_id=%s", (self.env.test_release_id,)).fetchone()[0])


if __name__ == "__main__":
    unittest.main()
