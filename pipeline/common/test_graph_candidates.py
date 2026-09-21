import json
import tempfile
import unittest
from pathlib import Path

from pipeline.common.graph_candidates import build_identifier_graph_candidate, write_graph_candidates
from pipeline.contracts.graph_candidate_handoff import validate_graph_candidate


class GraphCandidateGenerationTests(unittest.TestCase):
    def test_explicit_facility_operator_identifiers_emit_review_required_edge(self):
        candidate = build_identifier_graph_candidate(
            source_id="it.853-2004",
            source_record_key="REC|ACT|1",
            source_values={"recognition": "REC", "vat": "VAT"},
            facility_identifier=("eu_recognition_number", "REC"),
            organization_identifier=("italian_vat", "VAT"),
            observed_at="2026-09-17T00:00:00Z",
            source_row=2,
        )
        validate_graph_candidate(candidate)
        self.assertEqual(len(candidate["relationships"]), 1)
        self.assertEqual(candidate["relationships"][0]["relationship_type"], "operator")
        self.assertEqual(candidate["relationships"][0]["review_state"], "review_required")
        self.assertEqual(candidate["publication"]["publication_status"], "not_eligible")
        with tempfile.TemporaryDirectory() as directory:
            manifest = write_graph_candidates(directory, [candidate])
            self.assertEqual(manifest["operator_relationship_candidates"], 1)
            payload = Path(directory, "graph-candidates.jsonl").read_text(encoding="utf-8")
            self.assertEqual(len(payload.splitlines()), 1)
            self.assertNotIn("global_id", payload)


if __name__ == "__main__":
    unittest.main()
