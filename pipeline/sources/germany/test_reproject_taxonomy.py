import unittest

from pipeline.sources.germany.reproject_taxonomy import project_candidate
from pipeline.taxonomy.contract import TAXONOMY_VERSION, TaxonomyAssignment, canonical_assignments
from pipeline.taxonomy_crosswalk import persistence_assignments


class GermanyTaxonomyReprojectionTests(unittest.TestCase):
    def test_supported_codes_map_and_unknown_values_remain_partial(self):
        projected = project_candidate({
            "source_activity_codes": ["SH", "CP", "ZV", "UNKNOWN-DE"],
            "source_activity_labels": ["source label retained"],
        })
        self.assertEqual(projected["taxonomy_mapping_status"], "partial")
        self.assertEqual(projected["taxonomy_primaries"], ["slaughter", "processing_and_preparation"])
        self.assertEqual({row["source_code"] for row in projected["taxonomy_assignments"]}, {"SH", "CP", "ZV"})
        self.assertTrue(all(row["source_code_reference"] == "normalized.activity_codes"
                            for row in projected["taxonomy_assignments"]))
        self.assertEqual(projected["crosswalk_version"], "de-bltu-source-crosswalk-v1")

    def test_same_leaf_codes_keep_distinct_provenance_and_pass_persistence_contract(self):
        projected = project_candidate({
            "source_activity_codes": ["EPC", "PP", "PC", "PP"],
            "source_activity_labels": ["labels remain in candidate evidence"],
        })
        rows = persistence_assignments(projected)
        self.assertEqual(len(rows), 3)
        self.assertEqual({row["source_code"] for row in rows}, {"EPC", "PP", "PC"})
        assignments = [TaxonomyAssignment(
            primary_key=row["primary_key"], leaf_key=row["leaf_key"], leaf_label=row["leaf_label"],
            source_code_reference=row["source_code_reference"], source_label_reference=row["source_label_reference"],
            source_code=row["source_code"], source_label=row["source_label"],
            method=row["mapping_method"], status=row["mapping_status"],
            observation_id="observation", source_record_id="candidate", artifact_id="snapshot",
            taxonomy_version=TAXONOMY_VERSION, crosswalk_version=projected["crosswalk_version"],
            ruleset_version=projected["crosswalk_version"],
        ) for row in rows]
        self.assertEqual(len(canonical_assignments(assignments)), 3)

    def test_unrecognized_only_codes_do_not_receive_invented_category(self):
        projected = project_candidate({"source_activity_codes": ["UNKNOWN-DE"]})
        self.assertEqual(projected["taxonomy_mapping_status"], "unmapped")
        self.assertEqual(projected["taxonomy_primaries"], [])


if __name__ == "__main__":
    unittest.main()
