import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from pipeline.common.orchestrator import run_private_lifecycle
from pipeline.contracts.adapter_contract import SourceArtifact
from .adapter import BelgiumOperatorsAdapter


ROOT = Path(__file__).parent


class BelgiumAdapterTests(unittest.TestCase):
    def _adapter(self):
        return BelgiumOperatorsAdapter(ROOT / "fixtures" / "synthetic_activity_codes.csv", SourceArtifact("https://example.invalid/activity.csv", "2026-09-14T00:00:00Z", hashlib.sha256((ROOT / "fixtures" / "synthetic_activity_codes.csv").read_bytes()).hexdigest(), (ROOT / "fixtures" / "synthetic_activity_codes.csv").stat().st_size))

    def test_join_classifies_scope_without_exposing_private_fields(self):
        adapter = self._adapter()
        result = adapter.parse_bytes((ROOT / "fixtures" / "synthetic_operators.csv").read_bytes())
        self.assertEqual(len(result["accepted"]), 3)
        self.assertEqual(len(result["quarantined"]), 2)
        mixed = next(row for row in result["accepted"] if row["source_id"] == "be.locations" and row["normalized"]["establishment_id"] == "BE-SYN-003")
        self.assertEqual(mixed["normalized"]["activity_categories"], ("slaughter", "cutting"))
        self.assertTrue(mixed["normalized"]["scope_flags"]["slaughterhouse"])
        self.assertIsNone(mixed["normalized"]["address"])
        self.assertIn("address", mixed["source_values"])

    def test_unknown_activity_and_privacy_risk_quarantine(self):
        result = self._adapter().parse_bytes((ROOT / "fixtures" / "synthetic_operators.csv").read_bytes())
        reasons = [set(item["reasons"]) for item in result["quarantined"]]
        self.assertIn("address_privacy_risk", set().union(*reasons))
        self.assertIn("unresolved_activity_code", set().union(*reasons))

    def test_ambiguous_codebook_key_is_not_silently_selected(self):
        with tempfile.TemporaryDirectory() as directory:
            codebook = Path(directory) / "codes.csv"
            codebook.write_text("lap_code,place_description\nLAP-SH,Slaughterhouse\nLAP-SH,Other place\n", encoding="utf-8")
            adapter = BelgiumOperatorsAdapter(codebook)
            result = adapter.parse_bytes((ROOT / "fixtures" / "synthetic_operators.csv").read_bytes())
            first = next(item for item in result["quarantined"] if item["record"]["normalized"]["establishment_id"] == "BE-SYN-001")
            self.assertIn("unresolved_activity_code", first["reasons"])

    def test_run_is_deterministic_and_shared_health_is_private(self):
        raw = ROOT / "fixtures" / "synthetic_operators.csv"
        code = ROOT / "fixtures" / "synthetic_activity_codes.csv"
        adapter = self._adapter()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = SourceArtifact("https://example.invalid/operators.csv", "2026-09-14T00:00:00Z", hashlib.sha256(raw.read_bytes()).hexdigest(), raw.stat().st_size, publication_date="2026-09-13", code_version=adapter.adapter_version, config_version=adapter.schema_version)
            status = run_private_lifecycle(raw, root / "runs", artifact, adapter)
            run_dir = Path(status["run_dir"])
            self.assertEqual(status["status"], "candidate-ready")
            self.assertEqual(status["manifest"]["codebook_sha256"], hashlib.sha256(code.read_bytes()).hexdigest())
            self.assertTrue((run_dir / "source-health.json").exists())
            self.assertTrue((run_dir / "release-candidate" / "records.jsonl").exists())
            self.assertFalse(json.loads((run_dir / "source-health.json").read_text())["public_exposure"])
            self.assertNotIn("source_values", (run_dir / "qa.json").read_text())


if __name__ == "__main__":
    unittest.main()
