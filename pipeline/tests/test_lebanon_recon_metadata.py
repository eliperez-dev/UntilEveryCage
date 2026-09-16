import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LEBANON_IDS = {
    "lb.moa.approved-food", "lb.moa.farms-livestock", "lb.moe.environment-eia",
    "lb.justice.companies", "lb.industry.food-guide", "lb.cas.livestock-statistics",
}

class LebanonReconMetadataTests(unittest.TestCase):
    def test_lebanon_is_row_free_and_not_ingestion_ready(self):
        registry = json.loads((ROOT / "pipeline/source_registry.json").read_text(encoding="utf-8-sig"))
        self.assertTrue(LEBANON_IDS.issubset({s["source_id"] for s in registry["sources"]}))
        recon = (ROOT / "docs/country-recon-lb.md").read_text(encoding="utf-8").lower()
        self.assertIn("no facility rows", recon)
        self.assertIn("not ingestion-ready", recon)

    def test_lebanon_sources_are_blocked_or_not_run(self):
        status = json.loads((ROOT / "docs/source-status.json").read_text(encoding="utf-8-sig"))
        by_id = {s["source_id"]: s for s in status["sources"]}
        for source_id in LEBANON_IDS:
            self.assertEqual(by_id[source_id]["publication_eligibility"], "blocked")
            self.assertIn(by_id[source_id]["acquisition"], {"blocked", "not_run"})

if __name__ == "__main__":
    unittest.main()
