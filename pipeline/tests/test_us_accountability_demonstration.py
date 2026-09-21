import json
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[2]
MANIFEST = ROOT / "data/manifests/us-real-accountability-demonstration-2026-09-18.json"


class UsAccountabilityDemonstrationTests(unittest.TestCase):
    def test_real_demonstration_is_private_source_bound_and_row_free(self):
        report = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(report["corpus_state"], "private-regression-only")
        self.assertEqual(report["publication_eligibility"], "blocked")
        self.assertEqual(report["graph"]["cross_source_identity_joins_attempted"], 0)
        self.assertEqual(report["graph"]["name_address_phone_coordinate_joins_attempted"], 0)
        self.assertGreater(report["graph"]["accepted_relationships"], 0)
        self.assertGreater(report["graph"]["quarantined_relationships"], 0)
        self.assertEqual(report["graph"]["all_candidates"]["auto_merge"], False)
        self.assertEqual(report["privacy_and_provenance"]["coordinates"], "not used for identity; geocoding disabled")
        self.assertTrue(report["privacy_and_provenance"]["source_hashes"])
        self.assertTrue(all("name" not in json.dumps(value).lower() for value in report["privacy_and_provenance"]["source_hashes"].values()))


if __name__ == "__main__":
    unittest.main()
