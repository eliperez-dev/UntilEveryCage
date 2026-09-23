from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from pipeline.contracts.adapter_contract import SourceArtifact
from .sa_epa import ADAPTER_VERSION, SCHEMA_VERSION, SOURCE_URL, SaEpaLicensedActivitiesAdapter

ROOT = Path(__file__).parent
FIXTURE = ROOT / "fixtures" / "sa_epa_activities.geojson"


class SaEpaAdapterTests(unittest.TestCase):
    def setUp(self):
        self.adapter = SaEpaLicensedActivitiesAdapter()

    def test_aggregates_licences_and_preserves_child_activity_observations(self):
        parsed = self.adapter.parse_bytes(FIXTURE.read_bytes())
        self.assertEqual(parsed["licence_count"], 2)
        self.assertEqual(parsed["activity_observation_count"], 3)
        first = next(row for row in parsed["licences"] if row["source_record_key"] == "SYN-LIC-01")
        self.assertEqual(len(first["normalized"]["activity_observations"]), 2)
        self.assertEqual(first["normalized"]["coordinate_state"], "approximate-source-point")
        self.assertEqual(first["normalized"]["coordinate_precision"], "coarse-approximate-0.01-degree")
        self.assertEqual(first["normalized"]["publication_gate"], "blocked")

    def test_missing_ids_bad_points_and_schema_drift_are_explicit(self):
        payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        payload["features"][0]["properties"]["EPALICENCE"] = ""
        payload["features"][1]["geometry"]["coordinates"] = [0, 0]
        parsed = self.adapter.parse_bytes(json.dumps(payload).encode())
        self.assertEqual(len(parsed["quarantined"]), 2)
        self.assertIn("missing_licence_id", parsed["quarantined"][0]["reasons"])
        self.assertIn("unresolved_coordinate", parsed["quarantined"][1]["reasons"])
        with self.assertRaisesRegex(ValueError, "schema drift"):
            self.adapter.parse_bytes(b'{"type":"FeatureCollection","features":[{"properties":{},"geometry":{}}]}')

    def test_conflicting_points_for_a_licence_are_not_silently_selected(self):
        payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        payload["features"][1]["geometry"]["coordinates"] = [138.7, -34.9]
        parsed = self.adapter.parse_bytes(json.dumps(payload).encode())
        parent = next(row for row in parsed["licences"] if row["source_record_key"] == "SYN-LIC-01")
        self.assertIsNone(parent["normalized"]["coordinates"])
        self.assertEqual(parent["normalized"]["coordinate_state"], "ambiguous-within-licence")
        self.assertEqual(len(parent["normalized"]["activity_observations"]), 2)
        self.assertNotEqual(parent["normalized"]["activity_observations"][0]["coordinates"],
                            parent["normalized"]["activity_observations"][1]["coordinates"])

    def test_run_verifies_artifact_and_emits_private_manifest_without_release(self):
        raw = FIXTURE.read_bytes()
        artifact = SourceArtifact(source_url=self.adapter.source_url, retrieved_at_utc="2026-09-16T07:15:42Z",
            sha256=hashlib.sha256(raw).hexdigest(), byte_size=len(raw), publication_date=None,
            effective_date="2026-03-18", code_version=ADAPTER_VERSION, config_version=SCHEMA_VERSION,
            rights_caveat="Synthetic test artifact; source terms unresolved", privacy_caveat="Private; review required")
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            manifest = self.adapter.run(FIXTURE, Path(directory), artifact)
            self.assertEqual(manifest["source_licence_count"], 2)
            self.assertEqual(manifest["source_activity_observations"], 3)
            self.assertEqual(manifest["terms_state"], "unresolved")
            self.assertEqual(manifest["publication_state"], "private-candidate")
            self.assertEqual(manifest["publication_eligibility"], "blocked")
            self.assertFalse((Path(directory) / "released" / "records.jsonl").exists())
            self.assertTrue((Path(directory) / "manifest.json").exists())
            bad = SourceArtifact(source_url=self.adapter.source_url, retrieved_at_utc="2026-09-16T07:15:42Z", sha256="0"*64, byte_size=len(raw))
            with self.assertRaisesRegex(ValueError, "provenance mismatch"):
                self.adapter.run(FIXTURE, Path(directory) / "bad", bad)

    def test_shared_catalog_registers_source_and_live_mode_is_blocked(self):
        from pipeline.common.refresh_runner import RefreshCatalog, RefreshRunner
        from pipeline.contracts.refresh import RefreshRequest

        catalog = RefreshCatalog()
        self.assertIn(self.adapter.source_id, catalog.adapters)
        capability = catalog.capabilities[self.adapter.source_id]
        self.assertFalse(capability.live_callable)
        self.assertEqual(capability.operational_classification, "assisted")
        with tempfile.TemporaryDirectory(dir=Path.cwd() / "pipeline") as directory:
            result = RefreshRunner(catalog).run(RefreshRequest(
                source_ids=(self.adapter.source_id,), mode="live-acquisition", output_root=Path(directory)))
        source = result["results"][0]
        self.assertIn(source["status"], {"blocked", "failed"})
        self.assertNotEqual(source.get("acquisition_classification"), "live")

    def test_shared_runner_fixture_and_local_artifact_paths_stay_private(self):
        from pipeline.common.refresh_runner import RefreshCatalog, RefreshRunner
        from pipeline.contracts.refresh import RefreshRequest

        with tempfile.TemporaryDirectory(dir=Path.cwd() / "pipeline") as directory:
            root = Path(directory)
            catalog = RefreshCatalog()
            fixture = RefreshRunner(catalog).run(RefreshRequest(
                source_ids=(self.adapter.source_id,), mode="fixture", output_root=root / "fixture"))
            summary = fixture["results"][0]["summary"]
            self.assertEqual(summary["input_rows"], 3)
            self.assertEqual(summary["normalized_rows"], 3)
            self.assertFalse(fixture["results"][0]["publication"]["published"])

            local = RefreshRunner(catalog).run(RefreshRequest(
                source_ids=(self.adapter.source_id,), mode="local-artifact",
                artifact_paths={self.adapter.source_id: str(FIXTURE)}, output_root=root / "local",
                options={"artifact_metadata": {"source_url": SOURCE_URL,
                    "retrieved_at_utc": "2026-09-16T00:00:00Z", "sha256": hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
                    "byte_size": FIXTURE.stat().st_size, "effective_date": "2026-03-18"}}))
            self.assertEqual(local["results"][0]["status"], "succeeded")
            self.assertEqual(local["results"][0]["summary"]["normalized_rows"], 3)

            missing = RefreshRunner(catalog).run(RefreshRequest(
                source_ids=(self.adapter.source_id,), mode="local-artifact",
                artifact_paths={self.adapter.source_id: str(FIXTURE)}, output_root=root / "missing-metadata"))
            self.assertEqual(missing["results"][0]["status"], "failed")

            malformed = root / "bad.geojson"
            malformed.write_text('{"type":"FeatureCollection","features":[{"properties":{}}]}', encoding="utf-8")
            raw = malformed.read_bytes()
            failed = RefreshRunner(catalog).run(RefreshRequest(
                source_ids=(self.adapter.source_id,), mode="local-artifact",
                artifact_paths={self.adapter.source_id: str(malformed)}, output_root=root / "failed",
                options={"artifact_metadata": {"source_url": SOURCE_URL,
                    "retrieved_at_utc": "2026-09-16T00:00:00Z", "sha256": hashlib.sha256(raw).hexdigest(),
                    "byte_size": len(raw), "effective_date": "2026-03-18"},
                    "previous_valid_states": {self.adapter.source_id: {"verified": True, "artifact_sha256": "a" * 64}}}))
            failed_source = failed["results"][0]
            self.assertEqual(failed_source["status"], "failed")
            self.assertTrue(failed_source["operational"]["previous_valid_state"]["verified"])


if __name__ == "__main__":
    unittest.main()
