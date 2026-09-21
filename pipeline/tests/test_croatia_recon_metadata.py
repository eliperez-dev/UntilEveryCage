import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

class CroatiaReconMetadataTests(unittest.TestCase):
    def test_row_free_croatia_recon_is_present(self):
        text = (ROOT / "docs" / "country-recon-hr.md").read_text(encoding="utf-8")
        self.assertIn("row-free", text)
        self.assertIn("fully automated", text)
        self.assertIn("Recommended next country: Romania", text)

    def test_croatia_sources_have_conservative_status(self):
        registry = json.loads((ROOT / "pipeline" / "source_registry.json").read_text(encoding="utf-8"))
        status = json.loads((ROOT / "docs" / "source-status.json").read_text(encoding="utf-8"))
        ids = {source["source_id"] for source in registry["sources"] if source["source_id"].startswith("hr.")}
        self.assertEqual(ids, {source["source_id"] for source in status["sources"] if source["source_id"].startswith("hr.")})
        self.assertEqual(len(ids), 6)
        for source in status["sources"]:
            if source["source_id"].startswith("hr."):
                self.assertEqual(source["publication_eligibility"], "blocked")
                self.assertNotEqual(source["runtime_health"], "healthy")

if __name__ == "__main__":
    unittest.main()
