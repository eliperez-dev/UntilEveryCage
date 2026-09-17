import unittest

from .review_metrics import build_private_review_metrics


class ReviewMetricsTests(unittest.TestCase):
    def test_facility_observation_and_precision_metrics_are_aggregate_only(self):
        metrics = build_private_review_metrics(
            [
                {"source_record_key": "a", "normalized": {"recognition_number": "R", "classification_state": "source-category-preserved", "coordinate_state": "source-value-present-pending-review", "coordinate_precision": "source-precision-unknown", "coordinate_gate": "review_required"}},
                {"source_record_key": "b", "normalized": {"recognition_number": "R", "classification_state": "unknown", "coordinate_state": "unknown", "coordinate_gate": "review_required"}},
            ],
            [{"record": {"source_record_key": "c", "normalized": {"recognition_number": "R"}}, "reasons": ["ambiguous"]}],
        )
        facility = metrics["facility_observation"]
        self.assertEqual(facility["input_observations"], 3)
        self.assertEqual(facility["distinct_provisional_facility_keys"], 1)
        self.assertEqual(facility["repeated_provisional_facility_groups"], 1)
        self.assertEqual(metrics["geospatial"]["precision_counts"]["source-precision-unknown"], 1)
        self.assertNotIn("R", str(metrics))
        self.assertNotIn("source_record_key", str(metrics))


if __name__ == "__main__":
    unittest.main()
