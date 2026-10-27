"""Synthetic provenance and privacy checks for MX/NZ private imports."""

from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import unittest


IMPORTER_PATH = Path(__file__).parents[1] / "scripts" / "maintenance" / "import-real-preview.py"
IMPORTER_SPEC = importlib.util.spec_from_file_location("import_real_preview_launch_country", IMPORTER_PATH)
IMPORTER = importlib.util.module_from_spec(IMPORTER_SPEC)
assert IMPORTER_SPEC.loader
IMPORTER_SPEC.loader.exec_module(IMPORTER)


class LaunchCountryPreviewTests(unittest.TestCase):
    def _case(self, source_id: str):
        now = datetime.now(timezone.utc).replace(microsecond=0)
        retrieved = now.isoformat().replace("+00:00", "Z")
        source_url = ("https://www.inegi.org.mx/app/api/denue/v1/consulta/" if source_id == "mx.locations" else
                      "https://mpi.my.site.com/publicregister/s/RiskMeasureSearch?riskMeasureType=Risk%20Management%20Programme")
        code = "mx-denue-v1" if source_id == "mx.locations" else "nz-mpi-rmp-csv-v3"
        schema = "denue-api-v1" if source_id == "mx.locations" else "nz-mpi-rmp-extract-2026-10-v1"
        digest, size = "a" * 64, 4096
        manifest = {"source_id": source_id, "source_url": source_url, "retrieved_at_utc": retrieved,
                    "byte_size": size, "normalized_rows": 2}
        policy = {"source_url": source_url, "freshness_max_days": 60,
                  "adapter_version": code, "schema_version": schema}
        summary = {"retrieved_at_utc": retrieved}
        if source_id == "mx.locations":
            summary.update({"source_canonical_url": source_url, "source_artifact_sha256": digest,
                            "source_artifact_byte_size": size, "input_rows": 2,
                            "preflight_rows": 2, "request_count": 4})
        else:
            summary.update({"source_url": source_url, "candidate_handoff": True,
                            "candidate_observation_rows": 2})
        source_result = {"source_id": source_id, "mode": "local-artifact",
                         "acquisition_classification": "assisted", "summary": summary,
                         "operational": {"adapter_version": code,
                                         "acquisition_timestamp_utc": retrieved,
                                         "artifact": {"available": True, "sha256": digest, "byte_size": size}}}
        runtime = {"run_id": "refresh-synthetic", "mode": "local-artifact",
                   "exit_status": "ok", "selected_sources": [source_id]}
        return manifest, policy, summary, source_result, runtime, digest, now, code, schema

    def test_source_native_names_activity_addresses_and_cardinality_are_private_fields(self):
        policies = json.loads(IMPORTER.POLICY.read_text(encoding="utf-8"))["sources"]
        mexico = {"establishment_id": "MX-1", "clee": "MX-CLEE-1", "name": "Nombre reservado",
                  "operator_name": "Operador reservado", "country_code": "MX",
                  "facility_address": "Calle privada 1", "activity_class_id": "311611",
                  "activity_name": "Matanza de ganado", "activity_categories": ["slaughter"],
                  "classification_state": "mapped", "coordinates": {"latitude": 19.4, "longitude": -99.1},
                  "coordinate_precision": "unknown", "privacy_gate": "pending-review",
                  "coordinate_gate": "review_required", "publication_gate": "blocked"}
        nz = {"establishment_id": "MPI-1", "mpi_risk_measure_id": "MPI-1",
              "source_entity_type": "registered-risk-management-programme",
              "facility_identity_state": "programme-record; location cardinality is source-reported and may be multiple",
              "name": "Private operator", "trading_name": "Private trading name", "country_code": "NZ",
              "programme_type": "Animal Products RMP", "product_material": "Meat",
              "primary_activity": "Processing", "address": "Private physical address",
              "municipality": "Exampletown", "location_count": 3, "location_count_state": "source-reported",
              "coordinates": None, "coordinate_state": "not-supplied-by-source",
              "privacy_gate": "pending-review", "rights_gate": "review_required",
              "coordinate_gate": "review_required", "publication_gate": "blocked"}
        for source_id, normalized in (("mx.locations", mexico), ("nz.locations", nz)):
            with self.subTest(source_id=source_id):
                self.assertFalse(set(normalized) - set(policies[source_id]["allowed_preview_fields"]))
                parsed = IMPORTER.parse_row(source_id, {
                    "source_id": source_id, "source_record_key": normalized["establishment_id"],
                    "normalized": normalized, "source_values": {},
                })
                self.assertEqual(parsed[11], normalized["name"])
                self.assertEqual(parsed[18], normalized.get("facility_address", normalized.get("address")))
                self.assertEqual(parsed[3], "Exampletown" if source_id == "nz.locations" else None)
                if source_id == "mx.locations":
                    self.assertEqual(parsed[7], "source-precision-unknown")
                    self.assertEqual(parsed[5:7], (19.4, -99.1))
                else:
                    self.assertIsNone(parsed[5])
                    self.assertEqual(parsed[23], "MPI-1")
                    self.assertEqual(normalized["source_entity_type"], "registered-risk-management-programme")
                    self.assertEqual(normalized["location_count"], 3)

    def test_verified_mexico_capture_is_preserved_not_called_fresh(self):
        values = self._case("mx.locations")
        evidence = IMPORTER.validate_country_capture_binding(
            "mx.locations", values[0], values[4], values[3], values[2], values[1],
            values[5], values[6], values[7], values[8])
        provenance = IMPORTER.source_processing_provenance(
            "mx.locations", values[4], values[3], evidence, values[5], values[6], "refresh-synthetic",
            archived_replay=False, archived_replay_evidence=None, france_local_replay_evidence=None)
        self.assertFalse(provenance["fresh_live_run"])
        self.assertEqual(provenance["processing_mode"], "verified_preserved_live_capture_processing")
        self.assertEqual(provenance["acquisition_classification"], "live")

    def test_new_zealand_assisted_csv_never_claims_fresh_automation(self):
        values = self._case("nz.locations")
        evidence = IMPORTER.validate_country_capture_binding(
            "nz.locations", values[0], values[4], values[3], values[2], values[1],
            values[5], values[6], values[7], values[8])
        provenance = IMPORTER.source_processing_provenance(
            "nz.locations", values[4], values[3], evidence, values[5], values[6], "refresh-synthetic",
            archived_replay=False, archived_replay_evidence=None, france_local_replay_evidence=None)
        self.assertFalse(provenance["fresh_live_run"])
        self.assertEqual(provenance["processing_mode"], "assisted_local_artifact_processing")
        self.assertEqual(provenance["acquisition_classification"], "assisted")

    def test_hash_size_schema_source_and_url_mismatches_fail_closed(self):
        for source_id in ("mx.locations", "nz.locations"):
            for mutation in ("hash", "size", "schema", "source", "url"):
                with self.subTest(source_id=source_id, mutation=mutation):
                    values = list(self._case(source_id))
                    if mutation == "hash":
                        values[3]["operational"]["artifact"]["sha256"] = "b" * 64
                    elif mutation == "size":
                        values[3]["operational"]["artifact"]["byte_size"] += 1
                    elif mutation == "schema":
                        values[8] = "wrong-schema"
                    elif mutation == "source":
                        values[4]["selected_sources"] = ["other.source"]
                    else:
                        values[2]["source_url"] = "https://example.invalid/"
                        values[2]["source_canonical_url"] = "https://example.invalid/"
                    with self.assertRaises(IMPORTER.ImportFailure):
                        IMPORTER.validate_country_capture_binding(
                            source_id, values[0], values[4], values[3], values[2], values[1],
                            values[5], values[6], values[7], values[8])

    def test_live_classification_and_timestamp_mismatch_fail_closed(self):
        for source_id in ("mx.locations", "nz.locations"):
            with self.subTest(source_id=source_id, mutation="live"):
                values = list(self._case(source_id))
                values[3]["acquisition_classification"] = "live"
                with self.assertRaises(IMPORTER.ImportFailure):
                    IMPORTER.validate_country_capture_binding(
                        source_id, values[0], values[4], values[3], values[2], values[1],
                        values[5], values[6], values[7], values[8])
            with self.subTest(source_id=source_id, mutation="timestamp"):
                values = list(self._case(source_id))
                values[2]["retrieved_at_utc"] = "2026-01-01T00:00:00Z"
                with self.assertRaises(IMPORTER.ImportFailure):
                    IMPORTER.validate_country_capture_binding(
                        source_id, values[0], values[4], values[3], values[2], values[1],
                        values[5], values[6], values[7], values[8])


if __name__ == "__main__":
    unittest.main()
