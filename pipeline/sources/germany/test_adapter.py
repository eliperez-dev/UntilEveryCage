import hashlib
import importlib.util
import tempfile
import unittest
from pathlib import Path

from pipeline.common.orchestrator import run_private_lifecycle
from pipeline.contracts.adapter_contract import SourceArtifact
from .adapter import BltuAdapter


ROOT = Path(__file__).parent


class GermanyPrivateAdapterTests(unittest.TestCase):
    def test_bltu_preserves_native_flags_and_address_privately(self):
        raw = ROOT.parent.parent / "germany" / "fixtures" / "synthetic_bltu.csv"
        adapter = BltuAdapter()
        result = adapter.parse_bytes(raw.read_bytes())
        self.assertEqual(len(result["accepted"]), 2)
        normalized = result["accepted"][0]["normalized"]
        self.assertIn(normalized["activity_categories"], (("slaughter",), ("processing",)))
        self.assertIsNotNone(normalized["address"])
        self.assertIn(normalized["activity_flags"][0]["code"], {"SH", "CP"})
        self.assertIsNone(normalized["coordinates"])
        self.assertGreaterEqual(len(result["quarantined"]), 1)

    def test_unknown_native_activity_flag_is_preserved_not_discarded(self):
        raw = ROOT.parent.parent / "germany" / "fixtures" / "synthetic_bltu.csv"
        content = raw.read_bytes().replace(b";;;DE-SYN-001;;;;;;x", b";;;DE-SYN-001;x;;;;;x", 1)
        result = BltuAdapter().parse_bytes(content)
        self.assertEqual(result["schema_status"], "matched")
        self.assertEqual(len(result["accepted"]), 2)
        flags = result["accepted"][0]["normalized"]["activity_flags"]
        self.assertTrue(flags)

    def test_preview_projection_keeps_address_private_and_has_no_point(self):
        script = ROOT.parents[1] / "scripts" / "maintenance" / "import-real-preview.py"
        spec = importlib.util.spec_from_file_location("germany_preview_import", script)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)
        raw = ROOT.parent.parent / "germany" / "fixtures" / "synthetic_bltu.csv"
        row = BltuAdapter().parse_bytes(raw.read_bytes())["accepted"][0]
        projected = module.parse_row("de.locations", row)
        self.assertIsNone(projected[5])
        self.assertIsNone(projected[6])
        self.assertTrue(projected[18])

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
