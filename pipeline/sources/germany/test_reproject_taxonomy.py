import unittest

from pipeline.sources.germany.reproject_taxonomy import project_candidate


class GermanyTaxonomyReprojectionTests(unittest.TestCase):
    def test_supported_codes_map_and_unknown_values_remain_partial(self):
        projected = project_candidate({
            "source_activity_codes": ["SH", "CP", "ZV", "UNKNOWN-DE"],
            "source_activity_labels": ["source label retained"],
        })
        self.assertEqual(projected["taxonomy_mapping_status"], "partial")
        self.assertEqual(projected["taxonomy_primaries"], ["slaughter", "processing_and_preparation"])
        self.assertEqual(projected["taxonomy_assignments"][0]["source_label"], "source label retained")
        self.assertEqual(projected["crosswalk_version"], "de-bltu-source-crosswalk-v1")

    def test_unrecognized_only_codes_do_not_receive_invented_category(self):
        projected = project_candidate({"source_activity_codes": ["UNKNOWN-DE"]})
        self.assertEqual(projected["taxonomy_mapping_status"], "unmapped")
        self.assertEqual(projected["taxonomy_primaries"], [])


if __name__ == "__main__":
    unittest.main()
