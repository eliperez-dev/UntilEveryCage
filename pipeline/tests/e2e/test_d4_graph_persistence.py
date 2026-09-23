"""Docker-backed D4 persistence proof using synthetic private handoffs only."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path

import psycopg

from pipeline.common.d4_graph_e2e import D4_FACILITY_SOURCE_IDS, D3_EVIDENCE_SOURCE_IDS
from pipeline.common.graph_persistence import import_evidence_events, import_graph_candidates
from pipeline.contracts.graph_candidate_handoff import canonical_json_bytes

from .fixture import E2EEnvironment


@unittest.skipUnless(
    os.environ.get("UEC_RUN_E2E") == "1",
    "set UEC_RUN_E2E=1 to run Docker-backed E2E tests",
)
class D4GraphPersistenceE2ETests(unittest.TestCase):
    """Prove the real importer against disposable PostGIS, without real rows."""

    @classmethod
    def setUpClass(cls):
        cls.env = E2EEnvironment().start()
        cls.temp = tempfile.TemporaryDirectory(prefix="uec-d4-graph-")
        cls.root = Path(cls.temp.name)
        cls.handoffs: dict[tuple[str, str], Path] = {}
        for index, source_id in enumerate(D4_FACILITY_SOURCE_IDS):
            cls.handoffs[(source_id, "facility")] = cls._write_facility(source_id, index)
        for index, source_id in enumerate(D3_EVIDENCE_SOURCE_IDS):
            cls.handoffs[(source_id, "evidence")] = cls._write_evidence(source_id, index)

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "temp", None):
            cls.temp.cleanup()
        if getattr(cls, "env", None):
            cls.env.stop()

    @classmethod
    def _write_facility(cls, source_id: str, index: int) -> Path:
        observed = "2026-09-21T00:00:00Z"
        candidate = {
            "contract_version": "graph-candidate-handoff-v1",
            "source_id": source_id,
            "source_record_key": f"d4-synthetic-{index}",
            "source_row": 1,
            "source_values": {"name": f"D4 Synthetic Facility {index}"},
            "facilities": [{"local_ref": "facility:1", "source_identifier": {
                "identifier_type": "synthetic-permit", "value": f"D4-FAC-{index}",
                "identity_scope": "source_scoped",
            }}],
            "organizations": [{"local_ref": "organization:1", "source_identifier": {
                "identifier_type": "synthetic-operator", "value": f"D4-ORG-{index}",
                "identity_scope": "source_scoped",
            }}],
            "relationships": [{
                "relationship_type": "operator", "from_organization_ref": "organization:1",
                "target_facility_ref": "facility:1", "observed_at": observed,
                "confidence": 0.55, "review_state": "review_required",
            }],
            "claims": [{
                "claim_domain": "identity", "claim_kind": "source_label",
                "facility_ref": "facility:1", "value_state": "known",
                "value": f"D4 Synthetic Facility {index}", "observed_at": observed,
                "confidence": 0.55, "review_state": "review_required",
                "support": [{"source_record_key": f"d4-synthetic-{index}"}],
            }],
            "crosswalks": [],
            "contradiction_state": "none-observed",
            "review_state": "review_required",
            "publication": {"storage_state": "private", "privacy_status": "pending",
                            "review_state": "review_required", "publication_status": "not_eligible",
                            "release_id": None},
        }
        if index == 0:
            # Exercise the D6 matcher handoff without implementing matching in
            # the importer.  The endpoints stay source-qualified and the
            # candidate remains private/review-required.
            candidate["connection_candidates"] = [{
                "from": {"entity_type": "organization", "source_id": source_id,
                          "identifier_type": "synthetic-operator", "source_identifier": f"D4-ORG-INFERRED-{index}"},
                "to": {"entity_type": "facility", "source_id": source_id,
                        "identifier_type": "synthetic-permit", "source_identifier": f"D4-FAC-INFERRED-{index}"},
                "relationship_type": "operator",
                "signals": [{"name": "organization_name_normalized"}, {"name": "postal_match"}],
                "observed_at": observed,
            }]
        payload = canonical_json_bytes(candidate)
        return cls._write_jsonl_handoff(
            source_id, "facility", [payload], {
                "schema_version": "private-graph-candidate-set-v1",
                "contract_version": "graph-candidate-handoff-v1",
                "source_kind": "facility_master",
                "source_id": source_id,
                "records_sha256": hashlib.sha256(payload).hexdigest(),
                "checksum_sha256": hashlib.sha256(payload).hexdigest(),
                "byte_size": len(payload), "country_code": "ZZ",
                "storage_state": "private", "review_state": "review_required",
                "publication_status": "not_eligible", "release_state": "not-created",
                "publication_state": "private-candidate",
            })

    @classmethod
    def _write_evidence(cls, source_id: str, index: int) -> Path:
        row = {
            "source_id": source_id, "source_row": 1,
            "source_record_key": f"d4-evidence-{index}", "source_values": {},
            "normalized": {"event_type": "synthetic-inspection",
                           "source_observation_key": f"d4-evidence-{index}",
                           "event_date": "2026-09-21", "linkage_candidates": []},
        }
        payload = (json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n").encode()
        return cls._write_jsonl_handoff(
            source_id, "evidence", [payload], {
                "contract_version": "us-aphis-observation-handoff-v1",
                "source_id": source_id, "entity_scope": "evidence_event",
                "normalized_rows": 1, "normalized_sha256": hashlib.sha256(payload).hexdigest(),
                "checksum_sha256": hashlib.sha256(payload).hexdigest(), "byte_size": len(payload),
                "country_code": "US", "storage_state": "private",
                "publication_status": "not_eligible", "release_state": "not-created",
                "publication_state": "private-candidate",
            })

    @classmethod
    def _write_jsonl_handoff(cls, source_id: str, kind: str, payloads: list[bytes], manifest: dict) -> Path:
        path = cls.root / f"{kind}-{source_id.replace('.', '-') }"
        path.mkdir(parents=True, exist_ok=True)
        (path / "records.jsonl").write_bytes(b"".join(payloads))
        (path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        return path

    def test_all_fifteen_imports_and_rerun_is_idempotent(self):
        first = []
        for source_id in D4_FACILITY_SOURCE_IDS:
            first.append(import_graph_candidates(self.env.database_url, self.handoffs[(source_id, "facility")], disposable_db=True))
        for source_id in D3_EVIDENCE_SOURCE_IDS:
            first.append(import_evidence_events(self.env.database_url, self.handoffs[(source_id, "evidence")], disposable_db=True))
        self.assertEqual(len(first), 15)
        self.assertTrue(all(item["inserted_count"] == 1 for item in first))
        second = []
        for source_id in D4_FACILITY_SOURCE_IDS:
            second.append(import_graph_candidates(self.env.database_url, self.handoffs[(source_id, "facility")], disposable_db=True))
        for source_id in D3_EVIDENCE_SOURCE_IDS:
            second.append(import_evidence_events(self.env.database_url, self.handoffs[(source_id, "evidence")], disposable_db=True))
        self.assertTrue(all(item["status"] == "already_present" for item in second))
        with psycopg.connect(self.env.database_url) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM uec.graph_ingest_runs").fetchone()[0], 15)
            self.assertEqual(db.execute("SELECT count(*) FROM uec.graph_ingest_items").fetchone()[0], 15)
            self.assertEqual(db.execute("SELECT count(*) FROM uec.facilities").fetchone()[0], 13)
            self.assertEqual(db.execute("SELECT count(*) FROM uec.graph_evidence_events").fetchone()[0], 2)
            self.assertEqual(db.execute("SELECT count(*) FROM uec.graph_connection_edges").fetchone()[0], 14)
            self.assertEqual(db.execute("SELECT count(*) FROM uec.graph_connection_edges WHERE connection_type='exact'").fetchone()[0], 13)
            self.assertEqual(db.execute("SELECT count(*) FROM uec.graph_connection_edges WHERE connection_type='inferred'").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT count(*) FROM uec.graph_public_relationships").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT count(*) FROM uec.graph_public_claims").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
