import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SWEDEN_IDS = {
    "se.jordbruksverket.slaughterhouses",
    "se.jordbruksverket.feed-abp",
    "se.jordbruksverket.slaughter-stats",
    "se.jordbruksverket.animal-experiments",
    "se.naturvardsverket.prtr",
    "se.bolagsverket.company-api",
}


class SwedenReconMetadataTests(unittest.TestCase):
    def test_sweden_sources_are_registered_and_row_free(self):
        registry = json.loads((ROOT / "pipeline/source_registry.json").read_text(encoding="utf-8-sig"))
        self.assertTrue(SWEDEN_IDS.issubset({source["source_id"] for source in registry["sources"]}))
        recon = (ROOT / "docs/country-recon-se.md").read_text(encoding="utf-8")
        self.assertIn("No facility rows", recon)
        self.assertNotIn("Anläggnings-nummer", recon)
        self.assertIn("fully automated", recon)

    def test_sweden_sources_are_publication_blocked(self):
        status = json.loads((ROOT / "docs/source-status.json").read_text(encoding="utf-8-sig"))
        by_id = {source["source_id"]: source for source in status["sources"]}
        for source_id in SWEDEN_IDS:
            self.assertEqual(by_id[source_id]["publication_eligibility"], "blocked")
            self.assertEqual(by_id[source_id]["acquisition"], "not_run")


if __name__ == "__main__":
    unittest.main()