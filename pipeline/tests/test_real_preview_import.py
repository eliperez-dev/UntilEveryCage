"""Sanitized unit coverage for the real-preview importer contract."""

import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).parents[1] / "scripts" / "maintenance" / "import-real-preview.py"
SPEC = importlib.util.spec_from_file_location("import_real_preview", MODULE_PATH)
IMPORTER = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(IMPORTER)


class RealPreviewImporterTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
