import hashlib
import tempfile
import unittest
from pathlib import Path

from pipeline.common.orchestrator import run_private_lifecycle
from pipeline.contracts.adapter_contract import SourceArtifact
from .adapter import BltuAdapter


ROOT = Path(__file__).parent


class GermanyPrivateAdapterTests(unittest.TestCase):
    def test_bltu_is_typed_and_keeps_coordinates_and_addresses_private(self):
        raw = ROOT.parent.parent / "germany" / "fixtures" / "synthetic_bltu.csv"
        adapter = BltuAdapter()
        result = adapter.parse_bytes(raw.read_bytes())
        self.assertEqual(len(result["accepted"]), 1)
        normalized = result["accepted"][0]["normalized"]
        self.assertEqual(normalized["activity_categories"], ("slaughter",))
        self.assertIsNone(normalized["address"])
        self.assertIsNone(normalized["coordinates"])
        self.assertGreaterEqual(len(result["quarantined"]), 2)

    def test_shared_private_lifecycle_emits_health_and_no_release(self):
        raw = ROOT.parent.parent / "germany" / "fixtures" / "synthetic_bltu.csv"
        adapter = BltuAdapter(); content = raw.read_bytes()
        artifact = SourceArtifact("https://example.invalid/bltu-export.csv", "2026-09-14T00:00:00Z", hashlib.sha256(content).hexdigest(), len(content), code_version=adapter.adapter_version, config_version=adapter.schema_version)
        with tempfile.TemporaryDirectory() as directory:
            status = run_private_lifecycle(raw, Path(directory) / "runs", artifact, adapter)
            run_dir = Path(status["run_dir"])
            self.assertEqual(status["status"], "candidate-ready")
            self.assertTrue((run_dir / "source-health.json").exists())
            self.assertTrue((run_dir / "release-candidate" / "records.jsonl").exists())
            self.assertFalse((run_dir / "released" / "records.jsonl").exists())

    def test_schema_drift_fails_typed_run_before_candidate_handoff(self):
        raw = ROOT.parent.parent / "germany" / "fixtures" / "synthetic_bltu.csv"
        content = raw.read_bytes().replace(b"# Bundesland;", b"unexpected;", 1)
        adapter = BltuAdapter()
        artifact = SourceArtifact("https://example.invalid/bltu-export.csv", "2026-09-14T00:00:00Z", hashlib.sha256(content).hexdigest(), len(content), code_version=adapter.adapter_version, config_version=adapter.schema_version)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "drift.csv"; path.write_bytes(content)
            with self.assertRaisesRegex(ValueError, "schema drift"):
                adapter.run(path, Path(directory) / "run", artifact)


if __name__ == "__main__":
    unittest.main()
