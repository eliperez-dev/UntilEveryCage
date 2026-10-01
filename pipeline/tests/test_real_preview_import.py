"""Sanitized unit coverage for the real-preview importer contract."""

import hashlib
import importlib.util
import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

MODULE_PATH = Path(__file__).parents[1] / "scripts" / "maintenance" / "import-real-preview.py"
SPEC = importlib.util.spec_from_file_location("import_real_preview", MODULE_PATH)
IMPORTER = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(IMPORTER)


class RealPreviewImporterTests(unittest.TestCase):
    def test_activity_schema_migration_is_additive_and_keeps_legacy_display_fields(self):
        migration = (Path(__file__).parents[1] / "migrations" / "054_real_preview_activity_contract.sql").read_text(encoding="utf-8")
        for column in ("category", "activity_categories", "source_activity_codes", "source_activity_labels",
                       "activity_mapping_status", "classification_ruleset_version"):
            self.assertIn(f"ADD COLUMN {column}", migration)
        self.assertNotIn("DROP COLUMN", migration)
        self.assertIn("category = ANY(activity_categories)", migration)
        self.assertIn("activity_label", migration)

    def _offline_fixture(self, root: Path, *, source_id: str = "us.fsis") -> None:
        handoff = root / "d6-graph-mvp" / "handoffs" / "us.fsis"
        normalized_dir = handoff / "normalized"
        graph_dir = handoff / "graph-candidates"
        normalized_dir.mkdir(parents=True)
        graph_dir.mkdir()
        normalized = json.dumps({"source_id": "us.fsis", "source_record_key": "test-only-key",
            "source_values": {}, "normalized": {"establishment_number": "test-only-group",
                "city": "Example", "coordinates": {}}}, separators=(",", ":")).encode() + b"\n"
        (normalized_dir / "records.jsonl").write_bytes(normalized)
        graph_records = b"{}\n"
        (graph_dir / "records.jsonl").write_bytes(graph_records)
        manifest = {"source_id": source_id, "contract_version": "candidate-handoff-v1",
            "publication_state": "private-candidate", "release_state": "not-created",
            "review_state": "review_required", "privacy_gate": "pending", "coordinate_gate": "review_required",
            "code_version": "us-fsis-candidate-v2", "config_version": "us-fsis-mpi-v1",
            "checksum_sha256": "a" * 64, "normalized_sha256": hashlib.sha256(normalized).hexdigest(),
            "source_url": "https://www.fsis.usda.gov/sites/default/files/media_file/documents/MPI_Directory_by_Establishment_Number.csv",
            "retrieved_at_utc": "2026-09-20T00:00:00Z", "normalized_rows": 1}
        (handoff / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        graph_manifest = {"schema_version": "private-graph-candidate-set-v1", "records_sha256": hashlib.sha256(graph_records).hexdigest(),
            "candidate_rows": 1, "quarantined_source_rows": 0, "review_state": "review_required",
            "privacy_status": "pending", "publication_status": "not_eligible", "storage_state": "private", "auto_merge": False}
        (graph_dir / "manifest.json").write_text(json.dumps(graph_manifest), encoding="utf-8")

    def test_offline_handoff_hash_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._offline_fixture(root)
            normalized = root / "d6-graph-mvp/handoffs/us.fsis/normalized/records.jsonl"
            normalized.write_bytes(normalized.read_bytes() + b" ")
            with self.assertRaisesRegex(IMPORTER.ImportFailure, "offline_normalized_hash_mismatch"):
                IMPORTER.verify_offline_handoff(root, "us.fsis")

    def test_offline_handoff_source_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._offline_fixture(root, source_id="us.aphis")
            with self.assertRaisesRegex(IMPORTER.ImportFailure, "offline_handoff_provenance_mismatch"):
                IMPORTER.verify_offline_handoff(root, "us.fsis")

    def test_offline_handoff_uses_only_local_hash_checked_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._offline_fixture(root)
            with patch("urllib.request.urlopen", side_effect=AssertionError("network is forbidden")):
                verified = IMPORTER.verify_offline_handoff(root, "us.fsis")
            self.assertEqual(verified["source"], "us.fsis")
            self.assertEqual(verified["expected_rows"], 1)
            self.assertEqual(verified["quarantined"], 0)
            self.assertEqual(verified["normalized_actual"], verified["normalized_hash"])
            self.assertEqual(verified["graph_actual"], verified["graph_manifest"]["records_sha256"])

    def test_catalonia_locality_candidates_are_searchable_but_outside_default_map_scope(self):
        parsed = IMPORTER.parse_row("es.cat.feed-sandach", {
            "source_id": "es.cat.feed-sandach",
            "source_record_key": "synthetic-catalonia-group",
            "source_values": {},
            "normalized": {
                "establishment_id": "synthetic-register-key",
                "municipality_code": "080193",
                "country_code": "ES",
                "city": "Synthetic locality",
                "postal_code": "08000",
            },
        })
        self.assertFalse(parsed[16])
        self.assertEqual(parsed[17], "list_only_locality_reference")

    def test_catalonia_preserves_five_and_six_digit_codes_without_normalizing(self):
        for code in ("08019", "080193"):
            self.assertEqual(
                IMPORTER.administrative_code_for_row(
                    "es.cat.feed-sandach", {"municipality_code": code}
                ),
                code,
            )
        for code in ("0801", "0801930", "08A19"):
            with self.assertRaises(IMPORTER.ImportFailure):
                IMPORTER.administrative_code_for_row(
                    "es.cat.feed-sandach", {"municipality_code": code}
                )

    def test_fsa_records_are_listable_but_unmapped_and_name_gated(self):
        normalized = {
            "establishment_id": "A-1", "trading_name": "Example Foods",
            "activities": ["Fresh Fishery Products Plant"], "activity_categories": ["processing"],
            "nation": "England", "privacy_gate": "privacy-review-required",
            "coordinate_gate": "privacy-review-required", "coordinates": None,
            "coordinate_state": "source-precision-unspecified", "publication_gate": "blocked",
        }
        parsed = IMPORTER.parse_row("fsa_approved_establishments", {
            "source_id": "fsa_approved_establishments", "source_record_key": "England|A-1",
            "source_values": {}, "normalized": normalized,
        })
        self.assertEqual(parsed[1], "unmapped_private_observation")
        self.assertIsNone(parsed[5])
        self.assertIsNone(parsed[6])
        self.assertIsNone(parsed[11], "trading names stay hidden while row-level privacy review is pending")
        self.assertEqual(parsed[-1], "England|A-1", "the same application number in Wales remains a distinct source identity")

    def test_every_enabled_preview_source_has_a_maintained_safe_label(self):
        enabled_path = Path(__file__).parents[1] / "preview-enabled-sources.json"
        enabled = json.loads(enabled_path.read_text(encoding="utf-8"))["sources"]
        self.assertEqual(set(enabled), set(IMPORTER.SOURCE_NAMES))
        self.assertTrue(all(IMPORTER.SOURCE_NAMES[source].strip() for source in enabled))

    def test_generic_source_row_id_provenance_is_allowed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "records.jsonl"
            path.write_text(json.dumps({
                "source_id": "it.853-2004", "source_row": 2,
                "source_row_id": "sha256:fixture", "source_record_key": "record-2",
                "source_values": {"column": "private"}, "normalized": {"recognition_number": "id-2"},
            }) + "\n", encoding="utf-8")
            IMPORTER.validate_preview_fields(path, {"recognition_number"})

    def test_role_qualified_source_row_provenance_is_allowed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "records.jsonl"
            path.write_text(json.dumps({
                "source_id": "us.fsis", "source_row": 2,
                "source_record_key": "M-1", "source_rows": {"directory": 2, "demographics": 4},
                "source_values": {"directory": {}, "demographics": {}},
                "normalized": {"establishment_id": "M-1"},
            }) + "\n", encoding="utf-8")
            IMPORTER.validate_preview_fields(path, {"establishment_id"})

    def test_candidate_projection_version_creates_a_new_immutable_snapshot_identity(self):
        manifests = {"dk.smiley": (Path("unused"), {"normalized_sha256": "a" * 64})}
        digest = IMPORTER.hash_snapshot(manifests)
        old_digest = hashlib.sha256(b"dk.smiley" + bytes.fromhex("a" * 64)).hexdigest()
        self.assertEqual(digest, IMPORTER.hash_snapshot(manifests))
        self.assertNotEqual(digest, old_digest)

    def test_all_source_import_has_snapshot_identity(self):
        manifests = {
            source: (Path("unused"), {"normalized_sha256": hashlib.sha256(source.encode()).hexdigest()})
            for source in sorted(IMPORTER.LEGACY_ALLOWED)
        }
        self.assertEqual(IMPORTER.snapshot_identity(manifests), IMPORTER.hash_snapshot(manifests))
        self.assertEqual(len(IMPORTER.snapshot_identity(manifests)), 64)

    def test_precision_comes_from_coordinate_and_documented_precision_fields(self):
        numeric = IMPORTER.parse_row("it.853-2004", {
            "source_id": "it.853-2004", "source_record_key": "sanitized-fixture",
            "normalized": {"recognition_number": "group-1", "city": "Example",
                "coordinates": {"latitude": 44.1, "longitude": 11.2, "precision": "source-precision-unknown"}},
        })
        self.assertEqual(numeric[1], "numeric_source_coordinate")
        self.assertEqual(numeric[5:7], (44.1, 11.2))
        self.assertEqual(numeric[-1], "group-1")
        coarse = IMPORTER.parse_row("fr.dgal.section-i", {
            "source_id": "fr.dgal.section-i", "source_record_key": "sanitized-fixture",
            "normalized": {"establishment_id": "group-2", "city": "Example"},
        })
        self.assertEqual(coarse[1], "city_postal")
        unmapped = IMPORTER.parse_row("us.fsis", {
            "source_id": "us.fsis", "source_record_key": "numeric-looking-12345",
            "normalized": {"establishment_number": "group-3"},
        })
        self.assertEqual(unmapped[1], "unmapped_private_observation")
        self.assertEqual(unmapped[-1], "group-3")

    def test_fsis_source_provided_coordinate_remains_unverified_precision(self):
        row = IMPORTER.parse_row("us.fsis", {
            "source_id": "us.fsis", "source_record_key": "retained-source-key",
            "normalized": {"establishment_number": "retained-group", "city": "Example",
                "coordinates": {"latitude": 40.1, "longitude": -75.2, "precision": "source-provided"}},
        })
        self.assertEqual(row[1], "numeric_source_coordinate", "private preview may render source-provided positions")
        self.assertEqual(row[7], "source-provided")
        self.assertNotIn(row[7], {"exact", "numeric", "facility_coordinate"})
        self.assertEqual(row[-1], "retained-group")

    def test_italy_853_official_source_values_recover_only_unverified_coordinates(self):
        row = IMPORTER.parse_row("it.853-2004", {
            "source_id": "it.853-2004", "source_record_key": "sanitized-italy-row",
            "source_values": {"latitudine": "45.2", "longitudine": "12.5"},
            "normalized": {"recognition_number": "group-italy", "city": "Example",
                "coordinates": None, "coordinate_precision": "source-precision-unknown"},
        })
        self.assertEqual(row[1], "numeric_source_coordinate")
        self.assertEqual(row[5:7], (45.2, 12.5))
        self.assertEqual(row[7], "source-precision-unknown")

        zero_pair = IMPORTER.parse_row("it.853-2004", {
            "source_id": "it.853-2004", "source_record_key": "sanitized-zero-row",
            "source_values": {"latitudine": "0", "longitudine": "0"},
            "normalized": {"recognition_number": "group-zero", "city": "Example",
                "coordinates": None, "coordinate_precision": "source-precision-unknown"},
        })
        self.assertEqual(zero_pair[1], "city_postal")
        self.assertEqual(zero_pair[5:7], (None, None))
        self.assertTrue(zero_pair[9])

    def test_source_values_coordinates_are_not_used_for_other_sources(self):
        row = IMPORTER.parse_row("us.fsis", {
            "source_id": "us.fsis", "source_record_key": "sanitized-fsis-row",
            "source_values": {"latitudine": "45.2", "longitudine": "12.5"},
            "normalized": {"establishment_number": "group-fsis"},
        })
        self.assertEqual(row[1], "unmapped_private_observation")
        self.assertEqual(row[5:7], (None, None))

    def test_optional_display_evidence_is_allowlisted_and_privacy_gated(self):
        pending = IMPORTER.parse_row("it.853-2004", {
            "source_id": "it.853-2004", "source_record_key": "synthetic-row",
            "normalized": {"recognition_number": "synthetic-group", "name": "Example Works",
                "privacy_gate": "pending-review", "activity_description": "Cutting",
                "evidence_summary": "Synthetic source summary", "source_record_url": "http://example.test/record"},
        })
        self.assertIsNone(pending[11], "names remain omitted until the source privacy gate permits display")
        self.assertEqual(pending[12:14], ("Cutting", "source"))
        self.assertIsNone(pending[14], "record links must use HTTPS")
        self.assertEqual(pending[15], "Synthetic source summary")

        eligible = IMPORTER.parse_row("it.853-2004", {
            "source_id": "it.853-2004", "source_record_key": "synthetic-row",
            "normalized": {"recognition_number": "synthetic-group", "name": "Example Works",
                "privacy_gate": "privacy-cleared", "observation_date": "2026-09-20T12:00:00Z",
                "source_record_url": "https://example.test/record"},
        })
        self.assertEqual(eligible[11], "Example Works")
        self.assertEqual(eligible[14], "https://example.test/record")
        self.assertEqual(eligible[8].isoformat(), "2026-09-20T12:00:00+00:00")
        self.assertIsNone(IMPORTER.safe_https_url("https://user@example.test/record"))
        self.assertIsNone(IMPORTER.safe_https_url("https://example.test/record?token=private"))
        self.assertEqual(IMPORTER.SOURCE_NAMES["us.fsis"], "USDA Food Safety and Inspection Service")
    def test_denmark_default_map_scope_classification_is_preserved(self):
        row = IMPORTER.parse_row("dk.smiley", {
            "source_id": "dk.smiley", "source_record_key": "synthetic-row",
            "normalized": {
                "establishment_id": "synthetic-group",
                "city": "Example", "postal_code": "1234", "in_default_map_scope": False,
                "classification_optional_filter": "general-food",
            },
        })
        self.assertEqual(row[1], "city_postal")
        self.assertFalse(row[16])
        self.assertEqual(row[17], "general-food")
        self.assertEqual(row[18], "synthetic-group")

        unclassified = IMPORTER.parse_row("dk.smiley", {
            "source_id": "dk.smiley", "source_record_key": "synthetic-row",
            "normalized": {"establishment_id": "synthetic-group"},
        })
        self.assertFalse(unclassified[16], "missing Denmark scope classification must fail closed")

    def test_activity_contract_preserves_multi_activity_and_uses_stable_precedence(self):
        first = IMPORTER.activity_contract({
            "activity_categories": ["fish_processing", "slaughter"],
            "activity_codes": ["F-2", "S-1"],
            "activity_descriptions": ["Fish work", "Slaughter line"],
            "classification_ruleset_version": "rules-v7",
        })
        second = IMPORTER.activity_contract({
            "activity_categories": ["slaughter", "fish_processing"],
            "activity_codes": ["F-2", "S-1"],
            "activity_descriptions": ["Fish work", "Slaughter line"],
            "classification_ruleset_version": "rules-v7",
        })
        self.assertEqual(first, second)
        self.assertEqual(first["category"], "slaughter")
        self.assertEqual(first["activity_categories"], ["slaughter", "fish_processing"])
        self.assertEqual(first["source_activity_codes"], ["F-2", "S-1"])
        self.assertEqual(first["source_activity_labels"], ["Fish work", "Slaughter line"])
        self.assertEqual(first["classification_ruleset_version"], "rules-v7")

    def test_activity_contract_keeps_unknown_and_conflicting_values_unclassified(self):
        unknown = IMPORTER.activity_contract({
            "activity_codes": ["new-source-code"],
            "activity_descriptions": ["Not in crosswalk"],
            "classification_mapping_status": "unmapped",
            "classification_category": "unknown",
        })
        self.assertEqual(unknown["activity_categories"], [])
        self.assertIsNone(unknown["category"])
        self.assertEqual(unknown["activity_mapping_status"], "unmapped")
        self.assertEqual(unknown["source_activity_codes"], ["new-source-code"])
        conflict = IMPORTER.activity_contract({
            "classification_category": "slaughter",
            "activity_categories": ["fish_processing"],
            "activity_codes": ["S-1", "F-2"],
        })
        self.assertEqual(conflict["activity_mapping_status"], "conflicting")
        self.assertIsNone(conflict["category"])
        self.assertEqual(conflict["activity_categories"], ["fish_processing"])

    def test_australia_npi_coordinates_are_withheld_and_city_search_remains_listable(self):
        row = IMPORTER.parse_row("au.npi.facilities", {
            "source_id": "au.npi.facilities", "source_record_key": "NPI-1",
            "normalized": {"establishment_id": "NPI-1", "name": "Sensitive facility",
                "city": "Example", "postal_code": "2000", "country_code": "AU",
                "coordinates": None, "coordinate_state": "source-value-present-pending-privacy-review",
                "coordinate_precision": "source-provided; precision semantics not documented",
                "privacy_gate": "pending-review", "in_default_map_scope": False,
                "map_scope_reason": "pending privacy review"},
            "source_values": {"street_address": "1 private road", "latitude": "-33.1", "longitude": "151.2"},
        })
        self.assertEqual(row[1], "city_postal")
        self.assertEqual((row[2], row[3], row[4]), ("AU", "Example", "2000"))
        self.assertIsNone(row[5])
        self.assertIsNone(row[6])
        self.assertIsNone(row[11], "pending privacy must suppress the facility name")
        self.assertFalse(row[16], "NPI records must remain outside default map scope")
        self.assertEqual(IMPORTER.SOURCE_NAMES["au.npi.facilities"],
                         "Australian Department of Climate Change, Energy, the Environment and Water — National Pollutant Inventory")

    def test_unmapped_source_group_is_a_listable_candidate_without_coordinates(self):
        row = IMPORTER.parse_row("dk.smiley", {
            "source_id": "dk.smiley", "source_record_key": "synthetic-row",
            "normalized": {"establishment_id": "synthetic-group", "name": "Example", "in_default_map_scope": True},
        })
        self.assertEqual(row[1], "unmapped_private_observation")
        self.assertIsNone(row[5])
        self.assertIsNone(row[6])
        self.assertTrue(row[16])
        self.assertEqual(row[18], "synthetic-group")

    def test_import_creates_unmapped_source_group_candidate_with_scope_metadata(self):
        class Result:
            def fetchone(self):
                return ("opaque-preview-observation",)

        class Database:
            def __init__(self):
                self.candidates = []

            def execute(self, sql, params=()):
                if "INSERT INTO real_preview.candidates" in sql:
                    self.candidates.append((sql, params))
                return Result()

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rows.jsonl"
            records = [
                {"source_id": "dk.smiley", "source_record_key": "synthetic-row-1",
                 "normalized": {"establishment_id": "synthetic-group", "in_default_map_scope": False,
                     "classification_optional_filter": "general-food", "activity_categories": ["fish_processing"],
                     "activity_codes": ["EB.03.21.00"], "activity_descriptions": ["Fish plant"],
                     "classification_ruleset_version": "denmark-classification-v1"}},
                {"source_id": "dk.smiley", "source_record_key": "synthetic-row-2",
                 "normalized": {"establishment_id": "synthetic-group", "in_default_map_scope": False,
                     "classification_optional_filter": "general-food", "activity_categories": ["slaughter"],
                     "activity_codes": ["EB.10.10.99"], "activity_descriptions": ["Slaughterhouse"],
                     "classification_ruleset_version": "denmark-classification-v1"}},
            ]
            path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
            database = Database()
            imported = IMPORTER.import_rows(database, "dk.smiley", path, 2, "a" * 64)
        self.assertEqual(imported[3], 1, "the two source observations remain one source-scoped candidate")
        self.assertEqual(len(database.candidates), 1)
        sql, params = database.candidates[0]
        self.assertIn("default_map_scope,map_scope_reason", sql)
        self.assertEqual(params[4], "unmapped_private_observation")
        self.assertFalse(params[22])
        self.assertEqual(params[23], "general-food")
        self.assertEqual(params[3], "opaque-preview-observation", "candidate retains lineage to its observation")
        self.assertEqual(params[25], "slaughter")
        self.assertEqual(params[26], ["slaughter", "fish_processing"])
        self.assertEqual(params[27], ["EB.03.21.00", "EB.10.10.99"])
        self.assertEqual(params[28], ["Fish plant", "Slaughterhouse"])
        self.assertEqual(params[29], "mapped")
        self.assertEqual(params[30], "denmark-classification-v1")

    def test_french_commune_resolution_requires_department_to_disambiguate(self):
        reference = {
            "paris|75": {"municipality": "Paris", "department_code": "75", "latitude": 48.8566, "longitude": 2.3522},
            "paris|974": {"municipality": "Paris", "department_code": "974", "latitude": -20.8823, "longitude": 55.4504},
        }
        policy = {"department_field": "department_number"}
        mainland, match = IMPORTER._resolve_municipality(reference, "Paris", policy, "75")
        self.assertEqual(mainland["department_code"], "75")
        self.assertEqual(match, "exact_name")
        overseas, _ = IMPORTER._resolve_municipality(reference, "Paris", policy, "974")
        self.assertEqual(overseas["department_code"], "974")
        self.assertIsNone(IMPORTER._resolve_municipality(reference, "Paris", policy, None)[0])
        self.assertIsNone(IMPORTER._resolve_municipality(reference, "Unresolved", policy, "75")[0])

    def test_undocumented_or_partial_coordinates_fail_closed(self):
        with self.assertRaises(IMPORTER.ImportFailure):
            IMPORTER.parse_row("it.853-2004", {"source_id": "it.853-2004", "source_record_key": "x", "normalized": {}})
        with self.assertRaises(IMPORTER.ImportFailure):
            IMPORTER.parse_row("it.853-2004", {"source_id": "it.853-2004", "source_record_key": "x", "normalized": {"recognition_number": "x", "coordinates": {"latitude": 44.1}}})

    def test_zero_and_out_of_range_coordinates_are_never_numeric_map_points(self):
        zero_with_city = IMPORTER.parse_row("it.853-2004", {
            "source_id": "it.853-2004", "source_record_key": "zero-city",
            "normalized": {"recognition_number": "group-zero-city", "city": "Example",
                "coordinates": {"latitude": 0, "longitude": 0, "precision": "source-precision-unknown"}},
        })
        self.assertEqual(zero_with_city[1], "city_postal")
        self.assertIsNone(zero_with_city[5])
        self.assertIsNone(zero_with_city[6])
        self.assertTrue(zero_with_city[9])

        zero_without_placement = IMPORTER.parse_row("it.853-2004", {
            "source_id": "it.853-2004", "source_record_key": "zero-unmapped",
            "normalized": {"recognition_number": "group-zero-unmapped",
                "coordinates": {"latitude": 0, "longitude": 0, "precision": "source-precision-unknown"}},
        })
        self.assertEqual(zero_without_placement[1], "unmapped_private_observation")
        self.assertIsNone(zero_without_placement[5])
        self.assertIsNone(zero_without_placement[6])

        invalid_with_city = IMPORTER.parse_row("fr.dgal.section-i", {
            "source_id": "fr.dgal.section-i", "source_record_key": "invalid-city",
            "normalized": {"establishment_id": "group-invalid-city", "city": "Example",
                "coordinates": {"latitude": 91, "longitude": 181, "precision": "numeric"}},
        })
        self.assertEqual(invalid_with_city[1], "city_postal")
        self.assertIsNone(invalid_with_city[5])
        self.assertIsNone(invalid_with_city[6])

        invalid_without_placement = IMPORTER.parse_row("fr.dgal.section-i", {
            "source_id": "fr.dgal.section-i", "source_record_key": "invalid-unmapped",
            "normalized": {"establishment_id": "group-invalid-unmapped",
                "coordinates": {"latitude": 91, "longitude": 181, "precision": "numeric"}},
        })
        self.assertEqual(invalid_without_placement[1], "unmapped_private_observation")
        self.assertIsNone(invalid_without_placement[5])
        self.assertIsNone(invalid_without_placement[6])

    def test_artifact_hash_is_streamed_and_detected(self):
        with tempfile.TemporaryDirectory(dir=MODULE_PATH.parents[3]) as directory:
            path = Path(directory) / "fixture.jsonl"
            content = b'{"source_identifier":"synthetic","city":"Example"}\n'
            path.write_bytes(content)
            digest, size = IMPORTER.digest_file(path)
            self.assertEqual(digest, hashlib.sha256(content).hexdigest())
            self.assertEqual(size, len(content))

    def test_explicit_layout_selects_handoffs_and_ignores_aphis_and_historical_duplicates(self):
        with tempfile.TemporaryDirectory(dir=MODULE_PATH.parents[3]) as directory:
            root = Path(directory)
            for source in sorted(IMPORTER.LEGACY_ALLOWED):
                handoff = root / "d6-graph-mvp" / "handoffs" / source
                normalized = handoff / "normalized" / "records.jsonl"
                normalized.parent.mkdir(parents=True)
                normalized_content = json.dumps({"source_record_key": "fixture", "source_id": source,
                    "normalized": {"recognition_number": "group", "city": "Example"}}, separators=(",", ":")).encode() + b"\n"
                normalized.write_bytes(normalized_content)
                raw_content = b"synthetic original hash recorded but artifact not retained " + source.encode()
                manifest = {
                    "source_id": source,
                    "normalized_sha256": hashlib.sha256(normalized_content).hexdigest(),
                    "checksum_sha256": hashlib.sha256(raw_content).hexdigest(),
                }
                (handoff / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            apis = root / "d6-graph-mvp" / "handoffs" / "us.aphis" / "manifest.json"
            apis.parent.mkdir(parents=True)
            apis.write_text(json.dumps({"source_id": "us.aphis"}), encoding="utf-8")
            historical = root / "d5-rehearsal" / "handoffs" / "it.853-2004" / "candidate-handoff" / "manifest.json"
            historical.parent.mkdir(parents=True)
            historical.write_text(json.dumps({"source_id": "it.853-2004", "normalized_sha256": "a" * 64}), encoding="utf-8")
            manifests = IMPORTER.find_manifests(root)
            artifacts = IMPORTER.resolve_artifacts(root, manifests)
            self.assertEqual(set(artifacts), IMPORTER.LEGACY_ALLOWED)
            self.assertTrue(all(path.suffix == ".jsonl" for path in artifacts.values()))

    def test_source_mismatch_in_expected_layout_is_rejected(self):
        with tempfile.TemporaryDirectory(dir=MODULE_PATH.parents[3]) as directory:
            root = Path(directory)
            mismatch_source = next(iter(IMPORTER.LEGACY_ALLOWED))
            for source in IMPORTER.LEGACY_ALLOWED:
                target = root / "d6-graph-mvp" / "handoffs" / source / "manifest.json"
                target.parent.mkdir(parents=True)
                target.write_text(json.dumps({"source_id": "us.aphis" if source == mismatch_source else source, "normalized_sha256": "a" * 64}), encoding="utf-8")
            with self.assertRaises(IMPORTER.ImportFailure) as failure:
                IMPORTER.find_manifests(root)
            self.assertEqual(failure.exception.code, "manifest_source_mismatch")

    def test_second_valid_normalized_handoff_for_same_source_is_rejected(self):
        with tempfile.TemporaryDirectory(dir=MODULE_PATH.parents[3]) as directory:
            root = Path(directory)
            for source in IMPORTER.LEGACY_ALLOWED:
                for suffix in (("", "-alternate") if source == next(iter(IMPORTER.LEGACY_ALLOWED)) else ("",)):
                    handoff = root / "d6-graph-mvp" / "handoffs" / f"{source}{suffix}"
                    (handoff / "normalized").mkdir(parents=True)
                    if not suffix:
                        normalized_file = handoff / "normalized" / "records.jsonl"
                        normalized_file.write_text("{}\n", encoding="utf-8")
                        normalized_hash = hashlib.sha256(normalized_file.read_bytes()).hexdigest()
                    else:
                        normalized_hash = "a" * 64
                    (handoff / "manifest.json").write_text(json.dumps({"source_id": source, "normalized_sha256": normalized_hash}), encoding="utf-8")
            alternate_source = next(iter(IMPORTER.LEGACY_ALLOWED))
            alt = root / "d6-graph-mvp" / "handoffs" / f"{alternate_source}-alternate" / "normalized" / "records.jsonl"
            alt.write_text("{}\n", encoding="utf-8")
            (alt.parent.parent / "manifest.json").write_text(json.dumps({"source_id": alternate_source, "normalized_sha256": hashlib.sha256(alt.read_bytes()).hexdigest()}), encoding="utf-8")
            with self.assertRaises(IMPORTER.ImportFailure) as failure:
                IMPORTER.find_manifests(root)
            self.assertEqual(failure.exception.code, "duplicate_handoff")

    def test_aphis_is_not_imported_or_a_reason_to_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            selected = root / "d6-graph-mvp" / "handoffs"
            for source in IMPORTER.ALLOWED:
                p = selected / source
                (p / "normalized").mkdir(parents=True)
                (p / "normalized" / "records.jsonl").write_text("{}\n", encoding="utf-8")
                (p / "manifest.json").write_text(json.dumps({"source_id": source, "normalized_sha256": "a" * 64}), encoding="utf-8")
            apis = selected / "us.aphis" / "manifest.json"
            apis.parent.mkdir()
            apis.write_text(json.dumps({"source_id": "us.aphis"}), encoding="utf-8")
            found = IMPORTER.find_manifests(root)
            self.assertEqual(set(found), IMPORTER.LEGACY_ALLOWED)
            self.assertEqual(IMPORTER.excluded_sibling_sources(root), ["us.aphis"])

    def test_public_zero_gate_fails_closed_if_any_public_projection_exists(self):
        class EmptyDatabase:
            def execute(self, sql, params=()):
                return type("Result", (), {"fetchone": lambda self: (None,)})()

        self.assertEqual(IMPORTER.public_zero_counts(EmptyDatabase()), (0, 0))

        class PublicRowsDatabase:
            def execute(self, sql, params=()):
                value = "uec.release_members" if "to_regclass" in sql else 1
                return type("Result", (), {"fetchone": lambda self: (value,)})()

        with self.assertRaises(IMPORTER.ImportFailure) as failure:
            IMPORTER.public_zero_counts(PublicRowsDatabase())
        self.assertEqual(failure.exception.code, "public_rows_present")

    def test_map_unmapped_excludes_private_preview_features_but_counts_nonplaceable_groups(self):
        self.assertEqual(IMPORTER.map_unmapped_candidate_count(35_073, 7_241), 27_832)
        with self.assertRaises(IMPORTER.ImportFailure):
            IMPORTER.map_unmapped_candidate_count(10, 11)


if __name__ == "__main__":
    unittest.main()
