import unittest

from pipeline.scripts.diagnostics.compare_reviewed_demo_sources import compare_sources
from pipeline.scripts.diagnostics.data_readiness_report import build_report, DataReadinessError


def _report():
    return build_report(
        fsis={"candidate_count": 7241, "numeric_coordinate_count": 7241, "city_geocode_count": 0},
        italy={"observation_count": 41849, "provisional_identity_count": 25316, "numeric_coordinate_count": 24749, "city_only_count": 567},
        france={"section_i_count": 1449, "section_ii_count": 1068, "union_candidate_count": 2283, "numeric_coordinate_count": 0, "city_postal_count": 2283},
        denmark={"observation_count": 58766, "validation_finding_count": 57, "legacy_v1_count": 1561},
    )


class ReviewedDemoSourceComparisonTests(unittest.TestCase):
    def test_fsis_denmark_comparison_requires_explicit_pair_and_never_auto_selects(self):
        result = compare_sources(_report(), "us.fsis", "dk.smiley")
        self.assertEqual(result["selection"]["mode"], "explicit-source-pair")
        self.assertFalse(result["selection"]["auto_choice"])
        self.assertEqual(result["selection"]["left_source_id"], "us.fsis")
        self.assertEqual(result["selection"]["right_source_id"], "dk.smiley")
        self.assertEqual(result["publication"]["public_api_rows"], 0)
        self.assertIsNone(result["sources"][1]["facility_identity_count"])

    def test_same_source_and_unknown_source_fail_closed(self):
        with self.assertRaises(DataReadinessError):
            compare_sources(_report(), "dk.smiley", "dk.smiley")
        with self.assertRaises(DataReadinessError):
            compare_sources(_report(), "us.unknown", "dk.smiley")


if __name__ == "__main__":
    unittest.main()
