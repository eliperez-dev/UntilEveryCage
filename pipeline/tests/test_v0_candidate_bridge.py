from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "maintenance" / "bridge-v0-candidates.py"
SPEC = importlib.util.spec_from_file_location("bridge_v0_candidates", SCRIPT)
bridge = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bridge)
OWNED_TEST_DATABASE = "uec_v0_review_bridgetest20261004"


def _canonical(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


class CandidateBridgeTests(unittest.TestCase):
    def test_correction_source_record_key_is_versioned_and_keeps_evidence_identity(self):
        key = bridge._correction_source_record_key("a" * 64, "native-id")
        self.assertEqual(key, "v0-correction-v4:" + "a" * 64 + ":native-id")
        self.assertNotEqual(key, "v0:" + "a" * 64 + ":native-id")

    def test_append_candidate_keeps_shared_facility_name_and_uses_safe_status_label(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('facility_conflict = "DO NOTHING" if append_to_v0_baseline', source)
        self.assertIn('"facility_display_name"', source)

    def test_safe_status_adds_only_source_typed_facility_display_name(self):
        safe = bridge._safe_normalized(
            {"facility_name": "Synthetic Facility", "operator_name": "Synthetic Person"},
            "au.npi.facilities", {"telephone": "not-safe"},
        )
        self.assertEqual(safe["facility_display_name"], "Synthetic Facility")
        self.assertNotIn("operator_name", safe)
        self.assertNotIn("telephone", safe)

    def test_baseline_snapshot_orders_access_events_by_the_real_primary_key(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("record_access_events event ORDER BY event.access_event_id", source)
        self.assertNotIn("record_access_events event ORDER BY event.event_id", source)

    def test_facility_display_names_are_source_typed_and_never_use_operator_fallback(self):
        self.assertEqual(bridge._facility_display_name("au.npi.facilities", {
            "facility_name": "  Synthetic   Works ", "operator_name": "Synthetic Person"}), "Synthetic Works")
        self.assertEqual(bridge._facility_display_name("dk.smiley", {
            "name": "Synthetic Person", "trading_name": "Synthetic Foods"}), "Synthetic Foods")
        self.assertIsNone(bridge._facility_display_name("ca.cfia.federal-meat", {
            "name": "Synthetic Person", "operator_name": "Synthetic Person"}))
        self.assertEqual(bridge._facility_display_name("ca.ontario.meat-plants",
            {"name": "Operator fallback", "trading_name": "Operator fallback", "operator_name": "Person"},
            {"Plant Name_ Nom de l'usine": "Synthetic Ontario Plant", "Telephone_Téléphone": "not-used"}),
            "Synthetic Ontario Plant")
        self.assertIsNone(bridge._facility_display_name("ca.ontario.meat-plants",
            {"name": "Operator fallback", "trading_name": "Operator fallback"},
            {"operator name": "Person", "Telephone_Téléphone": "not-used"}))
        self.assertIsNone(bridge._facility_display_name("au.npi.facilities", {
            "facility_name": "   ", "operator_name": "Synthetic Person"}))
        self.assertIsNone(bridge._facility_display_name("dk.smiley", {
            "trading_name": "x" * 201}))

    def test_per_observation_taxonomy_dedupes_only_exact_semantic_claims(self):
        base = {
            "assignment_ordinal": 1, "primary_key": "slaughter", "leaf_key": "red-meat",
            "leaf_label": "Red meat", "source_code_reference": "activity-code",
            "source_label_reference": "activity-label", "source_code": "A1",
            "source_label": "Example", "mapping_method": "direct", "mapping_status": "mapped",
        }
        exact_duplicate = {**base, "assignment_ordinal": 2}
        distinct_reference = {**base, "assignment_ordinal": 3, "source_code_reference": "other-code"}

        result = bridge._deduplicate_exact_assignment_rows([base, exact_duplicate, distinct_reference])

        self.assertEqual(result, [base, distinct_reference])

    def _handoff(self, root: Path, *, source_coordinates: bool = False):
        source = "dk.smiley"
        folder = root / source
        (folder / "normalized").mkdir(parents=True)
        (folder / "graph-candidates").mkdir()
        normalized_rows = [
            {"source_id": source, "source_row": 1, "source_record_key": "DK-2", "source_values": {},
             "normalized": {"establishment_id": "DK-GROUP-1", "country_code": "DK", "city": "Aalborg", "postal_code": "9000", "trading_name": "Synthetic Foods"}},
            {"source_id": source, "source_row": 2, "source_record_key": "DK-1", "source_values": {},
             "normalized": {"establishment_id": "DK-GROUP-1", "country_code": "DK", "city": "Aalborg", "postal_code": "9000", "trading_name": "Synthetic Foods"}},
        ]
        if source_coordinates:
            for row in normalized_rows:
                row["normalized"]["coordinates"] = {
                    "latitude": 56.123456, "longitude": 10.654321,
                    "precision": "numeric", "method": "source_coordinates",
                }
        normalized_bytes = b"".join(_canonical(row) for row in normalized_rows)
        normalized_hash = hashlib.sha256(normalized_bytes).hexdigest()
        normalized_path = folder / "normalized" / "records.jsonl"
        normalized_path.write_bytes(normalized_bytes)
        source_hash = "a" * 64
        retrieved = "2026-10-04T00:00:00Z"
        policy = json.loads((bridge.ROOT / "pipeline" / "preview-enabled-sources.json").read_text(encoding="utf-8"))["sources"][source]
        manifest = {
            "source_id": source, "contract_version": "candidate-handoff-v1",
            "publication_state": "private-candidate", "release_state": "not-created",
            "review_state": "review_required", "privacy_gate": "pending",
            "coordinate_gate": "review_required", "checksum_sha256": source_hash,
            "normalized_sha256": normalized_hash, "normalized_rows": 2,
            "source_url": "https://pub.fvst.dk/smiley.xml", "retrieved_at_utc": retrieved,
            "code_version": policy["adapter_version"], "config_version": policy["schema_version"],
        }
        manifest_path = folder / "manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        graph_rows = [{"source_id": source, "source_record_key": row["source_record_key"],
                       "source_row": row["source_row"]} for row in normalized_rows]
        graph_bytes = b"".join(_canonical(row) for row in graph_rows)
        graph_path = folder / "graph-candidates" / "records.jsonl"
        graph_path.write_bytes(graph_bytes)
        graph_manifest = {
            "schema_version": "private-graph-candidate-set-v1", "candidate_rows": 2,
            "records_sha256": hashlib.sha256(graph_bytes).hexdigest(),
            "review_state": "review_required", "privacy_status": "pending",
            "publication_status": "not_eligible", "storage_state": "private", "auto_merge": False,
        }
        (folder / "graph-candidates" / "manifest.json").write_text(json.dumps(graph_manifest), encoding="utf-8")
        return manifest_path, normalized_rows, manifest, policy

    def _inventory(self, manifest, policy):
        source = "dk.smiley"
        true_manifest = {
            "present": True, "raw_hash_matches_run": True,
            "normalized_hash_matches_run": True,
            "normalized_rows_match_imported_observation_count": True,
            "source_host_matches_run": True, "retrieved_at_matches_run": True,
        }
        physical = {"observations_match_import_counter": True,
                    "candidate_groups_match_facility_counter": True,
                    "source_run_public_rows_zero": True, "idempotent_replay_recorded": True}
        raw_hash = manifest["checksum_sha256"]
        normalized_hash = manifest["normalized_sha256"]
        retrieved = manifest["retrieved_at_utc"]
        source_report = {
            "source_id": source,
            "snapshot": {"snapshot_sha256": "c" * 64, "source_artifact_sha256": raw_hash,
                         "normalized_sha256": normalized_hash, "source_host": "pub.fvst.dk",
                         "retrieved_at": retrieved, "adapter_version": policy["adapter_version"],
                         "schema_version": policy["schema_version"],
                         "handoff_code_version": manifest["code_version"],
                         "handoff_config_version": manifest["config_version"],
                         "manifest_reconciliation": true_manifest},
            "counts": {"accepted_count": 2, "quarantined_count": 0,
                       "imported_observation_count": 2, "facility_count": 1},
            "physical_reconciliation": physical,
        }
        inventory = {"status": "measured", "source_scope": {"sources": [source_report]}}
        digest = hashlib.sha256(_canonical(inventory)).hexdigest()
        return inventory, source_report, digest

    def test_handoff_hash_graph_identity_and_source_native_grouping(self):
        with tempfile.TemporaryDirectory(dir=bridge.ROOT) as temporary:
            manifest_path, rows, manifest, policy = self._handoff(Path(temporary))
            inventory, source_report, digest = self._inventory(manifest, policy)
            inventory["inventory_sha256"] = digest
            inventory["read_at_utc"] = "2026-10-04T01:00:00Z"
            # The isolated DK fixture is synthetic and verifies grouping only.
            entry = {"source_id": "dk.smiley", "snapshot_sha256": "c" * 64,
                     "source_artifact_sha256": manifest["checksum_sha256"],
                     "normalized_sha256": manifest["normalized_sha256"],
                     "handoff_manifest_path": str(manifest_path)}
            verified = bridge.verify_handoff(entry, source_report)
            self.assertEqual(len(verified["rows"]), 2)
            self.assertEqual(set(verified["groups"]), {"DK-GROUP-1"})
            self.assertEqual(verified["representatives"]["DK-GROUP-1"][0][0], "DK-1")
            self.assertEqual(verified["manifest_sha256"], bridge._digest(manifest_path)[0])
            self.assertEqual(verified["graph_manifest_sha256"], bridge._digest(
                manifest_path.parent / "graph-candidates" / "manifest.json")[0])

    def test_all_preview_sources_validate_before_any_canonical_insert(self):
        from contextlib import nullcontext

        sources = ("dk.smiley", "nl.synthetic")
        freeze = {"release_id": "v0-candidate-preflight", "selected_sources": [
            {"source_id": source, "snapshot_sha256": "c" * 64,
             "source_artifact_sha256": "a" * 64, "source_bytes_state": "not_retained",
             "source_artifact_byte_size": None} for source in sources],
            "excluded_sources": [], "inventory_sha256": "b" * 64}
        inventory = {"inventory_sha256": "b" * 64, "source_scope": {"sources": [
            {"source_id": source} for source in sources]}}
        handoffs = {source: {"source_url": "https://example.test/source", "source_host": "example.test",
            "manifest_path": Path("manifest.json"), "manifest": {}, "normalized_sha256": "d" * 64,
            "manifest_sha256": "e" * 64, "graph_manifest_sha256": "f" * 64,
            "graph_records_sha256": "1" * 64, "terms_review_sha256": "2" * 64,
            "rows": [], "representatives": {}} for source in sources}

        class Result:
            def __init__(self, row):
                self.row = row

            def fetchone(self):
                return self.row

        class Connection:
            def __init__(self):
                self.statements = []

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def transaction(self):
                return nullcontext()

            def execute(self, sql, _params=None):
                self.statements.append(sql)
                if sql == "SELECT current_database()":
                    return Result(("uec_v0_review_preflight",))
                if "to_regclass" in sql:
                    return Result((None,))
                if sql.startswith("SELECT count(*)"):
                    return Result((0,))
                if sql.startswith("SELECT status,profile,test_only,ruleset_version,summary"):
                    return Result(None)
                return Result(None)

        connection = Connection()
        with patch.object(bridge.psycopg, "connect", return_value=connection) as connect, \
                patch.object(bridge, "verify_handoff", side_effect=lambda entry, _inventory: handoffs[entry["source_id"]]), \
                patch.object(bridge, "_verify_preview_source", side_effect=[{}, bridge.BridgeError("preview_candidate_taxonomy_mismatch")]) as verify:
            with self.assertRaisesRegex(bridge.BridgeError, "preview_candidate_taxonomy_mismatch"):
                bridge.bridge("postgresql://127.0.0.1/uec_v0_review_preflight", "uec_v0_review_preflight",
                              freeze, inventory, candidate_only_ack=True)

        self.assertEqual([call.args[1] for call in verify.call_args_list], list(sources))
        connect.assert_called_once_with("postgresql://127.0.0.1/uec_v0_review_preflight", prepare_threshold=None)
        self.assertFalse(any(sql.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
                             for sql in connection.statements))

    def test_terms_review_accepts_approved_notes_format_and_binds_exact_file_hash(self):
        with tempfile.TemporaryDirectory(dir=bridge.ROOT) as temporary:
            terms_path = Path(temporary) / "terms.json"
            raw = _canonical({
                "source_id": "dk.smiley",
                "decision": "approved",
                "notes": "Authorized restricted private preview only; no public release.",
            })
            terms_path.write_bytes(raw)
            terms, digest = bridge._read_approved_terms(terms_path, "dk.smiley")
            self.assertEqual(terms["notes"], "Authorized restricted private preview only; no public release.")
            self.assertEqual(digest, hashlib.sha256(raw).hexdigest())

    def test_terms_review_rejects_denied_or_mismatched_source(self):
        with tempfile.TemporaryDirectory(dir=bridge.ROOT) as temporary:
            terms_path = Path(temporary) / "terms.json"
            for terms in (
                {"source_id": "dk.smiley", "decision": "denied", "notes": "Not authorized."},
                {"source_id": "other.source", "decision": "approved", "notes": "Not this source."},
            ):
                terms_path.write_bytes(_canonical(terms))
                with self.assertRaisesRegex(bridge.BridgeError, "source_terms_review_not_approved"):
                    bridge._read_approved_terms(terms_path, "dk.smiley")

    def test_terms_review_rejects_malformed_json(self):
        with tempfile.TemporaryDirectory(dir=bridge.ROOT) as temporary:
            terms_path = Path(temporary) / "terms.json"
            terms_path.write_text("{broken", encoding="utf-8")
            with self.assertRaisesRegex(bridge.BridgeError, "source_terms_review_unavailable"):
                bridge._read_approved_terms(terms_path, "dk.smiley")

    def test_graph_identifier_or_group_association_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory(dir=bridge.ROOT) as temporary:
            manifest_path, _, manifest, policy = self._handoff(Path(temporary))
            inventory, source_report, _ = self._inventory(manifest, policy)
            records = manifest_path.parent / "graph-candidates" / "records.jsonl"
            graph_rows = [json.loads(line) for line in records.read_text(encoding="utf-8").splitlines()]
            graph_rows[0]["source_record_key"] = "different-source-key"
            payload = b"".join(_canonical(row) for row in graph_rows)
            records.write_bytes(payload)
            graph_manifest_path = records.parent / "manifest.json"
            graph_manifest = json.loads(graph_manifest_path.read_text(encoding="utf-8"))
            graph_manifest["records_sha256"] = hashlib.sha256(payload).hexdigest()
            graph_manifest_path.write_text(json.dumps(graph_manifest), encoding="utf-8")
            entry = {"source_id": "dk.smiley", "snapshot_sha256": "c" * 64,
                     "source_artifact_sha256": manifest["checksum_sha256"],
                     "normalized_sha256": manifest["normalized_sha256"],
                     "handoff_manifest_path": str(manifest_path)}
            with self.assertRaisesRegex(bridge.BridgeError, "graph_handoff_identifier_set_mismatch"):
                bridge.verify_handoff(entry, source_report)

    def test_freeze_hash_only_artifact_requires_null_locator_and_size(self):
        with tempfile.TemporaryDirectory(dir=bridge.ROOT) as temporary:
            root = Path(temporary)
            manifest_path, _, manifest, policy = self._handoff(root)
            inventory, source_report, digest = self._inventory(manifest, policy)
            inventory["inventory_sha256"] = digest
            inventory["read_at_utc"] = "2026-10-04T01:00:00Z"
            inventory_path = root / "inventory.json"
            inventory_path.write_bytes(_canonical(inventory))
            freeze = {"schema_version": bridge.SCHEMA, "release_id": "v0-candidate-test",
                      "inventory_sha256": digest,
                      "selected_sources": [{"source_id": "dk.smiley", "snapshot_sha256": "c" * 64,
                          "source_artifact_sha256": manifest["checksum_sha256"],
                          "normalized_sha256": manifest["normalized_sha256"],
                          "accepted_count": 2, "quarantined_count": 0,
                          "imported_observation_count": 2, "facility_count": 1,
                          "handoff_manifest_path": str(manifest_path),
                          "source_bytes_state": "not_retained", "source_artifact_path": None,
                          "source_artifact_byte_size": None}],
                      "excluded_sources": []}
            freeze_path = root / "freeze.json"
            freeze_path.write_bytes(_canonical(freeze))
            loaded, frozen_inventory = bridge.load_freeze(freeze_path, inventory_path)
            self.assertEqual(loaded["inventory_sha256"], digest)
            self.assertEqual(frozen_inventory["status"], "measured")

            freeze["selected_sources"][0]["source_artifact_byte_size"] = 0
            freeze_path.write_bytes(_canonical(freeze))
            with self.assertRaisesRegex(bridge.BridgeError, "not_retained_artifact_metadata_must_be_null"):
                bridge.load_freeze(freeze_path, inventory_path)

    def test_database_guard_requires_loopback_candidate_only_ack_and_separate_name(self):
        freeze = {"release_id": "v0-candidate-test"}
        with self.assertRaisesRegex(bridge.BridgeError, "database_must_be_loopback"):
            bridge.bridge("postgresql://user:secret@db.example/uec_v0_review", "uec_v0_review",
                          freeze, {}, candidate_only_ack=True)
        with self.assertRaisesRegex(bridge.BridgeError, "explicit_candidate_only_ack_required"):
            bridge.bridge("postgresql://user:secret@127.0.0.1/uec_v0_review", "uec_v0_review",
                          freeze, {}, candidate_only_ack=False)
        with self.assertRaisesRegex(bridge.BridgeError, "expected_database_name_must_be_isolated_v0_review"):
            bridge.bridge("postgresql://user:secret@127.0.0.1/uec", "uec",
                          freeze, {}, candidate_only_ack=True)

    def test_public_projection_guard_excludes_candidate_release_membership(self):
        class _Result:
            def __init__(self, value):
                self.value = value

            def fetchone(self):
                return self.value

        class _Connection:
            def __init__(self):
                self.relations = []

            def execute(self, query, parameters=()):
                if query == "SELECT to_regclass(%s)":
                    self.relations.append(parameters[0])
                    return _Result((parameters[0],))
                self.assert_is_public_query(query)
                return _Result((0,))

            @staticmethod
            def assert_is_public_query(query):
                if "count(*)" not in query:
                    raise AssertionError("expected projection count query")

        connection = _Connection()
        self.assertEqual(bridge._public_projection_count(connection), 0)
        self.assertNotIn("uec.release_members", connection.relations)
        self.assertEqual(set(connection.relations), set(bridge.PUBLIC_PROJECTION_RELATIONS))

    def test_identity_uuid_is_source_native_and_snapshot_independent(self):
        first = bridge._uuid("facility", "dk.smiley", "DK-GROUP-1")
        second = bridge._uuid("facility", "dk.smiley", "DK-GROUP-1")
        other_source = bridge._uuid("facility", "nl.nvwa.approved-food", "DK-GROUP-1")
        self.assertEqual(first, second)
        self.assertNotEqual(first, other_source)

    def test_source_provider_and_coarse_coordinates_keep_distinct_provenance(self):
        candidate = [None] * 34
        candidate[11:13] = [56.1, 10.2]
        candidate[24], candidate[27], candidate[28], candidate[29] = "house_number", "result-id", "geoapify", "accepted"
        provider = bridge._coordinate({}, tuple(candidate), allow_display=True)
        self.assertEqual(provider[-1], "provider_derived")
        self.assertEqual(provider[2:5], ("geoapify_forward", "house_number", "geoapify"))
        self.assertEqual(bridge._point_sql_parameters(*provider[:2]), (10.2, 56.1))

        candidate[24] = None
        candidate[27:30] = [None, None, None]
        candidate[25:27] = ["city", "official-municipality-grid"]
        candidate[32:34] = ["reference-evidence-id", "grid-42"]
        coarse = bridge._coordinate({}, tuple(candidate), allow_display=True)
        self.assertEqual(coarse[-1], "verified_coarse_reference")
        self.assertEqual(coarse[2:5], ("coarse_reference", "city", "official-municipality-grid"))
        self.assertEqual(bridge._point_sql_parameters(*coarse[:2]), (10.2, 56.1))

        source = bridge._coordinate({"coordinates": {"latitude": 55.7, "longitude": 12.5,
            "precision": "source-provided", "method": "source_coordinates"}}, tuple(candidate), allow_display=True)
        self.assertEqual(source[:2], (55.7, 12.5))
        self.assertEqual(source[-1], "source_coordinates")
        self.assertEqual(bridge._point_sql_parameters(*source[:2]), (12.5, 55.7))

    def test_restricted_private_address_is_not_mistaken_for_public_clearance(self):
        normalized = {"privacy_gate": "restricted", "source_address_restricted": True,
                      "exact_geocode_candidate": {"source_eligible": True},
                      "name": "Synthetic Contact", "private_location_evidence": {
                          "address": "1 Synthetic Road", "address_lines": ["1 Synthetic Road"],
                          "city": "Aalborg", "country_code": "DK", "email": "private@example.invalid"}}
        stored_status = bridge._safe_normalized(normalized)
        stored_address = {key: value for key, value in normalized["private_location_evidence"].items()
                          if key in bridge._PRIVATE_LOCATION_KEYS}
        self.assertEqual(stored_status["privacy_gate"], "restricted")
        self.assertTrue(stored_status["source_address_restricted"])
        self.assertNotIn("exact_geocode_candidate", stored_status)
        self.assertNotIn("name", stored_status)
        self.assertNotIn("email", stored_address)

    def test_fsis_and_native_evidence_survives_as_bounded_typed_fields(self):
        stored = bridge._safe_normalized({
            "dba_names": "Example DBA", "grant_date": "2026-01-01",
            "species_slaughtered": {"beef_cow_slaughter": "Yes"},
            "processing_activities": {"raw_intact_beef_processing": "No"},
            "activity_volume_codes": {"processing_volume_category": {"code": "2.0"}},
            "native_code": "SH", "native_label": "Slaughterhouse",
            "address": "not retained here", "phone": "not retained here",
        })
        self.assertEqual(stored["alternate_names"], ["Example DBA"])
        self.assertEqual(stored["source_volume_categories"], [
            {"code": "2.0", "provenance": "processing_volume_category"}])
        self.assertEqual(stored["native_code"], "SH")
        self.assertNotIn("address", stored)
        self.assertNotIn("phone", stored)

    def test_not_retained_migration_preserves_retained_default_and_requires_explicit_state(self):
        migration = (bridge.ROOT / "pipeline" / "migrations" / "061_raw_artifact_retention_state.sql").read_text(encoding="utf-8")
        self.assertIn("DEFAULT 'retained'", migration)
        self.assertIn("retention_status = 'retained' AND storage_key IS NOT NULL AND byte_size IS NOT NULL", migration)
        self.assertIn("retention_status = 'not_retained' AND storage_key IS NULL AND byte_size IS NULL", migration)
        self.assertIn("ALTER COLUMN storage_key DROP NOT NULL", migration)
        self.assertIn("ALTER COLUMN byte_size DROP NOT NULL", migration)


@unittest.skipUnless(os.environ.get("UEC_V0_BRIDGE_TEST_DATABASE_URL"),
                     "requires the uniquely named disposable v0 bridge PostGIS database")
class CandidateBridgeDatabaseTests(unittest.TestCase):
    _handoff = CandidateBridgeTests._handoff
    _inventory = CandidateBridgeTests._inventory

    def _remove_abort_fixture(self):
        import psycopg
        url = os.environ.get("UEC_V0_BRIDGE_TEST_DATABASE_URL")
        if not url:
            return
        with psycopg.connect(url) as connection:
            if connection.execute("SELECT current_database()").fetchone()[0] != OWNED_TEST_DATABASE:
                return
            connection.execute("DROP TRIGGER IF EXISTS v0_bridge_test_abort ON uec.release_members")
            connection.execute("DROP FUNCTION IF EXISTS uec.v0_bridge_test_abort()")

    def test_late_rollback_then_same_freeze_idempotent_replay(self):
        import psycopg
        from psycopg.types.json import Jsonb

        with tempfile.TemporaryDirectory(dir=bridge.ROOT) as temporary:
            root = Path(temporary)
            handoff_path, _rows, manifest, policy = self._handoff(root, source_coordinates=True)
            inventory, inventory_source, inventory_hash = self._inventory(manifest, policy)
            inventory.update(inventory_sha256=inventory_hash, read_at_utc="2026-10-04T01:00:00Z")
            database = os.environ["UEC_V0_BRIDGE_TEST_DATABASE"]
            freeze = {"schema_version": bridge.SCHEMA, "release_id": "v0-candidate-dbtest",
                "inventory_sha256": inventory_hash,
                "selected_sources": [{"source_id": "dk.smiley", "snapshot_sha256": "c" * 64,
                    "source_artifact_sha256": manifest["checksum_sha256"],
                    "normalized_sha256": manifest["normalized_sha256"], "accepted_count": 2,
                    "quarantined_count": 0, "imported_observation_count": 2, "facility_count": 1,
                    "handoff_manifest_path": str(handoff_path), "source_bytes_state": "not_retained",
                    "source_artifact_path": None, "source_artifact_byte_size": None}],
                "excluded_sources": []}
            contracts = [bridge.IMPORTER.activity_contract(raw["normalized"], "dk.smiley", raw["source_values"])
                         for raw in _rows]
            merged = bridge.IMPORTER.merge_activity_contracts(contracts, "dk.smiley")
            document = contracts[0]["crosswalk_document"]
            retrieved = bridge._utc(manifest["retrieved_at_utc"], "retrieved_at")
            handoff = bridge.verify_handoff(freeze["selected_sources"][0], inventory_source)
            with psycopg.connect(os.environ["UEC_V0_BRIDGE_TEST_DATABASE_URL"]) as connection, connection.transaction():
                if database != OWNED_TEST_DATABASE or connection.execute("SELECT current_database()").fetchone()[0] != OWNED_TEST_DATABASE:
                    self.fail("integration test must use its exact owned disposable database")
                self.addCleanup(self._remove_abort_fixture)
                connection.execute("DROP TRIGGER IF EXISTS v0_bridge_test_abort ON uec.release_members")
                connection.execute("DROP FUNCTION IF EXISTS uec.v0_bridge_test_abort()")
                # This uniquely named DB is dedicated to this fixture. Clear
                # every table in its two application schemas so interrupted
                # runs cannot leave independent taxonomy or provenance rows.
                tables = connection.execute("""SELECT format('%I.%I',schemaname,tablename)
                    FROM pg_tables WHERE schemaname IN ('uec','real_preview')
                      AND NOT (schemaname='uec' AND tablename='schema_migrations')
                    ORDER BY schemaname,tablename""").fetchall()
                if not tables:
                    self.fail("disposable database schema is not migrated")
                connection.execute("TRUNCATE TABLE " + ",".join(row[0] for row in tables) +
                                   " RESTART IDENTITY CASCADE")
                connection.execute("INSERT INTO real_preview.imports(snapshot_sha256,observation_count) VALUES (%s,2)", ("c" * 64,))
                connection.execute("""INSERT INTO real_preview.source_manifests
                    (snapshot_sha256,source_id,source_artifact_sha256,normalized_sha256,normalized_rows,source_url,retrieved_at,code_version,config_version)
                    VALUES (%s,'dk.smiley',%s,%s,2,%s,%s,%s,%s)""",
                    ("c" * 64, manifest["checksum_sha256"], manifest["normalized_sha256"], manifest["source_url"],
                     retrieved, manifest["code_version"], manifest["config_version"]))
                connection.execute("""INSERT INTO real_preview.source_preview_runs
                    (run_id,source_id,snapshot_sha256,source_url,retrieved_at,source_artifact_sha256,normalized_sha256,
                     adapter_version,schema_version,input_count,accepted_count,quarantined_count,out_of_scope_count,
                     imported_observation_count,facility_count,numeric_coordinate_count,coarse_placeable_count,unmapped_count,
                     api_listable_count,map_visible_count,idempotent_replay,public_rows,runtime_details)
                    VALUES ('bridge-dbtest','dk.smiley',%s,%s,%s,%s,%s,%s,%s,2,2,0,0,2,1,1,0,0,1,1,false,0,'{}')""",
                    ("c" * 64, manifest["source_url"], retrieved, manifest["checksum_sha256"], manifest["normalized_sha256"],
                     manifest["code_version"], manifest["config_version"]))
                preview_ids = {}
                for parsed, _raw in handoff["rows"]:
                    identifier = str(parsed[0])
                    preview_ids[identifier] = connection.execute("""INSERT INTO real_preview.observations
                        (snapshot_sha256,source_id,source_identifier,location_class,facility_candidate,country_code,city,postal_code,
                         latitude,longitude,coordinate_precision,source_observed_at)
                        VALUES (%s,'dk.smiley',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING preview_id""",
                        ("c" * 64, identifier, parsed[1], identifier == "DK-1", parsed[2], parsed[3], parsed[4],
                         parsed[5], parsed[6], parsed[7], parsed[8])).fetchone()[0]
                representative = next(parsed for parsed, _raw in handoff["rows"] if parsed[0] == "DK-1")
                candidate_id = connection.execute("""INSERT INTO real_preview.candidates
                    (snapshot_sha256,source_id,source_group_key,representative_observation_id,location_class,country_code,city,postal_code,
                     latitude,longitude,coordinate_precision,observation_count)
                    VALUES (%s,'dk.smiley','DK-GROUP-1',%s,%s,%s,%s,%s,%s,%s,%s,2)
                    RETURNING candidate_id""",
                    ("c" * 64, preview_ids["DK-1"], representative[1], representative[2], representative[3],
                     representative[4], representative[5], representative[6], representative[7])).fetchone()[0]
                connection.execute("""INSERT INTO real_preview.taxonomy_crosswalks
                    (source_id,taxonomy_version,crosswalk_version,ruleset_version,definition,definition_sha256)
                    VALUES (%s,%s,%s,%s,%s,%s)""",
                    ("dk.smiley", document["taxonomy_version"], document["crosswalk_version"], document["ruleset_version"],
                     Jsonb(document), bridge.crosswalk_sha256(document)))
                candidate_before_assignment = connection.execute(
                    "SELECT to_jsonb(candidate) FROM real_preview.candidates candidate WHERE candidate_id=%s",
                    (candidate_id,),
                ).fetchone()[0]
                self.assertIsNone(candidate_before_assignment["category"])
                self.assertIsNone(candidate_before_assignment["classification_ruleset_version"])
                self.assertEqual(candidate_before_assignment["activity_categories"], [])
                self.assertEqual(candidate_before_assignment["activity_mapping_status"], "unclassified")
                bridge.IMPORTER.persist_preview_candidate_assignment_set(
                    connection, candidate_id=str(candidate_id),
                    representative_observation_id=str(preview_ids["DK-1"]), snapshot_sha256="c" * 64,
                    source_id="dk.smiley", document=document,
                    assignment_rows=merged["taxonomy_assignment_rows"],
                )
                self.assertEqual(connection.execute(
                    "SELECT to_jsonb(candidate) FROM real_preview.candidates candidate WHERE candidate_id=%s",
                    (candidate_id,),
                ).fetchone()[0], candidate_before_assignment)
            verified_freeze = dict(freeze)
            verified_inventory = dict(inventory)
            url = os.environ["UEC_V0_BRIDGE_TEST_DATABASE_URL"]
            # A deliberate late failure proves all prior rows roll back atomically.
            with psycopg.connect(url) as connection:
                connection.execute("""CREATE FUNCTION uec.v0_bridge_test_abort() RETURNS trigger LANGUAGE plpgsql
                    AS $$ BEGIN RAISE EXCEPTION 'synthetic rollback'; END $$""")
                connection.execute("""CREATE TRIGGER v0_bridge_test_abort BEFORE INSERT ON uec.release_members
                    FOR EACH ROW EXECUTE FUNCTION uec.v0_bridge_test_abort()""")
            with self.assertRaises(bridge.BridgeError) as expected_rollback:
                bridge.bridge(url, database, verified_freeze, verified_inventory, candidate_only_ack=True)
            self.assertEqual(expected_rollback.exception.database_sqlstate, "P0001",
                "safe rollback diagnostic: "
                f"error_class={getattr(expected_rollback.exception, 'database_error_class', type(expected_rollback.exception).__name__)}; "
                f"reason={expected_rollback.exception}; "
                f"sqlstate={getattr(expected_rollback.exception, 'database_sqlstate', None)}")
            with psycopg.connect(url) as connection:
                for table in ("uec.releases", "uec.release_members", "uec.raw_artifacts", "uec.source_records", "uec.observations"):
                    self.assertEqual(connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0], 0, table)
                self.assertEqual(connection.execute(
                    "SELECT to_jsonb(candidate) FROM real_preview.candidates candidate WHERE candidate_id=%s",
                    (candidate_id,),
                ).fetchone()[0], candidate_before_assignment)
                connection.execute("DROP TRIGGER v0_bridge_test_abort ON uec.release_members")
                connection.execute("DROP FUNCTION uec.v0_bridge_test_abort()")
            try:
                first = bridge.bridge(url, database, verified_freeze, verified_inventory, candidate_only_ack=True)
            except bridge.BridgeError as error:
                self.fail("successful candidate bridge failed; safe database diagnostics: "
                          f"{getattr(error, 'database_error_class', 'unknown')}/"
                          f"{getattr(error, 'database_sqlstate', 'unknown')}")
            second = bridge.bridge(url, database, verified_freeze, verified_inventory, candidate_only_ack=True)
            self.assertEqual(first, second)
            self.assertEqual(first["counts"]["source_observations"], 2)
            self.assertEqual(first["counts"]["facility_candidates"], 1)
            with psycopg.connect(url) as connection:
                self.assertEqual(connection.execute(
                    "SELECT to_jsonb(candidate) FROM real_preview.candidates candidate WHERE candidate_id=%s",
                    (candidate_id,),
                ).fetchone()[0], candidate_before_assignment)
                self.assertEqual(connection.execute("SELECT status,profile,test_only FROM uec.releases").fetchone(),
                                 ("candidate", "official", False))
                self.assertEqual(connection.execute("SELECT canonical_name FROM uec.facilities").fetchone(),
                                 ("Synthetic Foods",))
                raw_fields = connection.execute("SELECT raw_fields FROM uec.source_records LIMIT 1").fetchone()[0]
                self.assertNotIn("trading_name", raw_fields["normalized"])
                self.assertEqual(connection.execute("SELECT count(*) FROM uec.release_members WHERE default_visible").fetchone()[0], 0)
                self.assertEqual(connection.execute("SELECT retention_status,storage_key,byte_size FROM uec.raw_artifacts").fetchone(),
                                 ("not_retained", None, None))
                dates = connection.execute("SELECT observation->>'source_observed_at',observation->>'observed_at_basis' FROM uec.observations").fetchall()
                self.assertTrue(all(source_date is None and basis == "project_retrieved_at" for source_date, basis in dates))
                provenance = connection.execute("SELECT summary FROM uec.releases").fetchone()[0]["source_provenance"][0]
                self.assertEqual(provenance["handoff_manifest_sha256"], handoff["manifest_sha256"])
                self.assertEqual(provenance["graph_manifest_sha256"], handoff["graph_manifest_sha256"])
                evidence_hashes = connection.execute("SELECT observation->>'handoff_manifest_sha256',observation->>'graph_manifest_sha256' FROM uec.observations").fetchall()
                self.assertEqual(evidence_hashes, [(handoff["manifest_sha256"], handoff["graph_manifest_sha256"])] * 2)
                coordinates = connection.execute("""SELECT ST_Y(coordinate::geometry),ST_X(coordinate::geometry)
                    FROM uec.observations ORDER BY source_record_id""").fetchall()
                self.assertEqual(coordinates, [(56.123456, 10.654321), (56.123456, 10.654321)])

            # Exercise the bounded repair on the synthetic candidate only.
            # The production wrapper is pinned to the real r3 identifiers;
            # this core helper is invoked with this test's exact owned DB/release.
            test_release = verified_freeze["release_id"]
            def safe_state(connection):
                return (
                    connection.execute("SELECT count(*) FROM uec.observations").fetchone()[0],
                    connection.execute("SELECT count(*) FROM uec.source_records").fetchone()[0],
                    connection.execute("SELECT count(*) FROM uec.publication_review_events").fetchone()[0],
                    connection.execute("SELECT count(*) FROM uec.release_members").fetchone()[0],
                )

            with psycopg.connect(url) as connection:
                evidence_before = safe_state(connection)
                connection.execute("UPDATE uec.facilities SET canonical_name=NULL")
            dry = bridge._repair_candidate_names_checked(url, database, verified_freeze, verified_inventory,
                apply=False, required_database=database, required_release_id=test_release)
            self.assertEqual(dry["status"], "dry_run")
            self.assertEqual(dry["member_digest_before"], dry["member_digest_after"])
            with psycopg.connect(url) as connection:
                self.assertIsNone(connection.execute("SELECT canonical_name FROM uec.facilities").fetchone()[0])
            applied = bridge._repair_candidate_names_checked(url, database, verified_freeze, verified_inventory,
                apply=True, required_database=database, required_release_id=test_release)
            self.assertEqual(applied["sources"]["dk.smiley"]["updated_or_would_update"], 1)
            self.assertEqual(applied["member_digest_before"], applied["member_digest_after"])
            replay = bridge._repair_candidate_names_checked(url, database, verified_freeze, verified_inventory,
                apply=True, required_database=database, required_release_id=test_release)
            self.assertEqual(replay["sources"]["dk.smiley"]["updated_or_would_update"], 0)
            self.assertEqual(replay["sources"]["dk.smiley"]["already_named_unchanged"], 1)
            with psycopg.connect(url) as connection:
                connection.execute("UPDATE uec.facilities SET canonical_name='Synthetic Existing Label'")
            preserved = bridge._repair_candidate_names_checked(url, database, verified_freeze, verified_inventory,
                apply=True, required_database=database, required_release_id=test_release)
            with psycopg.connect(url) as connection:
                self.assertEqual(connection.execute("SELECT canonical_name FROM uec.facilities").fetchone()[0],
                                 "Synthetic Existing Label")
                self.assertEqual(safe_state(connection), evidence_before)
            wrong_freeze = {**verified_freeze, "inventory_sha256": "0" * 64}
            with self.assertRaisesRegex(bridge.BridgeError, "frozen_candidate_identity_mismatch"):
                bridge._repair_candidate_names_checked(url, database, wrong_freeze, verified_inventory,
                    apply=False, required_database=database, required_release_id=test_release)
            self.assertEqual(preserved["member_digest_before"], preserved["member_digest_after"])
            import uuid
            extra_facility, extra_observation = str(uuid.uuid4()), str(uuid.uuid4())
            with psycopg.connect(url) as connection:
                source_record_id = connection.execute("SELECT source_record_id FROM uec.source_records LIMIT 1").fetchone()[0]
                connection.execute("INSERT INTO uec.facilities(facility_id,country_code) VALUES (%s,'DK')", (extra_facility,))
                connection.execute("""INSERT INTO uec.observations
                    (observation_id,facility_id,source_record_id,observed_at,observation,classification,ruleset_id,rule_id,
                     classification_category,classification_review_status,default_visible,coordinate_review_status,first_observed_at)
                    VALUES (%s,%s,%s,now(),'{}','{}','synthetic','candidate','unclassified','review_required',false,'review_required',now())""",
                    (extra_observation, extra_facility, source_record_id))
                connection.execute("INSERT INTO uec.release_members(release_id,facility_id,observation_id,default_visible) VALUES (%s,%s,%s,false)",
                    (test_release, extra_facility, extra_observation))
            with self.assertRaisesRegex(bridge.BridgeError, "frozen_membership_identity_mismatch"):
                bridge._repair_candidate_names_checked(url, database, verified_freeze, verified_inventory,
                    apply=False, required_database=database, required_release_id=test_release)


if __name__ == "__main__":
    unittest.main()
