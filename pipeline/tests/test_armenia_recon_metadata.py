import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ARMENIA_IDS = {
    "am.snund.approved-food",
    "am.snund.farms-livestock",
    "am.environment-permits",
    "am.e-register.organizations",
    "am.armstat.livestock-statistics",
    "am.snund.inspections-experiments",
}

class ArmeniaReconMetadataTests(unittest.TestCase):
    def test_armenia_recon_is_row_free_and_automated(self):
        registry = json.loads((ROOT / "pipeline/source_registry.json").read_text(encoding="utf-8-sig"))
        self.assertTrue(ARMENIA_IDS.issubset({s["source_id"] for s in registry["sources"]}))
        recon = (ROOT / "docs/country-recon-am.md").read_text(encoding="utf-8")
        self.assertIn("no facility rows", recon.lower())
        self.assertIn("fully automated", recon.lower())
        self.assertIn("not ingestion-ready", recon.lower())

    def test_armenia_sources_are_blocked_or_not_run(self):
        status = json.loads((ROOT / "docs/source-status.json").read_text(encoding="utf-8-sig"))
        by_id = {s["source_id"]: s for s in status["sources"]}
        for source_id in ARMENIA_IDS:
            self.assertEqual(by_id[source_id]["publication_eligibility"], "blocked")
            self.assertIn(by_id[source_id]["acquisition"], {"blocked", "not_run"})

if __name__ == "__main__":
    unittest.main()
