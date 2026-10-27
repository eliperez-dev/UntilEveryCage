from __future__ import annotations

import importlib.util
from datetime import datetime, timezone, timedelta
from pathlib import Path
import unittest

SCRIPT = (Path(__file__).resolve().parents[1] / "scripts" / "stages"
          / "activate-uk-locationiq-preview.py")
SPEC = importlib.util.spec_from_file_location("activate_uk_locationiq_preview", SCRIPT)
activation = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(activation)


class ActivateUkLocationIqPreviewTests(unittest.TestCase):
    def test_helper_emits_name_free_canonical_road_query(self):
        self.assertEqual(activation.canonical_uk_query(
            ["Example Foods Ltd", "Unit 4, 12 Example Road", "London"],
            "London", "sw1a1aa"),
            "12 Example Road, London, SW1A 1AA, United Kingdom")
        self.assertIsNone(activation.canonical_uk_query(
            ["12 Example Road", "14 Example Lane"], "London", "SW1A 1AA"))
        self.assertIsNone(activation.canonical_uk_query(["12 Example Road"], None, "SW1A 1AA"))
        self.assertIsNone(activation.canonical_uk_query(["Example Foods Ltd"], "London", "SW1A 1AA"))

    def _provenance(self, source=activation.FSA):
        retrieved = datetime.now(timezone.utc).replace(microsecond=0)
        artifact_hash, normalized_hash = "a" * 64, "b" * 64
        run = {"run_id": "refresh-uk-1", "snapshot_sha256": "c" * 64,
               "source_artifact_sha256": artifact_hash, "source_url": activation.SOURCE_URLS[source],
               "retrieved_at": retrieved, "normalized_sha256": normalized_hash,
               "imported_observation_count": 42, "adapter_version": "adapter-v2",
               "schema_version": "schema-v1", "processing_mode": "live_acquisition",
               "acquisition_classification": "live", "fresh_live_run": True}
        manifest = {"source_artifact_sha256": artifact_hash, "normalized_sha256": normalized_hash,
                    "source_url": activation.SOURCE_URLS[source], "retrieved_at": retrieved,
                    "normalized_rows": 42, "code_version": "adapter-v2", "config_version": "schema-v1"}
        acquisition = {"source_id": source, "run_id": "refresh-uk-1", "sha256": artifact_hash,
                       "byte_size": 1024, "final_url": activation.SOURCE_URLS[source],
                       "retrieved_at_utc": retrieved.isoformat(), "adapter_version": "adapter-v2",
                       "config_version": "schema-v1", "terms_review": {"decision": "approved"}}
        return run, manifest, acquisition

    def test_provenance_requires_live_artifact_and_approved_terms(self):
        run, manifest, acquisition = self._provenance()
        self.assertEqual(activation._validate_provenance(activation.FSA, run, manifest, acquisition)[
            "source_artifact_sha256"], "a" * 64)
        for broken in ({**acquisition, "sha256": "d" * 64},
                       {**acquisition, "terms_review": {"decision": "pending"}},
                       {**acquisition, "final_url": "https://example.invalid/source.csv"}):
            with self.subTest(broken=broken), self.assertRaises(ValueError):
                activation._validate_provenance(activation.FSA, run, manifest, broken)
        with self.assertRaises(ValueError):
            activation._validate_provenance(activation.FSA, {**run, "fresh_live_run": False},
                                            manifest, acquisition)

    def test_unchanged_capture_preserves_first_manifest_timestamp(self):
        run, manifest, acquisition = self._provenance(activation.FSS)
        earlier = run["retrieved_at"] - timedelta(days=10)
        validated = activation._validate_provenance(
            activation.FSS, run, {**manifest, "retrieved_at": earlier}, acquisition)
        self.assertEqual(validated["retrieved_at"], run["retrieved_at"])
        with self.assertRaises(ValueError):
            activation._validate_provenance(activation.FSS, run,
                {**manifest, "retrieved_at": run["retrieved_at"] + timedelta(seconds=1)}, acquisition)
        with self.assertRaises(ValueError):
            activation._validate_provenance(activation.FSS, run,
                {**manifest, "retrieved_at": earlier, "source_artifact_sha256": "e" * 64}, acquisition)

    def test_source_gates_are_scoped_and_do_not_interpret_fsa_xy(self):
        sql = activation._CANDIDATES_SQL
        self.assertIn("candidate.source_id=%s", sql)
        self.assertIn("candidate.country_code='GB'", sql)
        self.assertIn("candidate.latitude IS NULL AND candidate.longitude IS NULL", sql)
        self.assertIn("candidate_private_location_evidence", sql)
        self.assertIn("state.state_code='restricted'", sql)
        self.assertIn("LEFT JOIN restricted_candidates restricted", sql)
        self.assertNotIn("coordinates", sql.casefold())
        self.assertNotIn("trading_name", sql.casefold())
        self.assertNotIn("location_evidence->>'x'", sql.casefold())
        self.assertNotIn("location_evidence->>'y'", sql.casefold())

    def test_candidate_query_bounds_latest_snapshot_and_materializes_existing_ids(self):
        sql = activation._CANDIDATES_SQL.casefold()
        self.assertIn("latest as materialized", sql)
        self.assertIn("accepted_source_records as materialized", sql)
        self.assertIn("existing_locationiq_jobs as materialized", sql)
        self.assertIn("existing_locationiq_targets as materialized", sql)
        self.assertIn("existing_other_results as materialized", sql)
        self.assertIn("join uec.geocode_results result on result.source_record_id=job.source_record_id", sql)
        self.assertIn("result.provider_id=job.provider_id and result.query=job.query", sql)
        self.assertNotIn("existing_other_targets", sql)
        self.assertNotIn("or existing_other_target", sql)
        self.assertEqual(sql.count("%s"), 8)
        self.assertEqual(sql.count(":%%')"), 2)
        self.assertIn("job.provider_id='locationiq'", sql)
        self.assertNotIn("select record.source_record_id from uec.source_records record", sql)
        self.assertIn("locationiq_target.candidate_id is null", sql)
        self.assertIn("record.source_record_key like ('real-preview:'||(select snapshot_sha256 from latest)||':%%')", sql)
        self.assertIn("limit %s for update of candidate skip locked", sql)
        self.assertIn("SET LOCAL statement_timeout = '30s'", SCRIPT.read_text(encoding="utf-8"))

    def test_fss_requires_actual_explicit_city_and_profiles_remain_source_specific(self):
        self.assertNotEqual(activation.PROFILE_IDS[activation.FSA], activation.PROFILE_IDS[activation.FSS])
        fss_evidence = {"country_code": "GB", "address_lines": ["12 Example Road"],
                        "postal_code": "IV3 8XY"}
        self.assertIsNone(activation.canonical_uk_query(
            fss_evidence["address_lines"], fss_evidence.get("city"), fss_evidence["postal_code"]))


if __name__ == "__main__":
    unittest.main()
