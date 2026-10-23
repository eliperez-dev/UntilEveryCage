import json
import tempfile
import unittest
from pathlib import Path

from pipeline.common.graph_candidates import build_identifier_graph_candidate, write_graph_candidates
from pipeline.common.d5_connection_analysis import _observed_from_row, _shared_typed_identifier
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
        self.assertEqual(candidate["organizations"][0]["source_identifier"]["id_namespace"], "it.tax-authority.vat")
        self.assertEqual(candidate["publication"]["publication_status"], "not_eligible")
        with tempfile.TemporaryDirectory() as directory:
            manifest = write_graph_candidates(directory, [candidate])
            self.assertEqual(manifest["operator_relationship_candidates"], 0)
            payload = Path(directory, "graph-candidates.jsonl").read_text(encoding="utf-8")
            self.assertEqual(len(payload.splitlines()), 1)
            self.assertNotIn("global_id", payload)

    def test_only_documented_italian_vat_authority_namespace_can_cross_sources(self):
        def candidate(source_id):
            return build_identifier_graph_candidate(
                source_id=source_id, source_record_key="row", source_values={},
                facility_identifier=("recognition", "R-1"),
                organization_identifier=("italian_vat", "IT-123"), observed_at="2026-10-23T00:00:00Z",
            )
        a = candidate("it.853-2004")["organizations"][0]["source_identifier"]
        b = candidate("it.1069-2009")["organizations"][0]["source_identifier"]
        unrelated = candidate("other.source")["organizations"][0]["source_identifier"]
        self.assertEqual((a["identifier_type"], a["id_namespace"], a["value"]),
                         (b["identifier_type"], b["id_namespace"], b["value"]))
        self.assertNotEqual((a["identifier_type"], a["id_namespace"], a["value"]),
                            (unrelated["identifier_type"], unrelated["id_namespace"], unrelated["value"]))
        left = _observed_from_row(candidate("it.853-2004"))
        right = _observed_from_row(candidate("it.1069-2009"))
        other = _observed_from_row(candidate("other.source"))
        self.assertTrue(_shared_typed_identifier(left, right))
        self.assertFalse(_shared_typed_identifier(left, other))

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
