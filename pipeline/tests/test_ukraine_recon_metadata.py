import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UKRAINE_IDS = {
    "ua.dpss.approved-food",
    "ua.farm-aquaculture",
    "ua.environment-permits",
    "ua.edr.organizations",
    "ua.ukrstat.statistics",
    "ua.inspections-experiments",
}


class UkraineReconMetadataTests(unittest.TestCase):
    def test_ukraine_recon_is_row_free_and_automated(self):
        registry = json.loads((ROOT / "pipeline/source_registry.json").read_text(encoding="utf-8-sig"))
        self.assertTrue(UKRAINE_IDS.issubset({s["source_id"] for s in registry["sources"]}))
        recon = (ROOT / "docs/country-recon-ua.md").read_text(encoding="utf-8")
        self.assertIn("no facility rows", recon.lower())
        self.assertIn("fully automated", recon.lower())
        self.assertIn("wartime", recon.lower())
        self.assertIn("operationally sensitive", recon.lower())

    def test_ukraine_sources_are_blocked_or_not_run(self):
        status = json.loads((ROOT / "docs/source-status.json").read_text(encoding="utf-8-sig"))
        by_id = {s["source_id"]: s for s in status["sources"]}
        for source_id in UKRAINE_IDS:
            self.assertEqual(by_id[source_id]["publication_eligibility"], "blocked")
            self.assertIn(by_id[source_id]["acquisition"], {"blocked", "not_run"})


if __name__ == "__main__":
    unittest.main()
