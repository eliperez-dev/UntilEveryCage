"""Disposable PostGIS exercise for synthetic SA EPA licence/activity records."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import psycopg

from pipeline.common.orchestrator import run_private_lifecycle
from pipeline.contracts.adapter_contract import SourceArtifact
from pipeline.contracts.candidate_handoff import write_handoff
from pipeline.sources.australia.sa_epa import ADAPTER_VERSION, SCHEMA_VERSION, SOURCE_URL, SaEpaLicensedActivitiesAdapter
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
        adapter = SaEpaLicensedActivitiesAdapter()
        artifact = SourceArtifact(SOURCE_URL, "2026-09-16T00:00:00Z", hashlib.sha256(raw).hexdigest(), len(raw),
            code_version=ADAPTER_VERSION, config_version=SCHEMA_VERSION,
            rights_caveat="Synthetic fixture; source terms unresolved", privacy_caveat="Private candidate; review required")
        status = run_private_lifecycle(FIXTURE, root / "run", artifact, adapter)
        if status["status"] != "candidate-ready":
            raise RuntimeError(status)
        run_dir = Path(status["run_dir"])
        rows = [json.loads(line) for line in (run_dir / "normalized/licences.jsonl").read_text(encoding="utf-8").splitlines() if line]
        write_handoff(run_dir / "candidate-handoff", rows, artifact, source_id=adapter.source_id)
        manifest = run_dir / "candidate-handoff/manifest.json"
        normalized = run_dir / "candidate-handoff/normalized/records.jsonl"
        cls.command = [sys.executable, str(IMPORTER), "--manifest", str(manifest), "--normalized", str(normalized),
            "--raw", str(FIXTURE), "--release-id", cls.env.test_release_id, "--database-url", cls.env.database_url, "--disposable-db"]
        for _ in range(2):
            result = subprocess.run(cls.command, cwd=ROOT, capture_output=True, text=True)
            if result.returncode:
                raise RuntimeError(f"candidate import failed:\n{result.stdout}\n{result.stderr}")

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "temp", None):
            cls.temp.cleanup()
        if getattr(cls, "env", None):
            cls.env.stop()

    def test_activity_children_import_idempotently_under_two_licences(self):
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
