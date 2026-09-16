import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from pipeline.common.orchestrator import run_private_lifecycle
from pipeline.contracts.adapter_contract import SourceArtifact
from .adapter import FranceDgalSectionIAdapter, FranceDgalSectionIIAdapter

FIXTURES = Path(__file__).parent / "fixtures"


class FranceAdapterTests(unittest.TestCase):
    def test_section_i_preserves_source_and_quarantines_duplicate(self):
        adapter = FranceDgalSectionIAdapter(); result = adapter.parse_file(FIXTURES / "section_i.csv")
        self.assertEqual(len(result["accepted"]), 2); self.assertEqual(len(result["quarantined"]), 1)
        row = result["accepted"][0]
        self.assertEqual(row["normalized"]["source_section"], "I"); self.assertEqual(row["normalized"]["activity_categories"], ("slaughter",))
        self.assertEqual(row["source_values"]["SIRET"], "12345678901234"); self.assertIsNone(row["normalized"]["address"]); self.assertIsNone(row["normalized"]["coordinates"])
        self.assertEqual(result["quarantined"][0]["reasons"], ("duplicate_source_row",))

    def test_section_ii_missing_identity_is_quarantined(self):
        result = FranceDgalSectionIIAdapter().parse_file(FIXTURES / "section_ii.csv")
        self.assertEqual(len(result["accepted"]), 1); self.assertIn("missing_approval_number", result["quarantined"][0]["reasons"])

    def test_schema_drift_and_lifecycle_are_closed(self):
        adapter = FranceDgalSectionIAdapter(); raw = (FIXTURES / "section_i.csv").read_bytes(); artifact = SourceArtifact(adapter.source_url, "2026-09-15T00:00:00Z", hashlib.sha256(raw).hexdigest(), len(raw), code_version=adapter.adapter_version, config_version=adapter.schema_version)
        with self.assertRaises(ValueError): adapter.parse_bytes(raw.replace("N° d'agrément".encode(), b"wrong"))
        with tempfile.TemporaryDirectory() as d:
            status = run_private_lifecycle(FIXTURES / "section_i.csv", Path(d) / "runs", artifact, adapter); root = Path(status["run_dir"])
            self.assertEqual(status["status"], "candidate-ready"); self.assertTrue((root / "operator-review-packet.json").exists()); self.assertFalse((root / "released").exists())
            self.assertFalse(json.loads((root / "operator-review-packet.json").read_text())["row_payloads_included"])


if __name__ == "__main__": unittest.main()
