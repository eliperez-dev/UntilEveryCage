import hashlib
import tempfile
import unittest
from pathlib import Path

from .graph_candidate_handoff import (
    CONTRACT_VERSION,
    canonical_json_bytes,
    validate_graph_candidate,
    write_graph_candidate,
)
from pipeline.common.graph_candidate import build_graph_candidate, write_graph_candidates


def candidate():
    return {
        "contract_version": CONTRACT_VERSION,
        "source_id": "synthetic.us-pilot",
        "source_record_key": "facility-001",
        "source_row": 1,
        "source_values": {"operator_id": "OP-001", "facility_name": "Synthetic Works"},
        "facilities": [{"local_ref": "facility:1", "source_identifier": {"identifier_type": "permit", "value": "FAC-001"}}],
        "organizations": [{"local_ref": "organization:1", "source_identifier": {"identifier_type": "registration", "value": "OP-001"}}],
        "relationships": [{
            "from_organization_ref": "organization:1", "target_facility_ref": "facility:1",
            "relationship_type": "operator", "assertion_status": "asserted",
            "valid_from": "2025-01-01", "valid_to": None, "observed_at": "2026-09-15T00:00:00Z",
            "confidence": 0.8, "review_state": "review_required",
        }],
        "claims": [{
            "facility_ref": "facility:1", "claim_domain": "animal_count", "claim_kind": "annual_headcount",
            "value_state": "known", "claim_value": {"count": 12, "unit": "animals"},
            "observed_at": "2026-01-01T00:00:00Z", "confidence": None,
            "support": [{"source_record_key": "facility-001"}],
        }],
        "crosswalks": [{
            "left_ref": "facility:1", "right_ref": "organization:1", "identity_scope": "source_scoped",
            "match_method": "same source registration", "confidence": 0.5,
        }],
        "publication": {
            "storage_state": "private", "privacy_status": "pending", "review_state": "review_required",
            "publication_status": "not_eligible", "release_id": None,
        },
    }


class GraphCandidateHandoffTests(unittest.TestCase):
    def test_validates_and_writes_deterministically(self):
        value = candidate()
        validate_graph_candidate(value)
        payload = canonical_json_bytes(value)
        with tempfile.TemporaryDirectory() as directory:
            manifest = write_graph_candidate(directory, value)
            self.assertEqual(manifest["sha256"], hashlib.sha256(payload).hexdigest())
            self.assertEqual(Path(directory, "graph-candidate.json").read_bytes(), payload)
            self.assertEqual(manifest["publication_state"], "private-candidate")

    def test_rejects_universal_identity_and_public_state(self):
        value = candidate()
        value["global_id"] = "do-not-accept"
        with self.assertRaisesRegex(ValueError, "universal"):
            validate_graph_candidate(value)
        value = candidate()
        value["publication"]["publication_status"] = "released"
        with self.assertRaisesRegex(ValueError, "private"):
            validate_graph_candidate(value)

    def test_requires_explicit_unknown_reason(self):
        value = candidate()
        value["relationships"] = [{
            "assertion_status": "unknown", "target_facility_ref": "facility:1",
            "observed_at": "2026-09-15T00:00:00Z",
        }]
        with self.assertRaisesRegex(ValueError, "unknown_reason"):
            validate_graph_candidate(value)

    def test_shared_builder_preserves_source_identity_and_blocks_publication(self):
        row = {
            "source_id": "fr.dgal.section-i", "source_row": 4,
            "source_record_key": "FR-1|SH|BOVINS|1",
            "source_values": {"N° d'agrément": "FR-1", "Catégorie": "SH"},
            "normalized": {"establishment_id": "FR-1", "name": "Synthetic", "activity_categories": ("slaughter",)},
        }
        candidate = build_graph_candidate(row, artifact_sha256="a" * 64, observed_at="2026-09-16T00:00:00Z")
        self.assertEqual(candidate["source_record_key"], row["source_record_key"])
        self.assertEqual(candidate["publication"]["publication_status"], "not_eligible")
        self.assertEqual(candidate["review_state"], "review_required")
        self.assertNotIn("canonical_id", candidate)
        with tempfile.TemporaryDirectory() as directory:
            manifest = write_graph_candidates(directory, [row], artifact_sha256="a" * 64, quarantined_rows=2)
            self.assertEqual(manifest["candidate_rows"], 1)
            self.assertEqual(manifest["quarantined_source_rows"], 2)
            self.assertEqual(len(Path(directory, "records.jsonl").read_text().splitlines()), 1)


if __name__ == "__main__":
    unittest.main()
