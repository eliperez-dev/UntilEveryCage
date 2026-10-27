from __future__ import annotations

import unittest

from pipeline.taxonomy_crosswalk import (
    CROSSWALK_VERSION,
    crosswalk_document,
    project_observation,
    reproject,
)


class LaunchCountryTaxonomyTests(unittest.TestCase):
    def test_mexico_scian_codes_map_directly_and_unknown_codes_stay_unmapped(self):
        expected = {
            "311611": ("slaughter", "slaughter"),
            "311612": ("processing", "processing_and_preparation"),
            "311613": ("processing", "processing_and_preparation"),
            "311614": ("processing", "processing_and_preparation"),
        }
        for code, (leaf, primary) in expected.items():
            source_values = {"CLASE_ACTIVIDAD_ID": code, "Nombre": "Synthetic source name"}
            record = {"source_id": "mx.locations", "source_values": source_values,
                      "normalized": {"activity_class_id": code}}
            projected = project_observation(record)
            self.assertEqual(projected["taxonomy_mapping_status"], "mapped")
            self.assertEqual(projected["taxonomy_mapping_method"], "direct")
            self.assertEqual(projected["taxonomy_assignments"][0]["leaf_activity"], leaf)
            self.assertEqual(projected["taxonomy_assignments"][0]["primary"], primary)
            self.assertEqual(projected["taxonomy_assignments"][0]["source_code"], code)
            self.assertEqual(record["source_values"], source_values)

        unknown = project_observation({"source_id": "mx.locations", "normalized": {"activity_class_id": "311615"}})
        self.assertEqual(unknown["taxonomy_mapping_status"], "unmapped")
        self.assertEqual(unknown["taxonomy_assignments"], [])
        partial = project_observation({"source_id": "mx.locations", "normalized": {
            "activity_class_id": ["311611", "311615"]}})
        self.assertEqual(partial["taxonomy_mapping_status"], "partial")
        self.assertEqual({item["leaf_activity"] for item in partial["taxonomy_assignments"]}, {"slaughter"})
        multi = project_observation({"source_id": "mx.locations", "normalized": {
            "activity_class_id": ["311611", "311612"]}})
        self.assertEqual({item["leaf_activity"] for item in multi["taxonomy_assignments"]},
                         {"slaughter", "processing"})
        self.assertEqual(crosswalk_document("mx.locations")["crosswalk_version"],
                         "mx-denue-source-crosswalk-v1")

    def test_new_zealand_maps_multiple_native_activities_and_preserves_evidence(self):
        source_values = {
            "Programme Type": "Micro Abattoir",
            "Primary": "Meat Processing",
            "Secondary Process": "Transport and storage",
            "Product/Material": "Meat products",
            "Number of Locations": "2",
        }
        record = {
            "source_id": "nz.locations",
            "source_values": source_values,
            "normalized": {
                "programme_type": source_values["Programme Type"],
                "primary_activity": source_values["Primary"],
                "secondary_activity": source_values["Secondary Process"],
                "product_material": source_values["Product/Material"],
                "location_count": 2,
            },
        }
        projected = project_observation(record)
        assignments = projected["taxonomy_assignments"]
        self.assertEqual(projected["taxonomy_mapping_status"], "mapped")
        self.assertEqual(projected["taxonomy_mapping_method"], "derived")
        self.assertEqual({item["leaf_activity"] for item in assignments},
                         {"slaughter", "processing", "logistics_and_storage"})
        self.assertEqual({item["method"] for item in assignments}, {"derived"})
        self.assertEqual(projected["taxonomy_display_category"], "slaughter")
        self.assertTrue(all(item["source_label"] for item in assignments))
        reprojected, _ = reproject([record])
        self.assertEqual(reprojected[0]["source_values"], source_values)
        self.assertEqual(reprojected[0]["normalized"]["location_count"], 2)
        document = crosswalk_document("nz.locations")
        self.assertEqual(document["crosswalk_version"], "nz-mpi-rmp-source-crosswalk-v1")
        self.assertTrue(all(rule["method"] == "derived" for rule in document["rules"]))

    def test_new_zealand_native_production_and_butcher_categories_map_conservatively(self):
        production = project_observation({
            "source_id": "nz.locations",
            "normalized": {
                "programme_type": "Chicken producers",
                "primary_activity": "Farm dairy production",
                "secondary_activity": "Egg production",
            },
        })
        self.assertEqual(production["taxonomy_mapping_status"], "mapped")
        self.assertEqual([item["leaf_activity"] for item in production["taxonomy_assignments"]],
                         ["animal_production"])
        self.assertEqual(production["taxonomy_primaries"], ["animal_keeping_and_production"])

        butcher = project_observation({
            "source_id": "nz.locations",
            "normalized": {"programme_type": "Dual operator butcher"},
        })
        self.assertEqual(butcher["taxonomy_mapping_status"], "mapped")
        self.assertEqual(butcher["taxonomy_assignments"][0]["leaf_activity"], "butcher_retail")
        self.assertEqual(butcher["taxonomy_primaries"], ["other_regulated_premises"])

        cross_field_processing = project_observation({
            "source_id": "nz.locations",
            "normalized": {"product_material": "Fish", "primary_activity": "Processing"},
        })
        self.assertEqual(cross_field_processing["taxonomy_assignments"][0]["leaf_activity"], "processing")
        self.assertIn("normalized.product_material",
                      cross_field_processing["taxonomy_assignments"][0]["source_label_reference"])

    def test_generic_custom_and_substring_near_matches_do_not_map(self):
        generic = project_observation({
            "source_id": "nz.locations", "normalized": {"programme_type": "Custom"},
        })
        self.assertEqual(generic["taxonomy_mapping_status"], "unmapped")
        self.assertEqual(generic["taxonomy_assignments"], [])

        near_match = project_observation({
            "source_id": "nz.locations",
            "normalized": {
                "programme_type": "Freshery wholesale",
                "primary_activity": "Fresh Fishery Products Plant",
                "secondary_activity": "Pretransportation",
            },
        })
        self.assertEqual(near_match["taxonomy_mapping_status"], "unmapped")
        self.assertEqual(near_match["taxonomy_assignments"], [])

    def test_new_source_specific_versions_do_not_bump_global_version(self):
        self.assertEqual(CROSSWALK_VERSION, "uec-source-crosswalk-v7")
        self.assertEqual(crosswalk_document("us.fsis")["crosswalk_version"], CROSSWALK_VERSION)


if __name__ == "__main__":
    unittest.main()
