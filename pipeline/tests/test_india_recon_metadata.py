import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class IndiaReconMetadataTests(unittest.TestCase):
    def test_row_free_recon_and_policy_boundaries_are_present(self):
        text = (ROOT / "docs" / "country-recon-in.md").read_text(encoding="utf-8")
        self.assertIn("row-free", text)
        self.assertIn("Publication remains blocked", text)
        self.assertIn("No adapter is built", text)

    def test_india_registry_and_status_are_aligned_and_blocked(self):
        registry = json.loads((ROOT / "pipeline" / "source_registry.json").read_text(encoding="utf-8"))
        status = json.loads((ROOT / "docs" / "source-status.json").read_text(encoding="utf-8"))
        registry_ids = {s["source_id"] for s in registry["sources"] if s["source_id"].startswith("in.")}
        status_rows = [s for s in status["sources"] if s["source_id"].startswith("in.")]
        self.assertEqual(registry_ids, {s["source_id"] for s in status_rows})
        self.assertEqual(len(registry_ids), 4)
        for row in status_rows:
            self.assertEqual(row["publication_eligibility"], "blocked")
            self.assertNotEqual(row["runtime_health"], "healthy")


if __name__ == "__main__":
    unittest.main()
