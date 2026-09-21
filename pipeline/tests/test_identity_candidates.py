import unittest

from pipeline.common.identity_candidates import (
    CandidateSafetyError,
    build_candidate_edge,
    build_lineage_event,
    build_review_event,
    build_review_packet_manifest,
)


class IdentityCandidateTests(unittest.TestCase):
    def edge(self, **overrides):
        values = {
            "source_id": "synthetic.identity",
            "source_record_key": "row-1",
            "left_identifier": {"source_id": "us.fsis", "identifier_type": "establishment", "value": "FSIS-1"},
            "right_identifier": {"source_id": "us.fsis", "identifier_type": "establishment", "value": "FSIS-001"},
            "match_method": "name_address",
            "confidence_score": 0.78,
            "contributing_features": {"name_similarity": 0.98, "address_similarity": 0.91},
            "contradictory_evidence": [],
            "provenance": {"source_url": "https://example.invalid", "source_record": "row-1"},
            "algorithm_version": "d4-test-v1",
        }
        values.update(overrides)
        return build_candidate_edge(**values)

    def test_probable_edge_is_retained_with_disclaimer_and_safe_defaults(self):
        edge = self.edge()
        self.assertEqual(edge["confidence_band"], "probable")
        self.assertEqual(edge["review_state"], "review_required")
        self.assertFalse(edge["automatic_merge"])
        self.assertFalse(edge["transfers_claims"])
        self.assertEqual(edge["publication_status"], "not_eligible")
        self.assertIn("not a canonical identity", edge["disclaimer"])

    def test_single_signal_is_rejected_when_it_has_no_supporting_features(self):
        with self.assertRaises(CandidateSafetyError):
            self.edge(match_method="name_only", contributing_features={"name_similarity": 0.99})

    def test_aphis_fsis_bridge_requires_explicit_reviewable_bridge(self):
        with self.assertRaises(CandidateSafetyError):
            self.edge(
                left_identifier={"source_id": "us.aphis", "identifier_type": "certificate", "value": "A-1"},
                right_identifier={"source_id": "us.fsis", "identifier_type": "establishment", "value": "F-1"},
                match_method="name_address",
                confidence_score=0.95,
                contributing_features={"name_similarity": 0.95, "address_similarity": 0.91},
            )
        edge = self.edge(
            left_identifier={"source_id": "us.aphis", "identifier_type": "certificate", "value": "A-1"},
            right_identifier={"source_id": "us.fsis", "identifier_type": "establishment", "value": "F-1"},
            match_method="explicit_authoritative_crosswalk",
            confidence_score=0.99,
            contributing_features={"authoritative_crosswalk": True},
        )
        self.assertEqual(edge["review_state"], "review_required")
        self.assertTrue(edge["cross_source"])

    def test_review_and_lineage_are_append_only_event_shapes(self):
        review = build_review_event(candidate_id="candidate:1", action="defer", reason="needs human evidence", reviewer_role="maintainer")
        lineage = build_lineage_event(event_type="reversal", candidate_id="candidate:1", subject_identifier_ids=["id-1"], reason="review reversed prior decision", actor_role="maintainer")
        self.assertEqual(review["action"], "defer")
        self.assertEqual(lineage["event_type"], "reversal")
        self.assertFalse(lineage["canonical_merge_executed"])

    def test_manifest_separates_synthetic_and_human_metrics_without_rows(self):
        manifest = build_review_packet_manifest([self.edge()], synthetic_correct=1, synthetic_total=1)
        self.assertEqual(manifest["synthetic_metrics"]["precision"], 1.0)
        self.assertIsNone(manifest["human_adjudication"]["precision"])
        self.assertIsNone(manifest["human_adjudication"]["recall"])
        self.assertFalse(manifest["row_payloads_included"])
        self.assertFalse(manifest["public_exposure"])


if __name__ == "__main__":
    unittest.main()
