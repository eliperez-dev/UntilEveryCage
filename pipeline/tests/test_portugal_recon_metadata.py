import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
IDS = {
    "pt.dgav.approved-food",
    "pt.dgav.abp",
    "pt.dgav.feed",
    "pt.apambiente.tua",
    "pt.ifap.snira",
    "pt.ine.animal-production",
}


class PortugalReconMetadataTests(unittest.TestCase):
    def test_row_free_recon_and_registry_entries(self):
        registry = json.loads((ROOT / "pipeline" / "source_registry.json").read_text(encoding="utf-8"))
        self.assertTrue(IDS.issubset({source["source_id"] for source in registry["sources"]}))
        document = (ROOT / "docs" / "country-recon-pt.md").read_text(encoding="utf-8")
        self.assertIn("row-free", document)
        self.assertIn("fully automated", document)
        self.assertNotIn("NCV |", document)

    def test_publication_remains_blocked(self):
        status = json.loads((ROOT / "docs" / "source-status.json").read_text(encoding="utf-8"))
        by_id = {source["source_id"]: source for source in status["sources"]}
        for source_id in IDS:
            self.assertEqual(by_id[source_id]["publication_eligibility"], "blocked")


if __name__ == "__main__":
    unittest.main()
