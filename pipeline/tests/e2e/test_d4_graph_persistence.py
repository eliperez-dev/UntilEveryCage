"""Docker-backed D4 persistence proof using synthetic private handoffs only."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import psycopg

from pipeline.common import graph_persistence as graph_module
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

    def test_all_thirteen_imports_and_rerun_is_idempotent(self):
        first = []
        for source_id in D4_FACILITY_SOURCE_IDS:
            first.append(import_graph_candidates(self.env.database_url, self.handoffs[(source_id, "facility")], disposable_db=True))
        for source_id in D3_EVIDENCE_SOURCE_IDS:
            first.append(import_evidence_events(self.env.database_url, self.handoffs[(source_id, "evidence")], disposable_db=True))
        self.assertEqual(len(first), 13)
        self.assertTrue(all(item["inserted_count"] == 1 for item in first))
        second = []
        for source_id in D4_FACILITY_SOURCE_IDS:
            second.append(import_graph_candidates(self.env.database_url, self.handoffs[(source_id, "facility")], disposable_db=True))
        for source_id in D3_EVIDENCE_SOURCE_IDS:
            second.append(import_evidence_events(self.env.database_url, self.handoffs[(source_id, "evidence")], disposable_db=True))
        self.assertTrue(all(item["status"] == "already_present" for item in second))
        with psycopg.connect(self.env.database_url) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM uec.graph_ingest_runs").fetchone()[0], 13)
            self.assertEqual(db.execute("SELECT count(*) FROM uec.graph_ingest_items").fetchone()[0], 13)
            self.assertEqual(db.execute("SELECT count(*) FROM uec.facilities").fetchone()[0], 11)
            self.assertEqual(db.execute("SELECT count(*) FROM uec.graph_evidence_events").fetchone()[0], 2)
            self.assertEqual(db.execute("SELECT count(*) FROM uec.graph_connection_edges").fetchone()[0], 12)
            self.assertEqual(db.execute("SELECT count(*) FROM uec.graph_connection_edges WHERE connection_type='exact'").fetchone()[0], 11)
            self.assertEqual(db.execute("SELECT count(*) FROM uec.graph_connection_edges WHERE connection_type='inferred'").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT count(*) FROM uec.graph_public_relationships").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT count(*) FROM uec.graph_public_claims").fetchone()[0], 0)

    def test_completed_handoff_backfills_context_without_changing_ingest_metrics(self):
        source_id = "synthetic.graph-context-backfill"
        candidate = {
            "contract_version": "graph-candidate-handoff-v1",
            "source_id": source_id,
            "source_record_key": "context-record-1",
            "source_row": 1,
            "source_values": {"name": "Synthetic Facility"},
            "facilities": [{"local_ref": "facility:1", "source_identifier": {
                "identifier_type": "synthetic-permit", "value": "CTX-FAC-1",
                "identity_scope": "source_scoped",
            }}],
            "organizations": [{"local_ref": "organization:1", "source_identifier": {
                "identifier_type": "synthetic-operator", "value": "CTX-ORG-1",
                "identity_scope": "source_scoped",
            }}],
            "name_assertions": [{
                "value": "Synthetic Legal Name", "source_field": "legal_name", "role": "legal",
            }],
            "relationships": [], "claims": [], "crosswalks": [],
            "contradiction_state": "none-observed", "review_state": "review_required",
            "publication": {"storage_state": "private", "privacy_status": "pending",
                            "review_state": "review_required", "publication_status": "not_eligible",
                            "release_id": None},
        }
        payload = canonical_json_bytes(candidate)
        digest = hashlib.sha256(payload).hexdigest()
        handoff = self._write_jsonl_handoff(source_id, "facility", [payload], {
            "schema_version": "private-graph-candidate-set-v1",
            "contract_version": "graph-candidate-handoff-v1",
            "source_kind": "facility_master", "source_id": source_id,
            "records_sha256": digest, "checksum_sha256": digest,
            "candidate_count": 1, "byte_size": len(payload), "country_code": "ZZ",
            "storage_state": "private", "review_state": "review_required",
            "publication_status": "not_eligible", "release_state": "not-created",
            "publication_state": "private-candidate",
        })

        # Model the original completed import, which persisted identifiers but
        # predates organization-name assertion storage. Keep the handoff/item
        # digest identical so the next import exercises the completed-run path.
        persist_candidate = graph_module._persist_candidate

        def legacy_persist(db, manifest, row, *args, **kwargs):
            without_context = dict(row)
            without_context.pop("name_assertions", None)
            return persist_candidate(db, manifest, without_context, *args, **kwargs)

        with patch.object(graph_module, "_persist_candidate", side_effect=legacy_persist):
            first = import_graph_candidates(self.env.database_url, handoff, disposable_db=True)
        self.assertEqual(first["inserted_count"], 1)
        with psycopg.connect(self.env.database_url) as db:
            self.assertEqual(db.execute(
                "SELECT count(*) FROM uec.graph_source_name_assertions WHERE source_id=%s", (source_id,)
            ).fetchone()[0], 0)

        second = import_graph_candidates(self.env.database_url, handoff, disposable_db=True)
        third = import_graph_candidates(self.env.database_url, handoff, disposable_db=True)
        self.assertEqual((second["status"], second["inserted_count"], second["already_present_count"]),
                         ("already_present", 0, 1))
        self.assertEqual((third["status"], third["inserted_count"], third["already_present_count"]),
                         ("already_present", 0, 1))
        with psycopg.connect(self.env.database_url) as db:
            self.assertEqual(db.execute(
                "SELECT count(*) FROM uec.graph_source_name_assertions WHERE source_id=%s", (source_id,)
            ).fetchone()[0], 1)
            self.assertEqual(db.execute(
                "SELECT count(*) FROM uec.graph_ingest_runs WHERE source_id=%s", (source_id,)
            ).fetchone()[0], 1)
            self.assertEqual(db.execute(
                "SELECT inserted_count,already_present_count,status FROM uec.graph_ingest_runs WHERE source_id=%s",
                (source_id,),
            ).fetchone(), (1, 0, "completed"))
            self.assertEqual(db.execute(
                "SELECT count(*) FROM uec.graph_ingest_items WHERE source_id=%s", (source_id,)
            ).fetchone()[0], 1)
            self.assertEqual(db.execute(
                "SELECT count(*) FROM uec.source_entity_identifiers WHERE source_id=%s AND entity_type='organization'",
                (source_id,),
            ).fetchone()[0], 1)
            self.assertEqual(db.execute(
                "SELECT count(*) FROM uec.source_records WHERE source_id=%s AND raw_fields ? 'name_assertions'",
                (source_id,),
            ).fetchone()[0], 0)

    def test_edge_timestamps_normalize_unknown_null_date_only_and_timezone_inputs(self):
        source_id = "synthetic.graph-edge-timestamps"
        retrieved_at = "2026-10-23T08:00:00Z"
        rows = []

        def make_candidate(index, observed_at=None, *, matcher=False):
            record_key = f"timestamp-record-{index}"
            facility_id = f"TS-FAC-{index}"
            organization_id = f"TS-ORG-{index}"
            row = {
                "contract_version": "graph-candidate-handoff-v1",
                "source_id": source_id,
                "source_record_key": record_key,
                "source_row": index + 1,
                "source_values": {},
                "facilities": [{"local_ref": "facility:1", "source_identifier": {
                    "identifier_type": "synthetic-permit", "value": facility_id,
                    "identity_scope": "source_scoped",
                }}],
                "organizations": [{"local_ref": "organization:1", "source_identifier": {
                    "identifier_type": "synthetic-operator", "value": organization_id,
                    "identity_scope": "source_scoped",
                }}],
                "relationships": [], "claims": [], "crosswalks": [],
                "contradiction_state": "none-observed", "review_state": "review_required",
                "publication": {"storage_state": "private", "privacy_status": "pending",
                                "review_state": "review_required", "publication_status": "not_eligible",
                                "release_id": None},
            }
            if matcher:
                row["connection_candidates"] = [{
                    "from": {"entity_type": "organization", "source_id": source_id,
                             "identifier_type": "synthetic-operator", "source_identifier": organization_id},
                    "to": {"entity_type": "facility", "source_id": source_id,
                           "identifier_type": "synthetic-permit", "source_identifier": facility_id},
                    "relationship_type": "operator",
                    "signals": [{"name": "organization_name_normalized"}],
                    "observed_at": observed_at,
                }]
            else:
                row["relationships"] = [{
                    "relationship_type": "operator", "from_organization_ref": "organization:1",
                    "target_facility_ref": "facility:1", "observed_at": observed_at,
                    "confidence": 0.55, "review_state": "review_required",
                }]
            return row

        for index, observed_at in enumerate(("unknown", "2026-09-21", "2026-09-20T12:30:00+02:00")):
            rows.append(make_candidate(index, observed_at))
        # The matcher contract permits an absent observation timestamp; this
        # exercises null-to-capture-time fallback on the inferred-edge path.
        rows.append(make_candidate(3, None, matcher=True))
        payloads = [canonical_json_bytes(row) for row in rows]
        payload = b"".join(payloads)
        digest = hashlib.sha256(payload).hexdigest()
        handoff = self._write_jsonl_handoff(source_id, "facility", payloads, {
            "schema_version": "private-graph-candidate-set-v1",
            "contract_version": "graph-candidate-handoff-v1",
            "source_kind": "facility_master", "source_id": source_id,
            "records_sha256": digest, "checksum_sha256": digest,
            "candidate_count": len(rows), "byte_size": len(payload), "country_code": "ZZ",
            "retrieved_at_utc": retrieved_at,
            "storage_state": "private", "review_state": "review_required",
            "publication_status": "not_eligible", "release_state": "not-created",
            "publication_state": "private-candidate",
        })
        result = import_graph_candidates(self.env.database_url, handoff, disposable_db=True)
        self.assertEqual(result["inserted_count"], 4)

        with psycopg.connect(self.env.database_url) as db:
            persisted = db.execute(
                "SELECT from_source_identifier, observed_at, computed_at, connection_type "
                "FROM uec.graph_connection_edges WHERE from_source_id=%s "
                "AND from_source_identifier LIKE 'TS-ORG-%' ORDER BY from_source_identifier",
                (source_id,),
            ).fetchall()
        self.assertEqual(len(persisted), 4)
        values = {row[0]: (row[1], row[2], row[3]) for row in persisted}
        capture = datetime.fromisoformat(retrieved_at.replace("Z", "+00:00"))
        self.assertEqual(values["TS-ORG-0"][0], capture)
        self.assertEqual(values["TS-ORG-0"][1], capture)
        self.assertEqual(values["TS-ORG-1"][0], datetime(2026, 9, 21, tzinfo=timezone.utc))
        self.assertEqual(values["TS-ORG-2"][0], datetime.fromisoformat("2026-09-20T10:30:00+00:00"))
        self.assertEqual(values["TS-ORG-3"][0], capture)
        self.assertEqual(values["TS-ORG-3"][1], capture)
        self.assertEqual(values["TS-ORG-3"][2], "inferred")

    def test_committed_batches_are_visible_and_resumable(self):
        source_id = "synthetic.graph-batch-resume"
        payloads = []
        for index in range(2):
            row = {
                "contract_version": "graph-candidate-handoff-v1",
                "source_id": source_id,
                "source_record_key": f"batch-row-{index}",
                "source_row": index + 1,
                "source_values": {"name": f"Synthetic batch facility {index}"},
                "facilities": [{"local_ref": "facility:1", "source_identifier": {
                    "identifier_type": "synthetic-permit", "value": f"BATCH-FAC-{index}",
                    "identity_scope": "source_scoped",
                }}],
                "organizations": [], "relationships": [], "claims": [], "crosswalks": [],
                "publication": {"storage_state": "private", "privacy_status": "pending",
                                "review_state": "review_required", "publication_status": "not_eligible",
                                "release_id": None},
            }
            payloads.append(canonical_json_bytes(row) + b"\n")
        payload = b"".join(payloads)
        digest = hashlib.sha256(payload).hexdigest()
        handoff = self._write_jsonl_handoff(source_id, "facility", payloads, {
            "schema_version": "private-graph-candidate-set-v1",
            "contract_version": "graph-candidate-handoff-v1",
            "source_kind": "facility_master", "source_id": source_id,
            "records_sha256": digest, "checksum_sha256": digest,
            "candidate_count": 2, "byte_size": len(payload), "country_code": "ZZ",
            "storage_state": "private", "review_state": "review_required",
            "publication_status": "not_eligible", "release_state": "not-created",
            "publication_state": "private-candidate",
        })
        visible_counts = []

        def fail_after_first_commit(_batch_number, _offset, _batch_inserted):
            with psycopg.connect(self.env.database_url) as verifier:
                visible_counts.append(verifier.execute(
                    "SELECT count(*) FROM uec.graph_ingest_items WHERE source_id=%s", (source_id,)
                ).fetchone()[0])
            raise RuntimeError("synthetic interruption after a committed batch")

        with self.assertRaisesRegex(RuntimeError, "synthetic interruption"):
            import_graph_candidates(self.env.database_url, handoff, disposable_db=True,
                                    batch_size=1, on_batch_committed=fail_after_first_commit)
        self.assertEqual(visible_counts, [1])
        resumed = import_graph_candidates(self.env.database_url, handoff, disposable_db=True,
                                           batch_size=1)
        self.assertEqual(resumed["resume_offset"], 1)
        self.assertEqual(resumed["inserted_count"], 2)
        with psycopg.connect(self.env.database_url) as verifier:
            self.assertEqual(verifier.execute(
                "SELECT count(*) FROM uec.graph_ingest_items WHERE source_id=%s", (source_id,)
            ).fetchone()[0], 2)


if __name__ == "__main__":
    unittest.main()
