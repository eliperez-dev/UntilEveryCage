import hashlib
import json
import unittest
import uuid
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from pipeline.common import graph_persistence as graph_module
from pipeline.common.graph_source_mapping import FACILITY_IDENTIFIERS
from pipeline.common.graph_persistence import (
    GraphPersistenceError,
    build_candidate_connection_edges,
    _matcher_edge,
    _aphis_facility_identifier_aliases,
    _additional_facility_identifier_aliases,
    _backfill_existing_candidate_context,
    _persist_facility_identifier_aliases,
    _repair_generic_facility_endpoint_types,
    _observed_at,
    _approved_facility_for_source_record,
    _ITALY_CANONICAL_BINDING_CTES,
    _load_approved_facility_map,
    _load_run_source_record_ids_for_edge_batches,
    _finalize_edge_materialization,
    _validate_private_graph_writer,
    _PRIVATE_GRAPH_REQUIRED_PRIVILEGES,
    _PRIVATE_GRAPH_REQUIRED_READ_PRIVILEGES,
    _PRIVATE_GRAPH_REQUIRED_FUNCTION_PRIVILEGES,
    load_evidence_handoff,
    load_graph_candidate_handoff,
    require_disposable_graph_database,
    require_private_graph_target,
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
    def test_duplicate_candidate_context_backfill_is_exact_record_append_only_and_idempotent(self):
        source_record_id, artifact_id = uuid.uuid4(), uuid.uuid4()
        facility_id, facility_identifier_id = uuid.uuid4(), uuid.uuid4()
        organization_id, organization_identifier_id = uuid.uuid4(), uuid.uuid4()

        class Capture:
            def __init__(self):
                self.calls = []
                self.aliases = set()
                self.assertions = set()

            def execute(self, query, params):
                normalized = " ".join(query.split())
                self.calls.append((normalized, params))
                if "SELECT source_record_id FROM uec.source_records" in normalized:
                    return self._result((source_record_id,))
                if "SELECT facility_id FROM uec.source_entity_identifiers" in normalized:
                    if params != ("us.aphis", source_record_id, "establishment_id", "12-R-3456"):
                        raise AssertionError("primary lookup was not bound to the exact source record")
                    return self._result((facility_id,))
                if "SELECT identifier_id FROM uec.source_entity_identifiers" in normalized and "entity_type='facility'" in normalized:
                    return self._result((facility_identifier_id,) if params[-2:] in self.aliases else None)
                if "INSERT INTO uec.source_entity_identifiers" in normalized:
                    self.aliases.add(params[-2:])
                    return self._result(None)
                if "SELECT identifier_id,organization_id FROM uec.source_entity_identifiers" in normalized:
                    if params != ("us.aphis", source_record_id, "business_number", "opaque-42"):
                        raise AssertionError("organization lookup was not bound to the exact source record")
                    return self._result((organization_identifier_id, organization_id))
                if "INSERT INTO uec.graph_source_name_assertions" in normalized:
                    if "ON CONFLICT DO NOTHING" not in normalized or params[:4] != (
                            "us.aphis", source_record_id, organization_id, organization_identifier_id):
                        raise AssertionError("assertion insert was not append-only and record-bound")
                    self.assertions.add(params)
                    return self._result(None)
                raise AssertionError(f"unexpected SQL in context backfill: {normalized}")

            @staticmethod
            def _result(row):
                class Result:
                    def fetchone(self):
                        return row
                    def fetchall(self):
                        return [row] if row is not None else []
                return Result()

        connection = Capture()
        candidate = {
            "source_record_key": "record-private",
            "facilities": [{"local_ref": "f", "source_identifier": {
                "identifier_type": "establishment_id", "value": "12-R-3456"}}],
            "additional_source_identifiers": [{"identifier_type": "siret", "value": "opaque-siret",
                                                  "id_namespace": "fr.insee.siret",
                                                  "identity_scope": "source_scoped"}],
            "organizations": [{"local_ref": "o", "source_identifier": {
                "identifier_type": "business_number", "value": "opaque-42"}}],
            "name_assertions": [{"value": "Synthetic Legal Name", "source_field": "legal_name", "role": "legal"}],
        }
        manifest = {"source_id": "us.aphis", "retrieved_at_utc": "2026-01-01T00:00:00Z"}
        _backfill_existing_candidate_context(connection, manifest, candidate, artifact_id)
        _backfill_existing_candidate_context(connection, manifest, candidate, artifact_id)

        source_record_selects = [(query, params) for query, params in connection.calls
                                 if "SELECT source_record_id FROM uec.source_records" in query]
        self.assertEqual(len(source_record_selects), 2)
        self.assertTrue(all(params == ("us.aphis", "record-private", artifact_id)
                            for _, params in source_record_selects))
        self.assertEqual(len(connection.aliases), 1)
        self.assertEqual(len(connection.assertions), 1)
        self.assertFalse(any("UPDATE uec.source_records" in query or "INSERT INTO uec.organizations" in query
                             or "INSERT INTO uec.graph_connection_edges" in query
                             for query, _ in connection.calls))

    def test_context_backfill_skips_candidates_without_org_names_or_aliases_before_database_lookup(self):
        class NoQueries:
            def execute(self, *_args, **_kwargs):
                raise AssertionError("context-free candidates must not query the database")

        candidate_without_org_name = {
            "source_record_key": "record-no-org-name",
            "facilities": [{"local_ref": "f", "source_identifier": {
                "identifier_type": "permit", "value": "FAC-1"}}],
            "organizations": [],
            "name_assertions": [{"value": "Facility Display Name", "source_field": "name", "role": "business"}],
        }
        _backfill_existing_candidate_context(
            NoQueries(), {"source_id": "synthetic.graph"}, candidate_without_org_name, uuid.uuid4())

    def test_evidence_import_supports_private_writer_target_without_disposable_bypass(self):
        with patch.object(graph_module, "require_private_graph_target") as private_gate, \
             patch.object(graph_module, "require_disposable_graph_database") as disposable_gate:
            with self.assertRaisesRegex(GraphPersistenceError, "batch size must be positive"):
                graph_module.import_evidence_events(
                    "postgresql://127.0.0.1:55433/uec_test_graph",
                    ".", private_target=("uec_test_graph", "private-graph-materialization-v1"),
                    batch_size=0,
                )
        private_gate.assert_called_once()
        disposable_gate.assert_not_called()
        with self.assertRaisesRegex(GraphPersistenceError, "choose either"):
            graph_module.import_evidence_events(
                "postgresql://127.0.0.1:55433/uec_test_graph", ".",
                disposable_db=True, private_target=("uec_test_graph", "private-graph-materialization-v1"),
                batch_size=0,
            )

    def test_aphis_event_identifiers_map_to_distinct_registration_aliases(self):
        normalized = {"source_native_ids": {
            "aphis_license_number": "license-private",
            "certificate_number": "certificate-private",
            "customer_number": "customer-private",
            "customer_number_x": "customer-x-private",
            "customer_number_y": "customer-y-private",
            "inspection_report_id": "report-private",
        }}
        aliases = _aphis_facility_identifier_aliases(normalized)
        self.assertEqual(aliases, [
            ("aphis_certificate_number", "certificate-private"),
            ("aphis_customer_number", "customer-private"),
            ("aphis_customer_number_x", "customer-x-private"),
            ("aphis_customer_number_y", "customer-y-private"),
        ])
        self.assertEqual(_aphis_facility_identifier_aliases({"source_native_ids": {"customer_number": " "}}), [])
        self.assertEqual(
            _aphis_facility_identifier_aliases({"establishment_id": "aphis-registration:12-R-3456"}),
            [("aphis_certificate_number", "12-R-3456")],
        )
        self.assertEqual(
            _aphis_facility_identifier_aliases({"establishment_id": "aphis-registration:12-A-3456"}),
            [],
        )
        self.assertEqual(
            _aphis_facility_identifier_aliases({"source_native_ids": {"aphis_license_number": "12-F-3456"}}),
            [("aphis_certificate_number", "12-F-3456")],
        )

    def test_source_declared_facility_aliases_are_validated_and_append_to_same_facility(self):
        aliases = _additional_facility_identifier_aliases({"additional_source_identifiers": [
            {"identifier_type": "siret", "value": "opaque-id", "id_namespace": "fr.insee.siret",
             "identity_scope": "source_scoped"},
        ]})
        self.assertEqual(aliases, [("siret", "opaque-id", "fr.insee.siret")])
        for bad in (
            {"additional_source_identifiers": [{"identifier_type": "siret", "value": "x",
                                                   "identity_scope": "global"}]},
            {"additional_source_identifiers": "not-a-list"},
        ):
            with self.assertRaises(GraphPersistenceError):
                _additional_facility_identifier_aliases(bad)

        class Capture:
            def __init__(self):
                self.calls = []
            def execute(self, query, params):
                self.calls.append((query, params))
                return self
            def fetchone(self):
                return None

        connection = Capture()
        record_id, facility_id = uuid.uuid4(), uuid.uuid4()
        inserted = _persist_facility_identifier_aliases(
            connection, source_id="fr.icpe", source_record_id=record_id,
            facility_id=facility_id, observed_at="2026-01-01T00:00:00Z", aliases=aliases,
        )
        self.assertEqual(inserted, 1)
        self.assertEqual(len(connection.calls), 2)
        insert_sql, insert_params = connection.calls[1]
        self.assertIn("INSERT INTO uec.source_entity_identifiers", insert_sql)
        self.assertEqual(insert_params[2], facility_id)
        self.assertEqual(insert_params[3:6], ("siret", "opaque-id", "opaque-id"))


    def test_shared_business_name_candidate_persists_as_inferred_non_operator_relation(self):
        raw = {
            "endpoints": [
                {"entity_type": "facility", "source_id": "us.fsis", "identifier_type": "establishment_id", "source_identifier": "FS-1"},
                {"entity_type": "facility", "source_id": "us.fsis", "identifier_type": "establishment_id", "source_identifier": "FS-2"},
            ],
            "provenance": [
                {"source_id": "us.fsis", "source_record_key": "record-1"},
                {"source_id": "us.fsis", "source_record_key": "record-2"},
            ],
            "relationship_type": "shared_business_name",
            "method": "exact_fsis_alternate_name_equality",
            "ruleset": "d6-shared-business-name-v2",
            "contributing_features": ["shared_business_name"],
            "contradictory_evidence": [],
            "observed_at": "2026-01-01T00:00:00Z",
            "disclaimer": "Inferred shared business name only; not evidence of ownership, operator status, or facility identity.",
        }
        edge = _matcher_edge(raw, {"source_record_key": "record-1"},
                             {"source_id": "us.fsis", "retrieved_at_utc": "2026-01-02T00:00:00Z"})
        self.assertIsNotNone(edge)
        self.assertEqual(edge["relationship_type"], "shared_business_name")
        self.assertEqual(edge["connection_type"], "inferred")
        self.assertEqual(edge["confidence_band"], "possible")
        self.assertEqual(edge["from"]["identifier_type"], "fsis_establishment_number")
        self.assertEqual(edge["to"]["identifier_type"], "fsis_establishment_number")
        self.assertEqual(edge["from"]["source_identifier"], "FS-1")
        self.assertEqual(edge["to"]["source_identifier"], "FS-2")
        self.assertEqual(edge["ruleset_version"], "d7-signal-rules-v3")
        self.assertEqual([item["source_record_key"] for item in edge["supporting_source_refs"]], ["record-1", "record-2"])
        self.assertNotIn("operator", edge["relationship_type"])
        self.assertNotIn("Tyson", json.dumps(edge))
        malformed = json.loads(json.dumps(raw))
        malformed["provenance"] = malformed["provenance"][:1]
        self.assertIsNone(_matcher_edge(malformed, {"source_record_key": "record-1"},
                                        {"source_id": "us.fsis", "retrieved_at_utc": "2026-01-02T00:00:00Z"}))

    def test_generic_matcher_facility_ids_normalize_through_existing_source_registry(self):
        for source_id, (expected_type, _namespace) in FACILITY_IDENTIFIERS.items():
            with self.subTest(source_id=source_id):
                left_value, right_value = "opaque-left", "opaque-right"
                raw = {
                    "endpoints": [
                        {"entity_type": "facility", "source_id": source_id,
                         "identifier_type": "establishment_id", "source_identifier": left_value},
                        {"entity_type": "facility", "source_id": source_id,
                         "identifier_type": "establishment_id", "source_identifier": right_value},
                    ],
                    "provenance": [
                        {"source_id": source_id, "source_record_key": "opaque-record-left"},
                        {"source_id": source_id, "source_record_key": "opaque-record-right"},
                    ],
                    "relationship_type": "shared_business_name",
                    "method": "exact_declared_business_name_equality",
                    "ruleset": "d7-shared-business-name-v3",
                    "contributing_features": ["shared_business_name"],
                    "contradictory_evidence": [],
                    "observed_at": "2026-01-01T00:00:00Z",
                }
                edge = _matcher_edge(
                    raw, {"source_id": source_id, "source_record_key": "opaque-record-left"},
                    {"source_id": source_id, "retrieved_at_utc": "2026-01-02T00:00:00Z"},
                )
                self.assertIsNotNone(edge)
                self.assertEqual(edge["from"]["identifier_type"], expected_type)
                self.assertEqual(edge["to"]["identifier_type"], expected_type)
                self.assertEqual(edge["from"]["source_id"], source_id)
                self.assertEqual(edge["to"]["source_id"], source_id)
                self.assertEqual(edge["from"]["source_identifier"], left_value)
                self.assertEqual(edge["to"]["source_identifier"], right_value)
                self.assertEqual(edge["relationship_type"], "shared_business_name")
                self.assertEqual(edge["connection_type"], "inferred")

    def test_endpoint_normalization_leaves_non_generic_unknown_and_org_refs_unchanged(self):
        mapped = FACILITY_IDENTIFIERS["us.fsis"][0]
        cases = (
            ("facility", "unmapped.source", "establishment_id", "opaque-a", "establishment_id"),
            ("facility", "us.fsis", mapped, "opaque-b", mapped),
            ("organization", "us.fsis", "establishment_id", "opaque-c", "establishment_id"),
            ("facility", "us.fsis", "eu_recognition_number", "opaque-d", "eu_recognition_number"),
        )
        for entity_type, source_id, identifier_type, value, expected_type in cases:
            with self.subTest(entity_type=entity_type, source_id=source_id, identifier_type=identifier_type):
                original = graph_module.EntityRef(entity_type, source_id, identifier_type, value)
                normalized = graph_module._native_matcher_endpoint(original)
                self.assertEqual(normalized.identifier_type, expected_type)
                self.assertEqual(normalized.entity_type, entity_type)
                self.assertEqual(normalized.source_id, source_id)
                self.assertEqual(normalized.source_identifier, value)

    def test_materialization_checkpoint_waits_for_finalization_and_failure_is_retryable(self):
        events = []

        class Transaction:
            def __init__(self, connection):
                self.connection = connection

            def __enter__(self):
                events.append("transaction_begin")

            def __exit__(self, *_args):
                events.append("transaction_end")

        class Connection:
            def transaction(self):
                return Transaction(self)

        run_id = uuid.uuid4()
        counts = {"inserted": 2, "updated": 0, "unchanged": 0, "total": 2}

        def failed_finalization():
            events.append("finalization_failed")
            raise RuntimeError("synthetic finalization failure")

        with patch("pipeline.common.graph_persistence._complete_edge_materialization",
                   side_effect=lambda *_args: events.append("completed")), \
             patch("pipeline.common.graph_persistence._fail_edge_materialization",
                   side_effect=lambda *_args: events.append("failed")):
            with self.assertRaisesRegex(RuntimeError, "synthetic finalization failure"):
                _finalize_edge_materialization(
                    Connection(), run_id, counts, {}, failed_finalization)
            self.assertNotIn("completed", events)
            self.assertIn("failed", events)

            events.clear()

            def successful_retry():
                events.append("finalization_succeeded")
                return {"related_facility": 2}

            result = _finalize_edge_materialization(
                Connection(), run_id, counts, {}, successful_retry)

        self.assertEqual(result, {"related_facility": 2})
        self.assertLess(events.index("finalization_succeeded"), events.index("completed"))


    def test_edge_source_record_lookup_closes_implicit_transaction_before_batches(self):
        class FakeConnection:
            def __init__(self):
                self.transaction_open = False
                self.commits = 0

            def commit(self):
                self.commits += 1
                self.transaction_open = False

        connection = FakeConnection()

        def open_read_transaction(_connection, _run_id, _artifact_id):
            connection.transaction_open = True
            return {("synthetic.source", "record-a"): uuid.uuid4()}

        run_id, artifact_id = uuid.uuid4(), uuid.uuid4()
        with patch("pipeline.common.graph_persistence._load_run_source_record_ids",
                   side_effect=open_read_transaction):
            mapping = _load_run_source_record_ids_for_edge_batches(
                connection, run_id, artifact_id)
        self.assertEqual(len(mapping), 1)
        self.assertEqual(connection.commits, 1)
        self.assertFalse(connection.transaction_open)

    def test_italy_canonical_binding_is_same_artifact_release_and_unambiguous_only(self):
        query = _ITALY_CANONICAL_BINDING_CTES
        self.assertIn("candidate.artifact_id=%s", query)
        self.assertIn("record.artifact_id=%s", query)
        self.assertIn("candidate.source_record_count=1 AND candidate.candidate_count=1", query)
        self.assertIn("approved.source_record_count=1 AND approved.facility_count=1", query)
        self.assertIn("profile='official'", query)
        self.assertIn("status='promoted'", query)
        self.assertIn("test_only IS NOT TRUE", query)
        self.assertIn("num_identificativo_produzione_commercializzazione", query)
        self.assertIn("codice_impianto_attivita", query)
        self.assertIn("{normalized,recognition_number}", query)
        self.assertIn("{normalized,activity_code}", query)

    def test_canonical_binding_insert_copies_private_state_without_release_decisions(self):
        from pipeline.common.graph_persistence import _insert_italy_canonical_identifier_bindings

        class Capture:
            rowcount = 7
            calls = []

            def execute(self, query, params):
                self.calls.append((query, params))
                return self

        connection = Capture()
        run_id, artifact_id = uuid.uuid4(), uuid.uuid4()
        self.assertEqual(_insert_italy_canonical_identifier_bindings(
            connection, run_id, "it.853-2004", artifact_id),
            {"identifier_rows": 7, "release_bindings": 7})
        identifier_query, identifier_params = connection.calls[0]
        self.assertIn("INSERT INTO uec.source_entity_identifiers", identifier_query)
        self.assertIn("private_identifier.review_state", identifier_query)
        self.assertIn("private_identifier.storage_state", identifier_query)
        self.assertIn("private_identifier.privacy_status", identifier_query)
        self.assertIn("private_identifier.publication_status", identifier_query)
        self.assertIn("private_identifier.release_id", identifier_query)
        self.assertIn("WHERE NOT EXISTS", identifier_query)
        self.assertNotIn("UPDATE uec.source_entity_identifiers", identifier_query)
        self.assertNotIn("publication_status='released'", identifier_query)
        self.assertEqual(identifier_params, (artifact_id, run_id, "it.853-2004", "it.853-2004", artifact_id, "it.853-2004"))
        binding_query, binding_params = connection.calls[1]
        self.assertIn("INSERT INTO uec.graph_record_release_bindings", binding_query)
        self.assertIn("it_recognition_activity_singleton_v1", binding_query)
        self.assertEqual(binding_params, (artifact_id, run_id, "it.853-2004", "it.853-2004", artifact_id, "it.853-2004", artifact_id))
        self.assertEqual(len(connection.calls), 2)

    def test_canonical_binding_rejects_other_sources_before_sql(self):
        from pipeline.common.graph_persistence import _italy_binding_summary

        class UnexpectedQuery:
            def execute(self, *_args):
                raise AssertionError("unsupported source must be rejected before SQL")

        with self.assertRaises(GraphPersistenceError):
            _italy_binding_summary(UnexpectedQuery(), uuid.uuid4(), "synthetic.graph", uuid.uuid4())

    def test_approved_lineage_cache_requires_one_facility_and_skips_database_queries(self):
        source_record = ("synthetic.graph", "record-1", uuid.uuid4())
        facility = uuid.uuid4()

        class UnexpectedQuery:
            def execute(self, *_args):
                raise AssertionError("cached lineage lookup must not query per source record")

        self.assertEqual(
            _approved_facility_for_source_record(UnexpectedQuery(), *source_record,
                                                 {source_record: {facility}}),
            (facility, "mapped"),
        )
        self.assertEqual(
            _approved_facility_for_source_record(UnexpectedQuery(), *source_record,
                                                 {source_record: {facility, uuid.uuid4()}})[1],
            "ambiguous_approved_release_mapping",
        )
        self.assertEqual(
            _approved_facility_for_source_record(UnexpectedQuery(), *source_record, {})[1],
            "no_eligible_public_record",
        )

    def test_approved_lineage_map_loads_one_release_qualified_query(self):
        facility = uuid.uuid4()
        artifact = uuid.uuid4()

        class OneQuery:
            calls = 0

            def execute(self, query, params):
                self.calls += 1
                self.assert_release_gate(query)
                assert params == ("synthetic.graph", artifact)
                return self

            @staticmethod
            def assert_release_gate(query):
                assert "status='promoted'" in query and "profile='official'" in query

            @staticmethod
            def fetchall():
                return [("synthetic.graph", "record-1", artifact, facility)]

        connection = OneQuery()
        mapping = _load_approved_facility_map(connection, "synthetic.graph", artifact)
        self.assertEqual(connection.calls, 1)
        self.assertEqual(mapping[("synthetic.graph", "record-1", artifact)], {facility})

    def test_indexed_matcher_candidate_becomes_private_inferred_edge(self):
        raw = {
            "endpoints": [
                {"entity_type": "facility", "source_id": "source-a", "identifier_type": "permit", "source_identifier": "A-1", "source_record_key": "row-a"},
                {"entity_type": "facility", "source_id": "source-b", "identifier_type": "permit", "source_identifier": "B-1", "source_record_key": "row-b"},
            ],
            "contributing_features": ["name", "postal"],
            "provenance": [
                {"source_id": "source-a", "source_record_key": "row-a"},
                {"source_id": "source-b", "source_record_key": "row-b"},
            ],
        }
        edge = _matcher_edge(raw, {"source_id": "source-a", "source_record_key": "row-a"}, {"source_id": "source-a", "retrieved_at_utc": "2026-09-21T00:00:00+00:00"})
        self.assertIsNotNone(edge)
        self.assertEqual(edge["connection_type"], "inferred")
        self.assertEqual(edge["from"]["source_identifier"], "A-1")
        self.assertEqual(edge["publication_status"], "not_eligible")
        self.assertEqual(len(edge["supporting_source_refs"]), 2)

    def test_indexed_matcher_preserves_native_endpoint_format_and_ordered_record_refs(self):
        left_id, right_id = uuid.uuid4(), uuid.uuid4()
        raw = {
            "endpoints": [
                {"entity_type": "facility", "source_id": "it.853-2004", "identifier_type": "eu_recognition_number", "source_identifier": "IT-00 123", "source_record_key": "row-a"},
                {"entity_type": "facility", "source_id": "it.853-2004", "identifier_type": "eu_recognition_number", "source_identifier": "B. 7/2", "source_record_key": "row-b"},
            ],
            "contributing_features": ["name", "postal"],
            "provenance": [
                {"source_id": "it.853-2004", "source_record_key": "row-a"},
                {"source_id": "it.853-2004", "source_record_key": "row-b"},
            ],
        }
        edge = _matcher_edge(
            raw, {"source_id": "it.853-2004", "source_record_key": "row-a"},
            {"source_id": "it.853-2004", "retrieved_at_utc": "2026-09-21T00:00:00Z"},
            source_record_ids={("it.853-2004", "row-a"): left_id,
                               ("it.853-2004", "row-b"): right_id},
        )
        self.assertEqual(edge["from"]["source_identifier"], "IT-00 123")
        self.assertEqual(edge["to"]["source_identifier"], "B. 7/2")
        self.assertEqual([ref["source_record_id"] for ref in edge["supporting_source_refs"]],
                         [str(left_id), str(right_id)])
        self.assertEqual([ref["role"] for ref in edge["supporting_source_refs"]], ["from", "to"])

    def test_native_endpoint_repair_requires_release_binding_and_appends_new_edge_key(self):
        from unittest.mock import patch
        from pipeline.common import graph_persistence

        class Cursor:
            def fetchall(self):
                refs = [
                    {"source_id": "it.853-2004", "source_record_key": "left", "source_record_id": str(uuid.uuid4()), "role": "from"},
                    {"source_id": "it.853-2004", "source_record_key": "right", "source_record_id": str(uuid.uuid4()), "role": "to"},
                ]
                return [("legacy-key", "related_facility", "inferred", Decimal("0.7"), "probable",
                         "multi_signal_intersection", refs, {"signals": []}, "d6-signal-rules-v1",
                         "2026-10-20T00:00:00Z", "2026-10-20T00:00:00Z", False, False,
                         "facility", "it.853-2004", "eu_recognition_number", "IT-00 123",
                         "facility", "it.853-2004", "eu_recognition_number", "B. 7/2")]

        class Connection:
            query = ""

            def execute(self, query, params):
                self.query = query
                self.params = params
                return Cursor()

        connection = Connection()
        persisted = []
        def persist(_connection, edges):
            persisted.extend(edges)
            return {"inserted": 1, "updated": 0, "unchanged": 0, "skipped_exact": 0, "total": 1}

        with patch.object(graph_persistence, "persist_connection_edges", persist):
            counts = graph_persistence._repair_inferred_native_endpoints(
                connection, "it.853-2004", uuid.uuid4())
        self.assertIn("graph_record_release_bindings", connection.query)
        self.assertIn("count(DISTINCT native_value)=1", connection.query)
        self.assertEqual(counts["repairable_legacy_inferred_edges"], 1)
        self.assertEqual(persisted[0]["from"]["source_identifier"], "IT-00 123")
        self.assertEqual(persisted[0]["to"]["source_identifier"], "B. 7/2")
        self.assertNotEqual(persisted[0]["edge_key"], "legacy-key")
        self.assertIs(type(persisted[0]["confidence"]), float)

    def test_native_endpoint_repair_empty_result_is_zero_counts(self):
        from pipeline.common import graph_persistence

        class Cursor:
            def fetchall(self):
                return []

        class Connection:
            def execute(self, query, params):
                self.query = query
                self.params = params
                return Cursor()

        counts = graph_persistence._repair_inferred_native_endpoints(
            Connection(), "it.853-2004", uuid.uuid4())
        self.assertEqual(counts, {
            "repairable_legacy_inferred_edges": 0,
            "native_endpoint_repair_inserted": 0,
            "native_endpoint_repair_updated": 0,
            "native_endpoint_repair_unchanged": 0,
            "native_endpoint_repair_skipped_exact": 0,
        })

    def test_generic_endpoint_repair_is_exact_release_bound_and_append_only(self):
        source_id = "us.fsis"
        native_type = FACILITY_IDENTIFIERS[source_id][0]
        original_refs = [
            {"source_id": source_id, "source_record_key": "opaque-left",
             "source_record_id": str(uuid.uuid4()), "artifact_sha256": "a" * 64, "role": "from"},
            {"source_id": source_id, "source_record_key": "opaque-right",
             "source_record_id": str(uuid.uuid4()), "artifact_sha256": "b" * 64, "role": "to"},
        ]

        class Cursor:
            def fetchall(self):
                return [("legacy-edge-key", "shared_business_name", "inferred", Decimal("0.61"),
                         "possible", "exact_declared_business_name_equality", original_refs,
                         {"signals": ["shared_business_name"]}, "d7-shared-business-name-v3",
                         "2026-10-20T00:00:00Z", "2026-10-20T00:00:00Z", False, False,
                         "facility", source_id, native_type, "opaque-facility-left",
                         "facility", source_id, native_type, "opaque-facility-right")]

        class Connection:
            query = ""
            params = ()

            def execute(self, query, params):
                self.query, self.params = query, params
                return Cursor()

        connection = Connection()
        appended = []

        def persist(_connection, edges):
            appended.extend(edges)
            return {"inserted": len(edges), "updated": 0, "unchanged": 0,
                    "skipped_exact": 0, "total": len(edges)}

        with patch.object(graph_module, "persist_connection_edges", persist):
            counts = _repair_generic_facility_endpoint_types(connection)

        self.assertIn("graph_record_release_bindings", connection.query)
        self.assertIn("source_record_key=refs.value->>'source_record_key'", connection.query)
        self.assertIn("lower(artifact.sha256)=lower(refs.value->>'artifact_sha256')", connection.query)
        self.assertIn("binding.release_id=(SELECT release_id FROM selected_release)", connection.query)
        registry = json.loads(connection.params[0])
        self.assertEqual(registry[source_id] if isinstance(registry, dict) else
                         next(item["identifier_type"] for item in registry if item["source_id"] == source_id),
                         native_type)
        self.assertEqual(counts["repairable_generic_facility_endpoint_edges"], 1)
        self.assertEqual(counts["generic_facility_endpoint_repair_inserted"], 1)
        repaired = appended[0]
        self.assertEqual(repaired["from"]["identifier_type"], native_type)
        self.assertEqual(repaired["to"]["identifier_type"], native_type)
        self.assertEqual(repaired["from"]["source_identifier"], "opaque-facility-left")
        self.assertEqual(repaired["to"]["source_identifier"], "opaque-facility-right")
        self.assertEqual(repaired["relationship_type"], "shared_business_name")
        self.assertEqual(repaired["supporting_source_refs"], original_refs)
        self.assertNotEqual(repaired["edge_key"], "legacy-edge-key")

    def test_generic_endpoint_repair_with_no_exact_native_matches_is_noop(self):
        class Cursor:
            def fetchall(self):
                return []

        class Connection:
            def execute(self, _query, _params):
                return Cursor()

        with patch.object(graph_module, "persist_connection_edges") as persist:
            counts = _repair_generic_facility_endpoint_types(Connection())
        persist.assert_not_called()
        self.assertEqual(counts["repairable_generic_facility_endpoint_edges"], 0)
        self.assertEqual(counts["generic_facility_endpoint_repair_inserted"], 0)
    def test_unknown_source_observation_time_uses_handoff_time(self):
        manifest = {"retrieved_at_utc": "2026-09-21T00:00:00Z"}
        self.assertEqual(_observed_at("unknown", manifest), manifest["retrieved_at_utc"])
        self.assertEqual(_observed_at(None, manifest), manifest["retrieved_at_utc"])
        self.assertEqual(_observed_at("2026-09-20", manifest), "2026-09-20")
        self.assertEqual(_observed_at("2026-09-20T12:30:00Z", manifest), "2026-09-20T12:30:00Z")
        self.assertEqual(_observed_at("2026-09-20T12:30:00+02:00", manifest), "2026-09-20T12:30:00+02:00")

    def test_loopback_non_default_disposable_guard(self):
        require_disposable_graph_database("postgresql://uec:pw@localhost:5433/uec-test", True)
        for url in ("postgresql://uec:pw@example.com:5433/uec-test", "postgresql://uec:pw@localhost:5432/uec-test", "postgresql://uec:pw@localhost:5433/app"):
            with self.assertRaises(GraphPersistenceError):
                require_disposable_graph_database(url, True)

    def test_configured_private_graph_target_is_exact_and_loopback_only(self):
        require_private_graph_target(
            "postgresql://uec:pw@127.0.0.1:55433/uec_real_preview_test_graph_20261020",
            expected_database="uec_real_preview_test_graph_20261020",
            purpose="private-graph-materialization-v1",
        )
        for url, database, purpose in (
            ("postgresql://uec:pw@127.0.0.1:55433/uec_real_preview_test_graph_20261020", "uec_other", "private-graph-materialization-v1"),
            ("postgresql://uec:pw@example.com:55433/uec_real_preview_test_graph_20261020", "uec_real_preview_test_graph_20261020", "private-graph-materialization-v1"),
            ("postgresql://uec:pw@127.0.0.1:55433/uec_v0_dev", "uec_v0_dev", "private-graph-materialization-v1"),
            ("postgresql://uec:pw@127.0.0.1:55433/uec_production_graph", "uec_production_graph", "private-graph-materialization-v1"),
            ("postgresql://uec:pw@127.0.0.1:55433/uec_real_preview_test_graph_20261020", "uec_real_preview_test_graph_20261020", "wrong-purpose"),
        ):
            with self.assertRaises(GraphPersistenceError):
                require_private_graph_target(url, expected_database=database, purpose=purpose)

    def test_private_graph_writer_requires_read_only_projection_gate_privileges(self):
        class Cursor:
            def __init__(self, rows):
                self.rows = rows

            def fetchone(self):
                return self.rows.pop(0)

            def fetchall(self):
                return self.rows

        class Connection:
            def __init__(self, privileges, function_grant=True):
                self.privileges = privileges
                self.function_grant = function_grant

            def execute(self, query, params=None):
                if query.startswith("SELECT current_database()"):
                    return Cursor([("uec_stage", "uec_graph_writer_test")])
                if query.startswith("SELECT rolsuper"):
                    return Cursor([(False, False, False, False)])
                if query.startswith("SELECT has_function_privilege"):
                    return Cursor([(self.function_grant,)])
                return Cursor(self.privileges)

        privileges = [
            ("uec", table, privilege)
            for table, grants in {
                **_PRIVATE_GRAPH_REQUIRED_PRIVILEGES,
                **_PRIVATE_GRAPH_REQUIRED_READ_PRIVILEGES,
            }.items()
            for privilege in grants
        ]
        missing_history_read = [
            row for row in privileges
            if row[1:] != ("public_release_history", "SELECT")
        ]
        with self.assertRaisesRegex(GraphPersistenceError, "grants are incomplete"):
            _validate_private_graph_writer(Connection(missing_history_read), "uec_stage")
        _validate_private_graph_writer(Connection(privileges), "uec_stage")
        with self.assertRaisesRegex(GraphPersistenceError, "function grants are incomplete"):
            _validate_private_graph_writer(Connection(privileges, function_grant=False), "uec_stage")

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

    def test_graph_candidate_loader_accepts_adapter_sibling_manifest_format(self):
        row = candidate(source_id="synthetic.italy")
        payload = canonical_json_bytes(row)
        run = test_directory()
        graph = run / "graph"
        graph.mkdir()
        (graph / "graph-candidates.jsonl").write_bytes(payload)
        (graph / "graph-candidates-manifest.json").write_text(json.dumps({
            "schema_version": "private-graph-candidate-batch-v1",
            "contract_version": "graph-candidate-handoff-v1",
            "candidate_count": 1,
            "publication_status": "not_eligible",
            "storage_state": "private",
            "sha256": hashlib.sha256(payload).hexdigest(),
        }), encoding="utf-8")
        (run / "manifest.json").write_text(json.dumps({
            "source_id": "synthetic.italy",
            "release_state": "not-created",
            "publication_state": "private-candidate",
            "storage_state": "private",
            "publication_status": "not_eligible",
        }), encoding="utf-8")
        manifest, rows, digest = load_graph_candidate_handoff(graph)
        self.assertEqual(manifest["source_id"], "synthetic.italy")
        self.assertEqual(rows, [row])
        self.assertEqual(digest, hashlib.sha256(payload).hexdigest())
        manifest, rows, digest = load_graph_candidate_handoff(run)
        self.assertEqual(manifest["source_id"], "synthetic.italy")
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

    def test_candidate_edges_use_source_qualified_endpoints_and_keep_exact_inferred_distinct(self):
        row = candidate()
        row["organizations"] = [{"local_ref": "organization:1", "source_identifier": {"identifier_type": "vat", "value": "IT-1", "identity_scope": "source_scoped"}}]
        row["relationships"] = [{
            "relationship_type": "operator", "from_organization_ref": "organization:1",
            "target_facility_ref": "facility:1", "assertion_status": "asserted",
            "observed_at": "2026-01-01T00:00:00Z", "valid_from": None, "valid_to": None,
            "confidence": None, "review_state": "review_required",
        }]
        row["connection_candidates"] = [{
            "from": {"entity_type": "organization", "source_id": "synthetic.graph", "identifier_type": "vat", "source_identifier": "IT-2"},
            "to": {"entity_type": "facility", "source_id": "synthetic.graph", "identifier_type": "permit", "source_identifier": "FAC-2"},
            "relationship_type": "operator",
            "signals": [
                {"name": "organization_name_normalized"},
                {"name": "postal_match"},
            ],
            "observed_at": "2026-01-01T00:00:00Z",
        }]
        edges = build_candidate_connection_edges(row, {"source_id": "synthetic.graph", "retrieved_at_utc": "2026-01-02T00:00:00Z"})
        self.assertEqual([edge["connection_type"] for edge in edges], ["exact", "inferred"])
        self.assertEqual({edge["from"]["source_id"] for edge in edges}, {"synthetic.graph"})
        self.assertTrue(all(edge["storage_state"] == "private" and edge["publication_status"] == "not_eligible" for edge in edges))
        self.assertNotEqual(edges[0]["edge_key"], edges[1]["edge_key"])

    def test_candidate_edges_do_not_assert_aphis_fsis_links(self):
        row = candidate(source_id="us.aphis")
        row["connection_candidates"] = [{
            "from": {"entity_type": "organization", "source_id": "us.aphis", "identifier_type": "operator_id", "source_identifier": "A-1"},
            "to": {"entity_type": "facility", "source_id": "us.fsis", "identifier_type": "establishment_id", "source_identifier": "F-1"},
            "relationship_type": "operator", "signals": [{"name": "source_assertion"}],
            "observed_at": "2026-01-01T00:00:00Z",
        }]
        self.assertEqual(build_candidate_connection_edges(row, {"source_id": "us.aphis"}), [])

    def test_relationship_matcher_signals_are_scored_as_inferred(self):
        row = candidate()
        row["organizations"] = [{"local_ref": "organization:1", "source_identifier": {"identifier_type": "vat", "value": "IT-1", "identity_scope": "source_scoped"}}]
        row["relationships"] = [{
            "relationship_type": "operator", "from_organization_ref": "organization:1",
            "target_facility_ref": "facility:1", "assertion_status": "asserted",
            "connection_type": "inferred", "signal_bundle": [{"name": "organization_name_normalized"}, {"name": "postal_match"}],
            "observed_at": "2026-01-01T00:00:00Z", "valid_from": None, "valid_to": None,
            "confidence": None, "review_state": "review_required",
        }]
        edges = build_candidate_connection_edges(row, {"source_id": "synthetic.graph"})
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0]["connection_type"], "inferred")

    def test_candidate_edges_include_exact_versioned_source_record_reference_when_resolved(self):
        row = candidate()
        row["organizations"] = [{"local_ref": "organization:1", "source_identifier": {
            "identifier_type": "vat", "value": "IT-1", "identity_scope": "source_scoped"}}]
        row["relationships"] = [{
            "relationship_type": "operator", "from_organization_ref": "organization:1",
            "target_facility_ref": "facility:1", "assertion_status": "asserted",
        }]
        record_id = uuid.uuid4()
        edge = build_candidate_connection_edges(
            row, {"source_id": "synthetic.graph"},
            source_record_ids={("synthetic.graph", row["source_record_key"]): record_id},
        )[0]
        support = edge["supporting_source_refs"][0]
        self.assertEqual(support["source_record_id"], str(record_id))
        self.assertEqual(support["source_record_key"], row["source_record_key"])

    def test_inferred_edge_identity_tracks_artifact_version_not_just_native_key(self):
        row = candidate()
        row["relationships"] = [{
            "relationship_type": "operator", "from_organization_ref": "organization:1",
            "target_facility_ref": "facility:1", "assertion_status": "asserted",
            "connection_type": "inferred",
            "signal_bundle": [{"name": "organization_name_normalized"}, {"name": "postal_match"}],
        }]
        row["organizations"] = [{"local_ref": "organization:1", "source_identifier": {
            "identifier_type": "vat", "value": "IT-1", "identity_scope": "source_scoped"}}]
        key = row["source_record_key"]
        sha_a, sha_b = "a" * 64, "b" * 64
        id_a, id_b = uuid.uuid4(), uuid.uuid4()
        edge_a = build_candidate_connection_edges(
            row, {"source_id": "synthetic.graph", "checksum_sha256": sha_a},
            source_record_ids={("synthetic.graph", key, sha_a): id_a})[0]
        edge_b = build_candidate_connection_edges(
            row, {"source_id": "synthetic.graph", "checksum_sha256": sha_b},
            source_record_ids={("synthetic.graph", key, sha_b): id_b})[0]
        duplicate_a = build_candidate_connection_edges(
            row, {"source_id": "synthetic.graph", "checksum_sha256": sha_a},
            source_record_ids={("synthetic.graph", key, sha_a): id_a})[0]
        self.assertNotEqual(edge_a["edge_key"], edge_b["edge_key"])
        self.assertEqual(edge_a["edge_key"], duplicate_a["edge_key"])
        self.assertEqual(edge_a["supporting_source_refs"][0]["source_record_id"], str(id_a))
        self.assertEqual(edge_b["supporting_source_refs"][0]["source_record_id"], str(id_b))
        self.assertEqual(edge_a["supporting_source_refs"][0]["artifact_sha256"], sha_a)
        self.assertEqual(edge_b["supporting_source_refs"][0]["artifact_sha256"], sha_b)


if __name__ == "__main__":
    unittest.main()
