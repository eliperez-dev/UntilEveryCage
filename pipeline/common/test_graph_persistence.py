import hashlib
import json
import unittest
import uuid
from pathlib import Path

from pipeline.common.graph_persistence import (
    GraphPersistenceError,
    load_evidence_handoff,
    load_graph_candidate_handoff,
    require_disposable_graph_database,
)
from pipeline.contracts.graph_candidate_handoff import canonical_json_bytes


TEST_TMP = Path(__file__).parents[2] / ".tmp" / "d4-graph-persistence-tests"


def test_directory() -> Path:
    # Windows CI in this workspace applies a restrictive ACL to Python's
    # mode-0700 tempfile directories.  These are synthetic-only test files in
    # the ignored workspace .tmp area, so leave the disposable directories for
    # the existing cache cleanup rather than weakening the ACL.
    directory = TEST_TMP / uuid.uuid4().hex
    directory.mkdir(parents=True, exist_ok=False)
    return directory


def candidate(source_id="synthetic.graph"):
    return {
        "contract_version": "graph-candidate-handoff-v1",
        "source_id": source_id,
        "source_record_key": "record-1",
        "source_row": 1,
        "source_values": {"name": "Synthetic facility"},
        "facilities": [{"local_ref": "facility:1", "source_identifier": {"identifier_type": "permit", "value": "FAC-1", "identity_scope": "source_scoped"}}],
        "organizations": [],
        "relationships": [],
        "claims": [{"claim_domain": "identity", "claim_kind": "source_label", "facility_ref": "facility:1", "value_state": "known", "value": "Synthetic facility", "observed_at": "2026-01-01T00:00:00Z", "confidence": 0.55, "review_state": "review_required", "support": [{"source_record_key": "record-1"}]}],
        "crosswalks": [],
        "contradiction_state": "none-observed",
        "review_state": "review_required",
        "publication": {"storage_state": "private", "privacy_status": "pending", "review_state": "review_required", "publication_status": "not_eligible", "release_id": None},
    }


class GraphPersistenceContractTests(unittest.TestCase):
    def test_loopback_non_default_disposable_guard(self):
        require_disposable_graph_database("postgresql://uec:pw@localhost:5433/uec-test", True)
        for url in ("postgresql://uec:pw@example.com:5433/uec-test", "postgresql://uec:pw@localhost:5432/uec-test", "postgresql://uec:pw@localhost:5433/app"):
            with self.assertRaises(GraphPersistenceError):
                require_disposable_graph_database(url, True)

    def test_graph_candidate_loader_accepts_private_jsonl_and_is_deterministic(self):
        row = candidate()
        payload = canonical_json_bytes(row)
        root = test_directory()
        graph = root / "graph-candidates"
        graph.mkdir()
        (graph / "records.jsonl").write_bytes(payload)
        (graph / "manifest.json").write_text(json.dumps({
            "schema_version": "private-graph-candidate-set-v1",
            "contract_version": "graph-candidate-handoff-v1",
            "source_id": "synthetic.graph",
            "records_sha256": hashlib.sha256(payload).hexdigest(),
            "storage_state": "private", "review_state": "review_required", "publication_status": "not_eligible",
        }), encoding="utf-8")
        manifest, rows, digest = load_graph_candidate_handoff(graph)
        self.assertEqual(manifest["source_kind"], "facility_master")
        self.assertEqual(rows, [row])
        self.assertEqual(digest, hashlib.sha256(payload).hexdigest())

    def test_graph_loader_rejects_global_identity_and_released_manifest(self):
        row = candidate()
        row["global_id"] = "do-not-accept"
        root = test_directory()
        (root / "records.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
        (root / "manifest.json").write_text(json.dumps({"source_id": "synthetic.graph", "publication_status": "not_eligible"}), encoding="utf-8")
        with self.assertRaises(GraphPersistenceError):
            load_graph_candidate_handoff(root)
        row = candidate()
        root = test_directory()
        payload = canonical_json_bytes(row)
        (root / "records.jsonl").write_bytes(payload)
        (root / "manifest.json").write_text(json.dumps({"source_id": "synthetic.graph", "records_sha256": hashlib.sha256(payload).hexdigest(), "publication_status": "released"}), encoding="utf-8")
        with self.assertRaises(GraphPersistenceError):
            load_graph_candidate_handoff(root)

    def test_evidence_loader_requires_evidence_scope_and_checksum(self):
        row = {"source_id": "us.aphis", "source_row": 2, "source_record_key": "registrations|certificate=1", "source_values": {}, "normalized": {"event_type": "registrations", "source_observation_key": "certificate=1", "linkage_candidates": []}}
        payload = (json.dumps(row, sort_keys=True) + "\n").encode()
        root = test_directory()
        (root / "records.jsonl").write_bytes(payload)
        (root / "manifest.json").write_text(json.dumps({
            "contract_version": "us-aphis-observation-handoff-v1", "source_id": "us.aphis", "entity_scope": "evidence_event",
            "normalized_rows": 1, "normalized_sha256": hashlib.sha256(payload).hexdigest(), "release_state": "not-created", "publication_state": "private-candidate",
        }), encoding="utf-8")
        manifest, rows, digest = load_evidence_handoff(root)
        self.assertEqual(manifest["source_kind"], "evidence_event")
        self.assertEqual(len(rows), 1)
        self.assertEqual(digest, hashlib.sha256(payload).hexdigest())
        (root / "manifest.json").write_text(json.dumps({"contract_version": "us-aphis-observation-handoff-v1", "source_id": "us.aphis", "entity_scope": "facility_master", "normalized_rows": 1, "normalized_sha256": hashlib.sha256(payload).hexdigest(), "release_state": "not-created", "publication_state": "private-candidate"}), encoding="utf-8")
        with self.assertRaises(GraphPersistenceError):
            load_evidence_handoff(root)


if __name__ == "__main__":
    unittest.main()
