import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GEORGIA_IDS = {
    "ge.nfa.approved-food",
    "ge.nfa.farms-livestock",
    "ge.nea.environment-permits",
    "ge.napr.organizations",
    "ge.geostat.slaughter-statistics",
    "ge.nfa.inspections-experiments",
}

class GeorgiaReconMetadataTests(unittest.TestCase):
    def test_georgia_recon_is_row_free_and_automated(self):
        registry = json.loads((ROOT / "pipeline/source_registry.json").read_text(encoding="utf-8-sig"))
        self.assertTrue(GEORGIA_IDS.issubset({s["source_id"] for s in registry["sources"]}))
        recon = (ROOT / "docs/country-recon-ge.md").read_text(encoding="utf-8")
        self.assertIn("no facility rows", recon.lower())
        self.assertIn("fully automated", recon.lower())
        self.assertIn("not ingestion-ready", recon.lower())

    def test_georgia_sources_are_blocked_or_not_run(self):
        status = json.loads((ROOT / "docs/source-status.json").read_text(encoding="utf-8-sig"))
        by_id = {s["source_id"]: s for s in status["sources"]}
        for source_id in GEORGIA_IDS:
            self.assertEqual(by_id[source_id]["publication_eligibility"], "blocked")
            self.assertIn(by_id[source_id]["acquisition"], {"blocked", "not_run"})

if __name__ == "__main__":
    unittest.main()
