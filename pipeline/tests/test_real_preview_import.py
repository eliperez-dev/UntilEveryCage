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

    def test_source_location_provenance_migration_is_additive_and_private(self):
        migration = (Path(__file__).parents[1] / "migrations" / "057_real_preview_source_location_provenance.sql").read_text(encoding="utf-8")
        for column in ("facility_address", "coordinate_method", "coordinate_provider", "coordinate_confidence", "coordinate_confidence_band"):
            self.assertIn(f"ADD COLUMN {column}", migration)
        self.assertIn("private later enrichment", migration)
        self.assertNotIn("INSERT INTO uec.release_members", migration)

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

    def test_archived_artifact_replay_keeps_original_provenance_and_checks_hash(self):
        content = b"synthetic retained official artifact"
        source_hash = hashlib.sha256(content).hexdigest()
        retrieved = IMPORTER.datetime.fromisoformat("2026-10-01T12:00:00+00:00")
        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory) / "source.csv"
            artifact.write_bytes(content)
            evidence = {"source_id": "au.npi.facilities", "run_id": "original-acquisition-1",
                        "sha256": source_hash, "byte_size": len(content),
                        "retrieved_at_utc": "2026-10-01T12:00:00Z",
                        "terms_review": {"decision": "approved"}}
            runtime = {"processing_mode": "archived_replay",
                       "replay_of": {"source_id": "au.npi.facilities",
                                      "original_acquisition_run_id": "original-acquisition-1",
                                      "source_artifact_sha256": source_hash,
                                      "retrieved_at_utc": "2026-10-01T12:00:00Z"}}
            result = {"acquisition_classification": "archived-replay"}
            replay = IMPORTER.validate_archived_replay(runtime, result, "au.npi.facilities",
                                                       source_hash, retrieved, evidence, artifact)
            self.assertEqual(replay["original_acquisition_run_id"], "original-acquisition-1")
            self.assertEqual(replay["source_artifact_sha256"], source_hash)
            artifact.write_bytes(content + b"tampered")
            with self.assertRaisesRegex(IMPORTER.ImportFailure, "archived_replay_artifact_mismatch"):
                IMPORTER.validate_archived_replay(runtime, result, "au.npi.facilities",
                                                  source_hash, retrieved, evidence, artifact)

    def test_archived_artifact_replay_rejects_live_or_unlinked_classification(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory) / "source.csv"
            content = b"synthetic retained official artifact"
            artifact.write_bytes(content)
            source_hash = hashlib.sha256(content).hexdigest()
            retrieved = IMPORTER.datetime.fromisoformat("2026-10-01T12:00:00+00:00")
            evidence = {"source_id": "ca.ontario.meat-plants", "run_id": "original-1",
                        "sha256": source_hash, "byte_size": len(content),
                        "retrieved_at_utc": "2026-10-01T12:00:00Z",
                        "terms_review": {"decision": "approved"}}
            runtime = {"processing_mode": "archived_replay",
                       "replay_of": {"source_id": "ca.ontario.meat-plants",
                                      "original_acquisition_run_id": "original-1",
                                      "source_artifact_sha256": source_hash,
                                      "retrieved_at_utc": "2026-10-01T12:00:00Z"}}
            with self.assertRaisesRegex(IMPORTER.ImportFailure, "archived_replay_provenance_mismatch"):
                IMPORTER.validate_archived_replay(runtime, {"acquisition_classification": "live"},
                                                   "ca.ontario.meat-plants", source_hash,
                                                   retrieved, evidence, artifact)

    def test_retained_live_acquisition_replay_is_not_reported_as_a_fresh_import(self):
        retrieved = IMPORTER.datetime.fromisoformat("2026-10-04T00:39:16+00:00")
        runtime = {"processing_mode": "verified_replay_of_retained_live_acquisition"}
        source_result = {"acquisition_classification": "live"}
        evidence = {"acquisition_method": "network_fetch", "source_id": "dk.smiley",
                    "run_id": "denmark-v0-live-20261003", "sha256": "a" * 64,
                    "retrieved_at_utc": "2026-10-04T00:39:16Z"}
        details = IMPORTER.source_processing_provenance(
            "dk.smiley", runtime, source_result, evidence, "a" * 64, retrieved,
            "denmark-v0-live-20261003", archived_replay=False,
            archived_replay_evidence=None)
        self.assertFalse(details["fresh_live_run"])
        self.assertEqual(details["processing_mode"], "verified_retained_artifact_replay")
        self.assertEqual(details["acquisition_classification"], "live")
        self.assertEqual(details["replay_of"]["source_artifact_sha256"], "a" * 64)
        evidence["sha256"] = "b" * 64
        with self.assertRaisesRegex(IMPORTER.ImportFailure, "retained_live_replay_provenance_mismatch"):
            IMPORTER.source_processing_provenance(
                "dk.smiley", runtime, source_result, evidence, "a" * 64, retrieved,
                "denmark-v0-live-20261003", archived_replay=False,
                archived_replay_evidence=None)

    def test_retained_replay_correction_is_deterministic_and_hash_linked(self):
        runtime = {
            "run_id": "dk-smiley-v0-private-20261004",
            "processing_mode": "verified_replay_of_retained_live_acquisition",
            "completed_at_utc": "2026-10-04T21:30:17Z",
            "results": [{"source_id": "dk.smiley", "status": "succeeded",
                         "acquisition_classification": "live",
                         "summary": {"candidate_handoff": True,
                                     "candidate_handoff_sha256": "b" * 64,
                                     "candidate_observation_rows": 4,
                                     "quarantined_rows": 1, "out_of_scope_rows": 0,
                                     "input_rows": 5}}],
        }
        handoff = {"source_id": "dk.smiley", "checksum_sha256": "a" * 64,
                   "normalized_sha256": "b" * 64, "normalized_rows": 4,
                   "retrieved_at_utc": "2026-10-04T00:39:16Z"}
        first = IMPORTER.prepare_retained_replay_correction(
            "dk.smiley", "denmark-v0-live-20261003", "dk-smiley-v0-private-20261004",
            runtime, handoff)
        second = IMPORTER.prepare_retained_replay_correction(
            "dk.smiley", "denmark-v0-live-20261003", "dk-smiley-v0-private-20261004",
            runtime, handoff)
        self.assertEqual(first, second)
        self.assertEqual(first["normalized_sha256"], "b" * 64)
        self.assertEqual(first["retrieved_at_utc"], "2026-10-04T00:39:16Z")
        self.assertEqual(first["replayed_at_utc"], "2026-10-04T21:30:17Z")
        handoff["normalized_sha256"] = "c" * 64
        with self.assertRaisesRegex(IMPORTER.ImportFailure, "retained_replay_correction_artifact_mismatch"):
            IMPORTER.prepare_retained_replay_correction(
                "dk.smiley", "denmark-v0-live-20261003", "dk-smiley-v0-private-20261004",
                runtime, handoff)

    def test_retained_replay_correction_is_append_only_and_does_not_reimport_source_rows(self):
        source = (Path(__file__).parents[1] / "scripts" / "maintenance" / "import-real-preview.py").read_text(encoding="utf-8")
        start = source.index("def record_retained_replay_correction(")
        end = source.index("\ndef ", start + 5)
        correction = source[start:end]
        self.assertIn("INSERT INTO real_preview.source_preview_runs", correction)
        self.assertIn("ON CONFLICT (run_id) DO NOTHING", correction)
        self.assertNotIn("UPDATE real_preview.", correction)
        self.assertNotIn("INSERT INTO real_preview.observations", correction)
        self.assertNotIn("INSERT INTO real_preview.candidates", correction)

    def test_catalonia_locality_candidates_use_map_scope_after_reference_enrichment(self):
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
        self.assertTrue(parsed[16])
        self.assertIsNone(parsed[17])

    def test_private_location_evidence_schema_excludes_contact_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "records.jsonl"
            row = {"source_id": "es.cat.feed-sandach", "source_record_key": "opaque",
                   "source_values": {}, "normalized": {"establishment_id": "opaque",
                       "private_location_evidence": {"address": "Synthetic Road", "postal_code": "08000",
                           "coordinates": {"latitude": "41.0", "longitude": "2.0", "precision": "source-precision-unknown"}}}}
            path.write_text(json.dumps(row) + "\n", encoding="utf-8")
            IMPORTER.validate_preview_fields(path, {"establishment_id"})
            row["normalized"]["private_location_evidence"]["email"] = "person@example.test"
            path.write_text(json.dumps(row) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(IMPORTER.ImportFailure, "private_location_evidence_invalid"):
                IMPORTER.validate_preview_fields(path, {"establishment_id"})

    def test_private_location_evidence_follows_its_source_candidate(self):
        class FakeDatabase:
            def __init__(self):
                self.statements = []
                self.fetch_count = 0

            def execute(self, statement, parameters=None):
                self.statements.append((str(statement), parameters))
                return self

            def fetchone(self):
                self.fetch_count += 1
                return (f"synthetic-id-{self.fetch_count}",)

        rows = []
        for index, address in enumerate(("Synthetic One Road", "Synthetic Two Road"), start=1):
            rows.append({"source_id": "us.fsis", "source_record_key": f"key-{index}",
                         "source_values": {}, "normalized": {
                             "establishment_number": f"group-{index}", "country_code": "US",
                             "private_location_evidence": {"address": address, "city": f"Town {index}"},
                         }})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "records.jsonl"
            path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            db = FakeDatabase()
            with patch.object(IMPORTER, "persist_preview_candidate_assignment_set"):
                IMPORTER.import_rows(db, "us.fsis", path, 2, "a" * 64)
        evidence_rows = [parameters for statement, parameters in db.statements
                         if "INSERT INTO real_preview.candidate_private_location_evidence" in statement]
        self.assertEqual([json.loads(parameters[3])["address"] for parameters in evidence_rows],
                         ["Synthetic One Road", "Synthetic Two Road"])

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

    def test_private_evidence_coordinates_do_not_override_source_display_policy(self):
        parsed = IMPORTER.parse_row("fsa_approved_establishments", {
            "source_id": "fsa_approved_establishments", "source_record_key": "England|A-2",
            "source_values": {}, "normalized": {
                "establishment_id": "A-2", "nation": "England", "coordinates": None,
                "coordinate_precision": "source-precision-unspecified",
                "private_location_evidence": {"address": ["Synthetic Road"], "city": "Exampletown",
                    "coordinates": {"latitude": 51.5, "longitude": -0.12,
                                    "precision": "source-precision-unspecified"}},
            },
        })
        self.assertEqual(parsed[1], "city_postal")
        self.assertIsNone(parsed[5])
        self.assertIsNone(parsed[6])

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

    def test_ontario_coordinates_and_facility_address_pass_private_projection(self):
        row = IMPORTER.parse_row("ca.ontario.meat-plants", {
            "source_id": "ca.ontario.meat-plants", "source_record_key": "ON-synthetic",
            "normalized": {
                "establishment_id": "ON-synthetic", "city": "Example City", "postal_code": "A1A 1A1",
                "facility_address": "1 Synthetic Road",
                "coordinates": {"latitude": 43.1, "longitude": -79.1, "precision": "source-provided",
                    "method": "source_coordinate", "provider": "Government of Ontario", "confidence_band": "high"},
            },
        })
        self.assertEqual(row[1], "numeric_source_coordinate")
        self.assertEqual(row[5:8], (43.1, -79.1, "source-provided"))
        self.assertEqual(row[18:23], ("1 Synthetic Road", "source_coordinate", "Government of Ontario", None, "high"))
        self.assertEqual(row[-1], "ON-synthetic")

    def test_ontario_adapter_handoff_location_provenance_is_private_allowlisted(self):
        from pipeline.sources.first_wave import FirstWaveRefreshAdapter, descriptor_for

        raw = (b"Plant Number,Plant Name,Address,City,Province,Postal Code,Phone,Latitude,Longitude,Plant Type\n"
               b"ON-SYNTHETIC,Synthetic Plant,1 Synthetic Road,Example City,ON,A1A 1A1,555-0100,43.1,-79.1,Abattoir\n")
        policy = json.loads((Path(__file__).parents[1] / "preview-enabled-sources.json").read_text(encoding="utf-8"))
        source_policy = policy["sources"]["ca.ontario.meat-plants"]
        self.assertFalse(source_policy["public_release"])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw_path = root / "ontario.csv"
            raw_path.write_bytes(raw)
            result = FirstWaveRefreshAdapter(descriptor_for("ca.ontario.meat-plants")).refresh(
                mode="local-artifact", run_dir=root / "run", artifact=raw_path, options={})
            self.assertTrue(result["candidate_handoff"])
            handoff = root / "run" / "candidate-handoff"
            IMPORTER.validate_preview_fields(handoff / "normalized" / "records.jsonl",
                                             set(source_policy["allowed_preview_fields"]))
            record = json.loads((handoff / "normalized" / "records.jsonl").read_text(encoding="utf-8"))
            class FakeDatabase:
                def __init__(self):
                    self.statements = []
                    self.next_id = 0

                def execute(self, statement, parameters=None):
                    self.statements.append((str(statement), parameters))
                    return self

                def fetchone(self):
                    self.next_id += 1
                    return (f"synthetic-id-{self.next_id}",)

            db = FakeDatabase()
            with patch.object(IMPORTER, "persist_preview_candidate_assignment_set"):
                IMPORTER.import_rows(db, "ca.ontario.meat-plants",
                    handoff / "normalized" / "records.jsonl", 1, "c" * 64,
                    municipality_policy=source_policy["display_policy"])
        normalized = record["normalized"]
        for field in ("facility_address", "coordinate_method", "coordinate_provider",
                      "coordinate_confidence_band"):
            self.assertIn(field, normalized)
        self.assertNotIn("Phone", normalized)
        evidence = normalized["private_location_evidence"]
        self.assertEqual(evidence["address"], "1 Synthetic Road")
        self.assertEqual(evidence["coordinates"]["latitude"], 43.1)
        self.assertEqual(evidence["coordinates"]["longitude"], -79.1)
        candidate = next(parameters for statement, parameters in db.statements
                         if "INSERT INTO real_preview.candidates" in statement)
        self.assertEqual(candidate[12:14], (43.1, -79.1))
        private_projection = next(parameters for statement, parameters in db.statements
                                  if "INSERT INTO real_preview.candidate_private_location_evidence" in statement)
        self.assertEqual(json.loads(private_projection[3])["address"], "1 Synthetic Road")

    def test_unmapped_count_is_candidate_groups_without_a_rendered_point(self):
        self.assertEqual(IMPORTER.map_unmapped_candidate_count(4, map_visible_count=2), 2)
        self.assertEqual(IMPORTER.map_unmapped_candidate_count(8_140, map_visible_count=8_116), 24)

    def test_address_candidate_is_linked_to_persisted_pending_provider_job(self):
        class FakeDatabase:
            def __init__(self):
                self.statements = []
                self.next_id = 0

            def execute(self, statement, parameters=None):
                self.statements.append((str(statement), parameters))
                return self

            def fetchone(self):
                self.next_id += 1
                return (f"synthetic-id-{self.next_id}",)

        row = {"source_id": "au.npi.facilities", "source_record_key": "synthetic-key",
               "source_values": {"Phone": "must-not-enter-query"},
               "normalized": {"establishment_id": "synthetic-group", "country_code": "AU",
                   "private_location_evidence": {"address": "1 Synthetic Road", "city": "Exampletown",
                                                   "postal_code": "12345", "country_code": "AU"}}}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "records.jsonl"
            path.write_text(json.dumps(row) + "\n", encoding="utf-8")
            db = FakeDatabase()
            with patch.object(IMPORTER, "persist_preview_candidate_assignment_set"):
                IMPORTER.import_rows(
                    db, "au.npi.facilities", path, 1, "a" * 64,
                    source_artifact_sha256="b" * 64,
                    source_url="https://example.test/official.csv",
                    source_retrieved_at=IMPORTER.datetime.fromisoformat("2026-10-01T00:00:00+00:00"),
                    source_artifact_byte_size=123,
                )
        statements = [statement for statement, _ in db.statements]
        self.assertTrue(any("INSERT INTO uec.geocode_jobs" in statement for statement in statements))
        self.assertTrue(any("INSERT INTO real_preview.geocode_targets" in statement for statement in statements))
        job = next(parameters for statement, parameters in db.statements
                    if "INSERT INTO uec.geocode_jobs" in statement)
        self.assertEqual(job[1], "pending-provider-review")
        self.assertIn("1 Synthetic Road", job[2])
        self.assertNotIn("must-not-enter-query", job[2])
        event = next(parameters for statement, parameters in db.statements
                     if "INSERT INTO uec.geocode_job_events" in statement)
        self.assertIn('"execution_status": "awaiting_provider_configuration"', event[1])

    def test_catalonia_local_reference_resolution_is_not_shadowed_by_address_queue(self):
        class FakeDatabase:
            def __init__(self):
                self.statements = []
                self.next_id = 0

            def execute(self, statement, parameters=None):
                self.statements.append((str(statement), parameters))
                return self

            def fetchone(self):
                self.next_id += 1
                return (f"synthetic-id-{self.next_id}",)

        row = {"source_id": "es.cat.feed-sandach", "source_record_key": "synthetic-source-row",
               "source_values": {}, "normalized": {"establishment_id": "synthetic-catalan-group",
                   "country_code": "ES", "city": "Synthetic locality", "municipality_code": "080193",
                   "private_location_evidence": {"address": "1 Synthetic Road", "city": "Synthetic locality",
                                                   "country_code": "ES"}}}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "records.jsonl"
            path.write_text(json.dumps(row) + "\n", encoding="utf-8")
            db = FakeDatabase()
            with patch.object(IMPORTER, "persist_preview_candidate_assignment_set"):
                result = IMPORTER.import_rows(
                    db, "es.cat.feed-sandach", path, 1, "d" * 64,
                    municipality_index={"synthetic locality": {"latitude": 41.0, "longitude": 1.0}},
                    municipality_policy={"kind": "official_municipality_reference"},
                    source_artifact_sha256="e" * 64,
                    source_url="https://example.test/catalonia.csv",
                    source_retrieved_at=IMPORTER.datetime.fromisoformat("2026-10-01T00:00:00+00:00"),
                    source_artifact_byte_size=123,
                )
        statements = [statement for statement, _ in db.statements]
        self.assertFalse(any("INSERT INTO uec.geocode_jobs" in statement for statement in statements))
        self.assertEqual(result[13], 0)
        state = next(parameters for statement, parameters in db.statements
                     if "INSERT INTO real_preview.enrichment_state_events" in statement)
        self.assertEqual(state[2:4], ("synthetic-catalan-group", "resolved"))

    def test_import_rows_returns_unmapped_candidates_after_numeric_and_coarse_placeable_groups(self):
        class FakeDatabase:
            def __init__(self):
                self.next_id = 0

            def execute(self, statement, parameters=None):
                return self

            def fetchone(self):
                self.next_id += 1
                return (f"synthetic-{self.next_id}",)

        rows = [
            {"source_id": "us.fsis", "source_record_key": "numeric",
             "normalized": {"establishment_number": "numeric", "country_code": "US",
                            "coordinates": {"latitude": 40.0, "longitude": -75.0,
                                            "precision": "source-provided"}}},
            {"source_id": "us.fsis", "source_record_key": "coarse",
             "normalized": {"establishment_number": "coarse", "country_code": "US",
                            "city": "Example City", "postal_code": "12345"}},
            {"source_id": "us.fsis", "source_record_key": "unmapped",
             "normalized": {"establishment_number": "unmapped", "country_code": "US"}},
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "records.jsonl"
            path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            with patch.object(IMPORTER, "persist_preview_candidate_assignment_set"):
                result = IMPORTER.import_rows(
                    FakeDatabase(), "us.fsis", path, 3, "a" * 64,
                    municipality_index={"example city": {"latitude": 41.0, "longitude": -74.0}},
                    municipality_policy={},
                )
        self.assertEqual(result[1], 1, "numeric source point is map-placeable")
        self.assertEqual(result[2], 1, "city/postal candidate is coarse-placeable")
        self.assertEqual(result[3], 3)
        self.assertEqual(result[12], 1)
        self.assertEqual(result[13], 1, "only the candidate with no usable point remains unmapped")

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
        self.assertEqual(row[23], "synthetic-group")

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

    def test_australia_npi_source_coordinates_and_location_provenance_are_imported(self):
        row = IMPORTER.parse_row("au.npi.facilities", {
            "source_id": "au.npi.facilities", "source_record_key": "NPI-1",
            "normalized": {"establishment_id": "NPI-1", "name": "Sensitive facility",
                "city": "Example", "postal_code": "2000", "country_code": "AU",
                "coordinates": {"latitude": "-33.1", "longitude": "151.2", "precision": "source-provided",
                    "method": "source_coordinates", "provider": "Australian National Pollutant Inventory",
                    "confidence": "high_source_reported_location"},
                "coordinate_state": "source-coordinate", "coordinate_precision": "source-provided",
                "coordinate_method": "source_coordinates", "coordinate_provider": "Australian National Pollutant Inventory",
                "coordinate_confidence": "high_source_reported_location",
                "evidence_summary": "Coordinates supplied by official NPI facility record.",
                "privacy_gate": "pending-review", "in_default_map_scope": True,
                "map_scope_reason": "official_source_facility_coordinates"},
            "source_values": {"street_address": "1 private road", "latitude": "-33.1", "longitude": "151.2"},
        })
        self.assertEqual(row[1], "numeric_source_coordinate")
        self.assertEqual((row[2], row[3], row[4]), ("AU", "Example", "2000"))
        self.assertEqual((row[5], row[6]), (-33.1, 151.2))
        self.assertIsNone(row[11], "pending privacy must suppress the facility name")
        self.assertTrue(row[16], "valid source facility coordinates are map-visible in private preview")
        self.assertIn("Coordinates supplied", row[15])

    def test_australia_npi_rejects_coordinate_provenance_mismatch(self):
        with self.assertRaisesRegex(IMPORTER.ImportFailure, "source_coordinate_provenance_invalid"):
            IMPORTER.parse_row("au.npi.facilities", {
                "source_id": "au.npi.facilities", "source_record_key": "NPI-2",
                "normalized": {"establishment_id": "NPI-2", "country_code": "AU",
                    "coordinates": {"latitude": "-33.1", "longitude": "151.2", "precision": "source-provided",
                        "method": "source_coordinates", "provider": "unexpected source",
                        "confidence": "high_source_reported_location"},
                    "coordinate_method": "source_coordinates", "coordinate_provider": "unexpected source",
                    "coordinate_confidence": "high_source_reported_location",
                    "coordinate_precision": "source-provided"},
                "source_values": {},
            })
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
        self.assertEqual(row[23], "synthetic-group")

    def test_import_creates_unmapped_source_group_candidate_with_scope_metadata(self):
        class Result:
            def __init__(self, row=("opaque-preview-observation",), rows=None):
                self.row = row
                self.rows = [] if rows is None else rows

            def fetchone(self):
                return self.row

            def fetchall(self):
                return self.rows

        class Database:
            def __init__(self):
                self.candidates = []
                self.crosswalk_digest = None
                self.assignments = []

            def execute(self, sql, params=()):
                if "INSERT INTO real_preview.candidates" in sql:
                    self.candidates.append((sql, params))
                if "INSERT INTO real_preview.taxonomy_crosswalks" in sql:
                    self.crosswalk_digest = params[5]
                if "INSERT INTO real_preview.candidate_taxonomy_assignments" in sql:
                    self.assignments.append((sql, params))
                if "SELECT definition_sha256" in sql:
                    return Result((self.crosswalk_digest,))
                if "SELECT assignment_ordinal" in sql:
                    return Result(rows=[])
                if "SELECT candidate_id FROM real_preview.candidates" in sql:
                    return Result(("synthetic-candidate",))
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
        self.assertGreaterEqual(len(database.assignments), 1)
        self.assertIn("real_preview.candidate_taxonomy_assignments", database.assignments[0][0])
        sql, params = database.candidates[0]
        self.assertIn("default_map_scope,map_scope_reason", sql)
        self.assertEqual(params[4], "unmapped_private_observation")
        self.assertFalse(params[22])
        self.assertEqual(params[23], "general-food")
        self.assertEqual(params[3], "opaque-preview-observation", "candidate retains lineage to its observation")
        self.assertEqual(params[30], "slaughter")
        self.assertEqual(params[31], ["slaughter", "processing_and_preparation"])
        self.assertEqual(params[32], ["EB.03.21.00", "EB.10.10.99"])
        self.assertEqual(params[33], ["Fish plant", "Slaughterhouse"])
        self.assertEqual(params[34], "mapped")
        self.assertEqual(params[35], "denmark-classification-v1")

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
