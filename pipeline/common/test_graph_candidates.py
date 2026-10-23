import json
import tempfile
import unittest
from pathlib import Path

from pipeline.common.graph_candidates import build_identifier_graph_candidate, write_graph_candidates
from pipeline.contracts.graph_candidate_handoff import validate_graph_candidate


class GraphCandidateGenerationTests(unittest.TestCase):
    def test_source_identifier_cooccurrence_does_not_invent_operator_assertion(self):
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
        self.assertEqual(candidate["relationships"], [])
        self.assertEqual(candidate["facilities"][0]["source_identifier"]["id_namespace"], "it.853-2004")
        self.assertEqual(candidate["organizations"][0]["source_identifier"]["id_namespace"], "it.853-2004")
        self.assertEqual(candidate["publication"]["publication_status"], "not_eligible")
        with tempfile.TemporaryDirectory() as directory:
            manifest = write_graph_candidates(directory, [candidate])
            self.assertEqual(manifest["operator_relationship_candidates"], 0)
            payload = Path(directory, "graph-candidates.jsonl").read_text(encoding="utf-8")
            self.assertEqual(len(payload.splitlines()), 1)
            self.assertNotIn("global_id", payload)

    def test_explicit_operator_assertion_is_preserved(self):
        candidate = build_identifier_graph_candidate(
            source_id="test.source", source_record_key="row-1", source_values={},
            facility_identifier=("facility_id", "F-1"), organization_identifier=("operator_id", "O-1"),
            observed_at="2026-09-17T00:00:00Z", operator_asserted=True,
        )
        validate_graph_candidate(candidate)
        self.assertEqual(candidate["relationships"][0]["relationship_type"], "operator")


if __name__ == "__main__":
    unittest.main()
