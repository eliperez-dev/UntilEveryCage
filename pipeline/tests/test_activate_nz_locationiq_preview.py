from __future__ import annotations

import importlib.util
from datetime import datetime, timezone
from pathlib import Path
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "stages" / "activate-nz-locationiq-preview.py"
SPEC = importlib.util.spec_from_file_location("activate_nz_locationiq_preview", SCRIPT)
activation = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(activation)


class ActivateNzLocationIqPreviewTests(unittest.TestCase):
    def _binding(self):
        retrieved = datetime.now(timezone.utc).replace(microsecond=0)
        digest, normalized = "a" * 64, "b" * 64
        run = {"snapshot_sha256": "c" * 64, "source_artifact_sha256": digest,
               "source_url": activation.SOURCE_URL, "retrieved_at": retrieved,
               "normalized_sha256": normalized, "imported_observation_count": 3,
               "adapter_version": "adapter-v2", "schema_version": "schema-v1",
               "processing_mode": "assisted_local_artifact_processing",
               "acquisition_classification": "assisted"}
        manifest = {"source_artifact_sha256": digest, "normalized_sha256": normalized,
                    "source_url": activation.SOURCE_URL, "retrieved_at": retrieved,
                    "normalized_rows": 3, "code_version": "adapter-v2",
                    "config_version": "schema-v1"}
        acquisition = {"source_id": activation.SOURCE_ID, "source_url": activation.SOURCE_URL,
                       "source_artifact_sha256": digest, "source_artifact_byte_size": 1234,
                       "retrieved_at_utc": retrieved.isoformat(), "adapter_version": "adapter-v2",
                       "schema_version": "schema-v1", "runner_run_id": "refresh-abc",
                       "source_processing_mode": "local-artifact"}
        return run, manifest, acquisition

    def test_source_binding_requires_matching_manifest_and_runner_artifact(self):
        run, manifest, acquisition = self._binding()
        binding = activation._validate_source_binding(run, manifest, acquisition)
        self.assertEqual(binding["source_artifact_sha256"], "a" * 64)
        self.assertEqual(binding["source_artifact_byte_size"], 1234)
        for field, value in (("source_artifact_sha256", "d" * 64),
                             ("source_artifact_byte_size", 0),
                             ("runner_run_id", ""),
                             ("source_processing_mode", "network")):
            with self.subTest(field=field):
                broken = {**acquisition, field: value}
                with self.assertRaises(ValueError):
                    activation._validate_source_binding(run, manifest, broken)
        broken_manifest = {**manifest, "normalized_rows": 4}
        with self.assertRaises(ValueError):
            activation._validate_source_binding(run, broken_manifest, acquisition)

    def test_projection_key_is_exact_snapshot_and_native_group_key(self):
        self.assertEqual(activation._projection_source_record_key("c" * 64, "MPI-123"),
                         f"real-preview:{'c' * 64}:MPI-123")
        for snapshot, key in (("bad", "MPI-123"), ("c" * 64, " ")):
            with self.subTest(snapshot=snapshot, key=key), self.assertRaises(ValueError):
                activation._projection_source_record_key(snapshot, key)

    def test_source_linkage_uses_verified_artifact_and_projection_identity(self):
        class FakeConnection:
            def __init__(self):
                self.calls = []

            def execute(self, sql, params=()):
                self.calls.append((sql, params))
                if "SELECT country_code" in sql:
                    return type("Result", (), {"fetchone": lambda self: (
                        "NZ", activation.SOURCE_URL, "private_preview_address_enrichment")})()
                if "SELECT artifact_id,byte_size" in sql:
                    return type("Result", (), {"fetchone": lambda self: (71, 1234)})()
                if "SELECT source_record_id,artifact_id,raw_fields" in sql:
                    return type("Result", (), {"fetchone": lambda self: (
                        92, 71, {"projection": "real_preview_private_geocode_target",
                                 "snapshot_sha256": "c" * 64})})()
                return type("Result", (), {"fetchone": lambda self: None})()

        connection = FakeConnection()
        run, manifest, acquisition = self._binding()
        metadata = activation._validate_source_binding(run, manifest, acquisition)
        record_id = activation._ensure_source_linkage(
            connection, snapshot="c" * 64, source_group_key="MPI-123", metadata=metadata)
        self.assertEqual(record_id, 92)
        artifact_insert = next(params for sql, params in connection.calls if "INSERT INTO uec.raw_artifacts" in sql)
        self.assertEqual(artifact_insert[0], f"private-preview-source-artifact:{activation.SOURCE_ID}:{'a' * 64}")
        record_insert = next(params for sql, params in connection.calls if "INSERT INTO uec.source_records" in sql)
        self.assertEqual(record_insert[1], f"real-preview:{'c' * 64}:MPI-123")
        self.assertEqual(record_insert[2], 71)

    def test_query_uses_only_physical_address_town_and_country(self):
        location = {
            "address": "  12  Example Street ", "city": " Wellington ",
            "country_code": "NZ", "location_count": 1,
            "number_of_locations": "1", "name": "Never query this name",
            "operator_name": "Never query a person",
        }
        self.assertEqual(activation._query_from_location(location),
                         "12 Example Street, Wellington, New Zealand")
        with_postcode = {**location, "postal_code": "6011"}
        self.assertEqual(activation._query_from_location(with_postcode),
                         "12 Example Street, 6011, Wellington, New Zealand")

    def test_rejects_non_single_location_coordinates_and_invalid_locality(self):
        base = {"address": "12 Example Street", "city": "Wellington", "country_code": "NZ",
                "location_count": 1, "number_of_locations": "1"}
        for change in (
            {"location_count": 2}, {"location_count": True}, {"number_of_locations": "2"},
            {"coordinates": {"latitude": -41.2, "longitude": 174.7}},
            {"latitude": -41.2}, {"country_code": "AU"}, {"address": ""}, {"city": ""},
            {"address": "Main Street"}, {"postal_code": "6011 1"},
        ):
            with self.subTest(change=change):
                self.assertIsNone(activation._query_from_location({**base, **change}))

    def test_sql_is_current_snapshot_private_and_deduplicates_without_geoapify_dependency(self):
        sql = activation._LATEST_CANDIDATES_SQL
        self.assertIn("ORDER BY created_at DESC,run_id DESC", activation._LATEST_RUN_SQL)
        self.assertIn("candidate_private_location_evidence", sql)
        self.assertIn("location_evidence->'location_count'='1'::jsonb", sql)
        self.assertIn("FROM uec.public_access_restricted", sql)
        self.assertIn("result.status='accepted'", sql)
        self.assertIn("job.provider_id='locationiq'", sql)
        self.assertIn("FOR UPDATE OF candidate SKIP LOCKED", sql)
        self.assertNotIn("geoapify", sql.casefold())
        self.assertNotIn("name", sql.casefold())

    def test_limit_is_finite(self):
        for limit in (0, 5001):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                activation.activate("unused", limit=limit)


if __name__ == "__main__":
    unittest.main()
