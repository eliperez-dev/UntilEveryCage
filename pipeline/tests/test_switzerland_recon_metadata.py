import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class SwitzerlandReconMetadataTests(unittest.TestCase):
    def test_row_free_recon_and_conservative_language(self):
        text = (ROOT / "docs" / "country-recon-ch.md").read_text(encoding="utf-8")
        self.assertIn("row-free", text)
        self.assertIn("Difficulty estimate: high", text)
        self.assertIn("No adapter", text)

    def test_registry_and_status_have_matching_blocked_source(self):
        registry = json.loads((ROOT / "pipeline" / "source_registry.json").read_text(encoding="utf-8"))
        status = json.loads((ROOT / "docs" / "source-status.json").read_text(encoding="utf-8"))
        source = next(s for s in registry["sources"] if s["source_id"] == "ch.blv.approved-food")
        current = next(s for s in status["sources"] if s["source_id"] == "ch.blv.approved-food")
        self.assertEqual(source["adapter_status"], "reference_only")
        self.assertEqual(current["publication_eligibility"], "blocked")
        self.assertEqual(current["acquisition"], "blocked")
        self.assertTrue(source["blockers"])


if __name__ == "__main__":
    unittest.main()
