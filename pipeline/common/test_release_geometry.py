"""Focused contracts for the public geometry selection query."""

import unittest

from pipeline.common.release_geometry import GEOMETRY_MEMBERS_CTE, geometry_rows_sql


class ReleaseGeometryTests(unittest.TestCase):
    def test_frozen_geometry_requires_scoped_approval_and_current_taxonomy(self):
        sql = GEOMETRY_MEMBERS_CTE.lower()
        self.assertIn("approved_geometry_members", sql)
        self.assertIn("geometry_interpretation_status='approved'", sql)
        self.assertIn("classification_interpretation_status='approved'", sql)
        self.assertIn("excluded_display_categories", sql)
        self.assertIn("artifact.sha256=scope.artifact_sha256", sql)

    def test_geometry_classes_keep_source_precision_and_gate_provider_results(self):
        sql = GEOMETRY_MEMBERS_CTE.lower()
        self.assertIn("'source_reported'", sql)
        self.assertIn("'approximate'", sql)
        self.assertIn("provider_status}'='accepted'", sql)
        self.assertIn("confidence_band}'='high'", sql)
        self.assertIn("coordinate_review_status", sql)
        self.assertIn("'source_precision'", sql)
        self.assertIn("'evidence_id'", sql)

    def test_null_geometry_is_explicitly_unmapped_and_private_payloads_are_not_selected(self):
        sql = GEOMETRY_MEMBERS_CTE.lower()
        self.assertIn("else null::geography", sql)
        self.assertIn("jsonb_build_object('origin', 'unmapped')", sql)
        for forbidden in ("private_location_evidence", "raw_fields", "street_address", "query_text"):
            self.assertNotIn(forbidden, sql)

    def test_query_helper_requires_select_and_preserves_parameter_order(self):
        query = geometry_rows_sql("SELECT observation_id FROM eligible_geometry")
        self.assertTrue(query.lstrip().startswith("WITH approved_geometry_members"))
        self.assertEqual(query.count("%s"), 2)
        with self.assertRaises(ValueError):
            geometry_rows_sql("DELETE FROM uec.observations")


if __name__ == "__main__":
    unittest.main()
