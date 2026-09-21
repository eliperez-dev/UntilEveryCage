"""CI-discovered consistency checks for the source-status evidence baseline."""

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class SourceStatusBaselineTests(unittest.TestCase):
    def load_status(self):
        return json.loads((ROOT / "docs" / "source-status.json").read_text(encoding="utf-8"))

    def load_registry_ids(self):
        registry = json.loads((ROOT / "pipeline" / "source_registry.json").read_text(encoding="utf-8"))
        return {source["source_id"] for source in registry["sources"]}

    def test_status_covers_exactly_the_source_registry_ids(self):
        payload = self.load_status()
        ids = {source["source_id"] for source in payload["sources"]}
        self.assertEqual(ids, self.load_registry_ids())

    def test_status_values_are_explicit_and_conservative(self):
        payload = self.load_status()
        vocab = payload["status_vocabulary"]
        for source in payload["sources"]:
            self.assertIn(source["metadata"], vocab["metadata"])
            self.assertIn(source["acquisition"], vocab["acquisition"])
            self.assertIn(source["runtime_health"], vocab["runtime_health"])
            self.assertIn(source["publication_eligibility"], vocab["publication_eligibility"])
            self.assertTrue(source["evidence"])
            self.assertTrue(source["next_action"])
        self.assertTrue(all(source["runtime_health"] != "healthy" for source in payload["sources"]))
        self.assertTrue(all(source["publication_eligibility"] != "eligible" for source in payload["sources"]))

    def test_evidence_paths_exist_and_exclude_private_roots(self):
        payload = self.load_status()
        for source in payload["sources"]:
            for evidence in source["evidence"]:
                self.assertFalse(evidence.startswith((".codex/", "data/terms-reviews/", "philosophy/")))
                self.assertTrue((ROOT / evidence).exists(), evidence)


if __name__ == "__main__":
    unittest.main()
