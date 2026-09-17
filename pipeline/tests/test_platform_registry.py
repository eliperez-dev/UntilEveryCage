import unittest

from pipeline.platform_registry import build_platform_registry, source_metadata


class PlatformRegistryTests(unittest.TestCase):
    def test_materialized_registry_scales_from_existing_source_status_inputs(self):
        registry = build_platform_registry()
        self.assertEqual(registry["source_count"], 234)
        self.assertGreaterEqual(registry["country_count"], 40)
        self.assertEqual(registry["publication_boundary"], "awaiting-owner-review; private staging may continue; no release approval or promotion is implied")
        self.assertTrue(all(country["publication"]["state"] == "blocked" for country in registry["countries"]))
        self.assertTrue(all(source["owner_review"]["state"] == "awaiting-owner-review" for source in registry["sources"]))

    def test_source_context_carries_coverage_and_attribution_without_rows(self):
        source = source_metadata("dk.smiley")
        self.assertEqual(source["country_code"], "DK")
        self.assertEqual(source["coverage"]["completeness"], "not-claimed")
        self.assertTrue(source["attribution"]["attribution_required"])
        self.assertEqual(source["readiness"]["state"], "awaiting-owner-review")
        self.assertNotIn("source_values", source)


if __name__ == "__main__":
    unittest.main()
