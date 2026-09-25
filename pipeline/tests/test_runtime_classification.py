import unittest

from pipeline.source_runtime_classification import (
    RuntimeClassificationError,
    build_runtime_classification_index,
    require_production_preview_source,
)


VERIFIED_PRIVATE_E2E = {
    "au.sa.epa.licensed-activities",
    "be.locations",
    "fr.dgal.section-i",
    "fr.dgal.section-ii",
    "it.853-2004",
    "it.1069-2009",
    "us.fsis",
}


class RuntimeClassificationTests(unittest.TestCase):
    def test_verified_private_e2e_sources_are_classified_without_public_release(self):
        index = build_runtime_classification_index()
        sources = index["sources"]
        classified = {
            source_id for source_id, row in sources.items()
            if row["classification"] == "production-e2e"
        }
        self.assertEqual(classified, VERIFIED_PRIVATE_E2E)
        self.assertTrue(all(sources[source_id]["private_preview_enabled"] for source_id in classified))
        self.assertTrue(all(not row["public_release"] for row in sources.values()))

    def test_known_blocked_unlisted_source_is_not_production_e2e(self):
        sources = build_runtime_classification_index()["sources"]
        self.assertEqual(sources["mx.locations"]["classification"], "research-blocked")
        with self.assertRaises(RuntimeClassificationError):
            require_production_preview_source("mx.locations")

    def test_each_enabled_source_must_carry_the_private_production_boundary(self):
        # The production allowlist is validated at load time against the joined
        # status and registry inputs; the shared helper also fails closed for typos.
        self.assertEqual(require_production_preview_source("be.locations")["public_release"], False)
        with self.assertRaises(RuntimeClassificationError):
            require_production_preview_source("unknown.source")


if __name__ == "__main__":
    unittest.main()
