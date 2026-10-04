import hashlib, importlib.util, tempfile, unittest
import json
from pathlib import Path
from .adapter import DenmarkSmileyAdapter, check_refresh
from pipeline.contracts.adapter_contract import SourceArtifact
from pipeline.common.orchestrator import run_private_lifecycle
from pipeline.common.review_metrics import build_private_review_metrics
from .pipeline import _materialize_validated_rows, _write_geocode_eligible_candidates

_CLASSIFIER_PATH = Path(__file__).parent / "stages" / "classify-denmark.py"
_CLASSIFIER_SPEC = importlib.util.spec_from_file_location("denmark_classifier", _CLASSIFIER_PATH)
CLASSIFIER = importlib.util.module_from_spec(_CLASSIFIER_SPEC)
assert _CLASSIFIER_SPEC and _CLASSIFIER_SPEC.loader
_CLASSIFIER_SPEC.loader.exec_module(CLASSIFIER)

XML = b'<Root><Row><ID_nummer>1</ID_nummer><Virksomhed>Test</Virksomhed></Row><Row><Virksomhed>Unkeyed</Virksomhed></Row></Root>'

class DenmarkAdapterTests(unittest.TestCase):
    def artifact(self, data=XML):
        return SourceArtifact("https://example.test/smiley.xml", "2026-01-01T00:00:00Z", hashlib.sha256(data).hexdigest(), len(data), code_version="test", config_version="test")

    def test_denmark_classifier_keeps_raw_values_all_recognized_activities_and_unknowns_unclassified(self):
        rules = json.loads((Path(__file__).parents[2] / "config" / "denmark-classification-v1.json").read_text(encoding="utf-8"))
        row = {"activity": {"code": ["EB.10.10.99", "EB.10.10.13"],
                            "labels": ["source label", "alternate source label"],
                            "category": "source category", "category_labels": ["source category", "alternate category"]}}
        classified = CLASSIFIER.classify_record(row, rules)
        self.assertEqual(classified["source_classification"]["codes"], ["EB.10.10.99", "EB.10.10.13"])
        self.assertEqual(classified["source_classification"]["labels"], ["source label", "alternate source label"])
        self.assertEqual(classified["source_classification"]["category_labels"], ["source category", "alternate category"])
        self.assertEqual(classified["classification"]["activity_categories"], ["slaughter", "meat_processing"])
        self.assertEqual(classified["classification"]["category"], "slaughter")
        self.assertEqual(classified["classification"]["mapping_status"], "mapped")

        unknown = CLASSIFIER.classify_record({"activity": {"code": "NEW.CODE", "label": "Unknown source label"}}, rules)
        self.assertIsNone(unknown["classification"]["category"])
        self.assertEqual(unknown["classification"]["activity_categories"], [])
        self.assertEqual(unknown["classification"]["mapping_status"], "unmapped")
        self.assertEqual(unknown["source_classification"]["codes"], ["NEW.CODE"])

    def test_rerun_is_deterministic_and_private(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); raw = root / "raw.xml"; raw.write_bytes(XML)
            a = DenmarkSmileyAdapter().run(raw, root / "one", self.artifact())
            b = DenmarkSmileyAdapter().run(raw, root / "two", self.artifact())
            self.assertEqual(a, b); self.assertEqual(a["quarantined_rows"], 1)
            self.assertFalse((root / "one" / "released").exists())

    def test_failed_acquisition_does_not_write_staging(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); raw = root / "raw.xml"; raw.write_bytes(XML)
            with self.assertRaises(ValueError): DenmarkSmileyAdapter().run(raw, root / "run", self.artifact(b"wrong"))
            self.assertFalse((root / "run").exists())

    def test_registered_bridge_requires_and_checks_provenance(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); raw = root / "raw.xml"; raw.write_bytes(XML)
            adapter = DenmarkSmileyAdapter()
            with self.assertRaisesRegex(ValueError, "missing acquisition provenance"):
                adapter.run_registered(raw, root / "missing", {})
            config = {"source_url": "https://example.test/source.xml", "retrieved_at_utc": "2026-01-01T00:00:00Z", "checksum_sha256": "0" * 64, "byte_size": len(XML)}
            with self.assertRaisesRegex(ValueError, "integrity mismatch"):
                adapter.run_registered(raw, root / "bad", config)
            config["checksum_sha256"] = hashlib.sha256(XML).hexdigest()
            manifest = adapter.run_registered(raw, root / "good", config)
            self.assertEqual(manifest["acquisition"]["source_url"], config["source_url"])

    def test_candidate_mapping_preserves_source_values_and_pending_gates(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); raw = root / "raw.xml"; raw.write_bytes(XML)
            parsed = {"source_id": "dk.smiley", "source_row": 2, "source_record_key": "1", "source_fields": {"ID_nummer": "1", "Virksomhed": "Test", "Adresse": "Road 1"}, "classification": {"category": "general_food_business", "review_status": "approved", "default_visible": False, "optional_filter": "general-food"}}
            manifest = DenmarkSmileyAdapter().write_candidate_handoff(root / "handoff", self.artifact(), [parsed])
            self.assertEqual(manifest["privacy_gate"], "pending")
            handoff = json.loads((root / "handoff" / "normalized/records.jsonl").read_text())
            self.assertEqual(handoff["source_values"]["ID_nummer"], "1")
            self.assertEqual(handoff["source_record_key"], "1")
            self.assertEqual(handoff["normalized"]["establishment_id"], "1")
            self.assertEqual(handoff["normalized"]["classification_category"], "general_food_business")
            self.assertFalse(handoff["normalized"]["in_default_map_scope"])
            self.assertEqual(handoff["normalized"]["private_location_evidence"]["address"], "Road 1")
            self.assertEqual(handoff["normalized"]["private_location_evidence"]["address_lines"], ["Road 1"])

    def test_candidate_mapping_preserves_denmark_classification_fields_and_all_activities(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); raw = root / "raw.xml"; raw.write_bytes(XML)
            fields = {"ID_nummer": "1", "FVST_branchenummer": "EB.10.10.99",
                      "FVST_branche": "Slaughterhouse", "Smileybranche": "Animal food business"}
            parsed = {"source_id": "dk.smiley", "source_row": 2, "source_record_key": "1",
                      "source_fields": fields,
                      "location": {
                          "source_address_eligible": True,
                          "source_address_restricted": False,
                          "source_scope_eligible": True,
                          "exact_geocode_candidate_state": "eligible_pending_queue",
                          "exact_geocode_eligible": False,
                          "privacy_status": "eligible",
                          "exact_geocode_candidate": {"source_eligible": True, "eligible": False,
                                                       "address": {"country_code": "DK"}},
                      },
                      "source_classification": {"codes": ["EB.10.10.99", "EB.10.10.13"],
                                                 "labels": ["Slaughterhouse", "Meat processing"]},
                      "classification": {"category": "slaughter", "activity_categories": ["slaughter", "meat_processing"],
                                         "mapping_status": "mapped", "ruleset_id": "denmark-classification-v1",
                                         "review_status": "approved", "default_visible": True,
                                         "private_geocode_scope": "animal_product_production_and_processing",
                                         "private_geocode_scope_policy_id": "denmark-private-geocode-scope-v1",
                                         "optional_filter": "production-and-processing"}}
            DenmarkSmileyAdapter().write_candidate_handoff(root / "handoff", self.artifact(), [parsed])
            handoff = json.loads((root / "handoff" / "normalized/records.jsonl").read_text())
            normalized = handoff["normalized"]
            self.assertEqual(handoff["source_values"], fields)
            self.assertEqual(normalized["source_classification_code"], "EB.10.10.99")
            self.assertEqual(normalized["source_classification_label"], "Slaughterhouse")
            self.assertEqual(normalized["activity_codes"], ["EB.10.10.99", "EB.10.10.13"])
            self.assertEqual(normalized["activity_categories"], ["slaughter", "meat_processing"])
            self.assertEqual(normalized["classification_ruleset_version"], "denmark-classification-v1")
            self.assertTrue(normalized["source_address_eligible"])
            self.assertTrue(normalized["exact_geocode_candidate"]["source_eligible"])
            self.assertFalse(normalized["exact_geocode_eligible"])
            self.assertEqual(normalized["exact_geocode_candidate_state"], "eligible_pending_queue")
            self.assertNotIn("source_address_eligible", normalized["private_location_evidence"])

    def test_candidate_mapping_does_not_invent_missing_address_eligibility(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            row = {"source_id": "dk.smiley", "source_row": 1, "source_record_key": "missing-flags",
                   "source_fields": {"ID_nummer": "missing-flags", "Adresse": "Synthetic Road 1"},
                   "classification": {"review_status": "approved"}}
            DenmarkSmileyAdapter().write_candidate_handoff(root / "handoff", self.artifact(), [row])
            handoff = json.loads((root / "handoff" / "normalized/records.jsonl").read_text())
            normalized = handoff["normalized"]
            self.assertNotIn("source_address_eligible", normalized)
            self.assertNotIn("exact_geocode_candidate", normalized)

    def test_normalization_and_private_handoff_keep_all_codes_labels_and_observation_date(self):
        from pipeline.sources.denmark.stages import __path__ as _stages_path
        normalize_script = Path(_stages_path[0]) / "normalize-denmark-smiley.py"
        spec = importlib.util.spec_from_file_location("denmark_normalizer", normalize_script)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)
        source = {"ID_nummer": "1", "Adresse": "Industrial Road 2", "Postnummer": "0123", "By": "Testby",
                  "FVST_branchenummer": "EB.10.10.99", "brancheKode": "EB.10.10.13",
                  "FVST_branche": "Slagterier", "branche": "Fremstilling af animalske produkter - Kød",
                  "Smileybranche": "Animalske produkter", "Pixibranche": "Kødprodukter",
                  "Seneste_kontrol_dato": "02/09/2024"}
        normalized = module.normalize_record({"source_row": 1, "fields": source})
        self.assertEqual(normalized["activity"]["codes"], ["EB.10.10.99", "EB.10.10.13"])
        self.assertEqual(normalized["activity"]["labels"], ["Slagterier", "Fremstilling af animalske produkter - Kød"])
        self.assertEqual(normalized["source_observation_date"], "2024-09-02")
        self.assertEqual(normalized["source_fields"], source)

    def test_refresh_guards_reject_schema_count_and_duplicate_drift(self):
        with self.assertRaisesRegex(ValueError, "schema"):
            check_refresh({"source_id":"dk.smiley", "schema_version":"a", "normalized_rows":10}, {"source_id":"dk.smiley", "schema_version":"b", "normalized_rows":10})
        with self.assertRaisesRegex(ValueError, "count"):
            check_refresh({"source_id":"dk.smiley", "schema_version":"a", "normalized_rows":100}, {"source_id":"dk.smiley", "schema_version":"a", "normalized_rows":50})
        duplicate = {"source_id":"dk.smiley", "source_row":3, "source_record_key":"1", "source_fields":{}}
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError, "duplicate"):
                DenmarkSmileyAdapter().write_candidate_handoff(Path(d), self.artifact(), [duplicate, duplicate])

    def test_canonical_lifecycle_emits_private_qa_status_and_deterministic_health(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); raw = root / "raw.xml"; raw.write_bytes(XML)
            first = run_private_lifecycle(raw, root / "runs-one", self.artifact(), DenmarkSmileyAdapter())
            second = run_private_lifecycle(raw, root / "runs-two", self.artifact(), DenmarkSmileyAdapter())
            self.assertEqual(first["status"], "candidate-ready")
            self.assertEqual(first["manifest"]["contract_version"], "source-lifecycle-v1")
            self.assertEqual(first["manifest"], second["manifest"])
            first_dir, second_dir = Path(first["run_dir"]), Path(second["run_dir"])
            self.assertTrue((first_dir / "qa.json").is_file())
            self.assertTrue((first_dir / "run-status.json").is_file())
            self.assertTrue((first_dir / "source-health.json").is_file())
            self.assertEqual((first_dir / "source-health.json").read_bytes(), (second_dir / "source-health.json").read_bytes())
            health = json.loads((first_dir / "source-health.json").read_text())
            self.assertEqual(health["health_state"], "private-validated")
            self.assertFalse(health["public_exposure"])
            self.assertNotIn("source_values", (first_dir / "source-health.json").read_text())

    def test_canonical_lifecycle_rejects_malformed_xml_without_health(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); raw = root / "bad.xml"; raw.write_bytes(b"<Root><Row>")
            status = run_private_lifecycle(raw, root / "runs", self.artifact(raw.read_bytes()), DenmarkSmileyAdapter())
            self.assertEqual(status["status"], "failed")
            run_dir = Path(status["run_dir"])
            self.assertFalse((run_dir / "source-health.json").exists())
            self.assertFalse((run_dir / "release-candidate" / "records.jsonl").exists())

    def test_validation_findings_are_quarantined_before_candidate_handoff(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "03-classify").mkdir()
            (root / "04-validate").mkdir()
            good = {"source_id": "dk.smiley", "source_row": 1, "source_record_key": "good", "classification": {"review_status": "approved"}}
            bad = {"source_id": "dk.smiley", "source_row": 2, "source_record_key": "bad", "classification": {"review_status": "review_required"}}
            (root / "03-classify/classified-records.jsonl").write_text(
                json.dumps(good) + "\n" + json.dumps(bad) + "\n", encoding="utf-8"
            )
            (root / "04-validate/validation-findings.jsonl").write_text(
                json.dumps({"record": bad, "findings": [{"severity": "review", "code": "classification_requires_review"}]}) + "\n",
                encoding="utf-8",
            )
            accepted, quarantined, findings = _materialize_validated_rows(root)
            self.assertEqual([row["source_record_key"] for row in accepted], ["good"])
            self.assertEqual([row["source_record_key"] for row in quarantined], ["bad"])
            self.assertEqual(len(findings), 1)

    def test_review_metrics_understand_denmark_source_coordinates(self):
        metrics = build_private_review_metrics([
            {"source_id": "dk.smiley", "source_record_key": "1", "normalized": {
                "coordinates": {"latitude": "55.5", "longitude": "12.3", "method": "source", "review_status": "source"},
            }},
            {"source_id": "dk.smiley", "source_record_key": "2", "normalized": {
                "coordinates": {"latitude": None, "longitude": None, "method": None, "review_status": "unresolved"},
            }},
        ])
        self.assertEqual(metrics["geospatial"]["coordinate_state_counts"], {"source_point": 1, "unresolved": 1})

    def test_geocode_queue_contains_only_candidates_that_pass_all_gates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "records.jsonl"
            target = root / "eligible.jsonl"
            records = [
                {"source_record_key": "held", "coordinates": {"latitude": None, "longitude": None},
                 "location": {"exact_geocode_eligible": False,
                              "exact_geocode_candidate_state": "held_for_privacy_review"}},
                {"source_record_key": "eligible", "coordinates": {"latitude": None, "longitude": None},
                 "location": {"exact_geocode_eligible": True,
                              "source_address_eligible": True,
                              "exact_geocode_candidate_state": "eligible_pending_queue",
                              "exact_geocode_candidate": {"eligible": True, "source_eligible": True}}},
                {"source_record_key": "source-point", "coordinates": {"latitude": 55.5, "longitude": 12.3},
                 "location": {"exact_geocode_eligible": False,
                              "exact_geocode_candidate_state": "insufficient_location_fields"}},
            ]
            source.write_text("\n".join(json.dumps(item) for item in records) + "\n", encoding="utf-8")

            summary = _write_geocode_eligible_candidates(source, target)

            self.assertEqual(summary["records_seen"], 3)
            self.assertEqual(summary["unresolved_records"], 2)
            self.assertEqual(summary["source_coordinate_records"], 1)
            self.assertEqual(summary["eligible_records"], 1)
            self.assertEqual(summary["eligibility_state_counts"]["held_for_privacy_review"], 1)
            self.assertFalse(summary["geocoder_called"])
            queued = [json.loads(line) for line in target.read_text(encoding="utf-8").splitlines()]
            self.assertEqual([item["source_record_key"] for item in queued], ["eligible"])

    def test_only_core_facility_activity_codes_make_private_address_queue_candidates(self):
        rules = json.loads((Path(__file__).parents[2] / "config" / "denmark-classification-v1.json").read_text(encoding="utf-8"))
        for code, expected in (("EB.10.10.99", True), ("EB.10.50.00", True),
                               ("DD.56.10.99", False), ("DD.47.22.00", False),
                               ("00.00.02.A", False), ("NEW.CODE", False)):
            record = {"source_id": "dk.smiley", "source_record_key": code,
                      "source_fields": {"Adresse": "Example Street 1", "Postnummer": "1234", "By": "Exampleby"},
                      "address": {"street": "Example Street 1", "postal_code": "1234", "city": "Exampleby", "country_code": "DK"},
                      "coordinates": {"latitude": None, "longitude": None},
                      "activity": {"code": code, "label": f"source label {code}"}}
            classified = CLASSIFIER.classify_record(record, rules)
            self.assertEqual(classified["location"]["source_address_eligible"], expected, code)
            self.assertEqual(classified["classification"]["default_visible"], expected, code)

    def test_local_acquisition_keeps_fixed_provenance_for_reruns(self):
        path = Path(__file__).parents[2] / "sources" / "denmark" / "stages" / "acquire-denmark-smiley.py"
        spec = importlib.util.spec_from_file_location("denmark_acquire_test", path)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.xml"
            source.write_bytes(b"<Root />")
            metadata = module.archive_local_file(
                source,
                root / "raw",
                run_id="fixed",
                retrieved_at="2026-09-14T05:41:12Z",
                source_url="https://pub.fvst.dk/publikationer/Smileydata.xml",
            )
            self.assertEqual(metadata["final_url"], "https://pub.fvst.dk/publikationer/Smileydata.xml")
            self.assertEqual(metadata["retrieved_at_utc"], "2026-09-14T05:41:12Z")

if __name__ == "__main__": unittest.main()
