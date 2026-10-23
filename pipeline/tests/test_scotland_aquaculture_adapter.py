from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline.common.orchestrator import run_private_lifecycle
from pipeline.contracts.adapter_contract import SourceArtifact
from pipeline.sources.scotland_aquaculture import acquire
from pipeline.sources.scotland_aquaculture.adapter import (
    ADAPTER_VERSION, CATALOG_URL, SCHEMA_VERSION, SOURCE_ID, ScotlandAquacultureAdapter,
)
from pipeline.sources.scotland_aquaculture.refresh import ScotlandAquacultureRefreshAdapter


def feature(site_id: str, site_type: str, *, status: str = "A", lon: float = -4.2,
            lat: float = 56.1, species: str = "SAL", stage: str = "G") -> dict:
    return {
        "type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": {
            "siteno": site_id, "sitename": f"Synthetic {site_id}", "sitecatcd": "ECI",
            "sitestatcd": status, "sitetype": site_type, "mgtarea": "Synthetic area",
            "unitauth": "Synthetic locality", "regionname": "Synthetic region", "watertype": "M",
            "osgridref": "Synthetic grid ref", "easting": "200000", "northing": "700000",
            "scotaqurl": "https://example.invalid/site", "facilitytp": "Synthetic facility",
            "speciescd": species, "stagecode": stage,
        },
    }


def payload() -> bytes:
    name_conflict = feature("SYN-NAME-CONFLICT", "Fish")
    name_conflict_second = feature("SYN-NAME-CONFLICT", "Fish")
    name_conflict_second["properties"]["sitename"] = "Different synthetic name"
    geometry_conflict = feature("SYN-GEOM-CONFLICT", "Fish")
    geometry_conflict_second = feature("SYN-GEOM-CONFLICT", "Fish", lon=-4.1)
    projected_conflict = feature("SYN-PROJECTED-CONFLICT", "Shellfish")
    projected_conflict_second = feature("SYN-PROJECTED-CONFLICT", "Shellfish")
    projected_conflict_second["properties"]["easting"] = "200001"
    features = [
        feature("SYN-FISH", "Fish", species="SAL", stage="G"),
        feature("SYN-FISH", "Fish", species="TRO", stage="H"),
        feature("SYN-SHELL", "Shellfish", species="MED"),
        feature("SYN-RECREATION", "Fishery Site"),
        feature("SYN-CONFLICT", "Fish", status="A"),
        feature("SYN-CONFLICT", "Fish", status="D"),
        name_conflict, name_conflict_second,
        geometry_conflict, geometry_conflict_second,
        projected_conflict, projected_conflict_second,
    ]
    return json.dumps({"type": "FeatureCollection", "features": features,
                       "numberMatched": len(features), "numberReturned": len(features),
                       "totalFeatures": len(features), "timeStamp": "2026-10-20T12:00:00Z",
                       "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::4326"}}}).encode()


class ScotlandAquacultureAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.adapter = ScotlandAquacultureAdapter()

    def test_grouping_preserves_native_fields_and_coordinate_provenance(self):
        result = self.adapter.parse_bytes(payload())
        self.assertEqual(result["source_feature_rows"], 12)
        self.assertEqual(result["input_rows"], 7)
        self.assertEqual(result["normalized_rows"], 2)
        self.assertEqual(result["quarantined_rows"], 5)
        fish = next(row for row in result["accepted"] if row["normalized"]["establishment_id"] == "SYN-FISH")
        self.assertEqual(fish["normalized"]["source_status_code"], "A")
        self.assertEqual(fish["normalized"]["source_status"], "active")
        self.assertEqual(fish["normalized"]["source_species_codes"], ["SAL", "TRO"])
        self.assertEqual(fish["normalized"]["source_feature_count"], 2)
        self.assertEqual(fish["normalized"]["coordinates"], {
            "longitude": -4.2, "latitude": 56.1, "source_crs": "EPSG:4326",
            "precision": "source-reported-unknown",
            "location_semantics": "Scottish aquaculture registered site point; not operator correspondence address",
        })
        self.assertEqual(fish["normalized"]["source_projected_coordinates"]["crs"], "EPSG:27700")

    def test_fishery_and_conflicting_statuses_are_quarantined(self):
        result = self.adapter.parse_bytes(payload())
        reasons = [item["reasons"][0] for item in result["quarantined"]]
        self.assertCountEqual(reasons, ["out_of_animal_aquaculture_scope_fishery_site",
                                        "missing_or_conflicting_source_status", "conflicting_site_names",
                                        "conflicting_source_site_coordinates",
                                        "conflicting_source_projected_coordinates"])
        self.assertEqual(result["anomaly_counts"]["out_of_animal_aquaculture_scope_fishery_site"], 1)
        self.assertEqual(result["input_rows"], result["normalized_rows"] + result["quarantined_rows"])

    def test_schema_drift_and_invalid_geometry_fail_closed_or_quarantine(self):
        doc = json.loads(payload())
        del doc["features"][0]["properties"]["siteno"]
        with self.assertRaisesRegex(ValueError, "schema drift"):
            self.adapter.parse_bytes(json.dumps(doc).encode())
        doc = json.loads(payload())
        doc["numberReturned"] -= 1
        with self.assertRaisesRegex(ValueError, "incomplete WFS response"):
            self.adapter.parse_bytes(json.dumps(doc).encode())
        doc = json.loads(payload())
        doc["features"][0]["geometry"]["coordinates"] = [200.0, 56.1]
        result = self.adapter.parse_bytes(json.dumps(doc).encode())
        self.assertIn("invalid_or_out_of_extent_source_coordinates",
                      [item["reasons"][0] for item in result["quarantined"]])

    def test_native_status_codes_remain_distinct_and_do_not_become_verified_activity(self):
        doc = json.loads(payload())
        doc["features"] = [feature(f"SYN-STATUS-{status}", "Fish", status=status)
                            for status in ("A", "I", "D")]
        for key in ("numberMatched", "numberReturned", "totalFeatures"):
            doc[key] = len(doc["features"])
        result = self.adapter.parse_bytes(json.dumps(doc).encode())
        rows = {item["normalized"]["source_status_code"]: item["normalized"] for item in result["accepted"]}
        self.assertEqual({code: value["source_status"] for code, value in rows.items()},
                         {"A": "active", "I": "inactive", "D": "deregistered"})
        self.assertTrue(all("status" not in value for value in rows.values()))

    def test_shared_lifecycle_and_candidate_handoff_are_private(self):
        raw = payload()
        staging = Path(__file__).resolve().parents[2] / "data" / "staging" / "source-expansion-20261020" / "scotland" / "test-runs"
        staging.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=staging) as directory:
            root = Path(directory)
            raw_path = root / "synthetic.geojson"
            raw_path.write_bytes(raw)
            artifact = SourceArtifact(
                source_url=CATALOG_URL, retrieved_at_utc="2026-10-20T12:00:00Z",
                sha256=hashlib.sha256(raw).hexdigest(), byte_size=len(raw),
                code_version=ADAPTER_VERSION, config_version=SCHEMA_VERSION,
                rights_caveat="synthetic OGL v3 test data", coverage="synthetic-only",
            )
            result = run_private_lifecycle(raw_path, root / "runs", artifact, self.adapter)
            self.assertEqual(result["status"], "candidate-ready")
            run_root = Path(result["run_dir"])
            self.assertTrue((run_root / "source-health.json").exists())
            rows = [json.loads(line) for line in (run_root / "normalized" / "records.jsonl").read_text().splitlines()]
            handoff = self.adapter.write_candidate_handoff(run_root / "handoff", artifact, rows)
            self.assertEqual(handoff["normalized_rows"], 2)
            self.assertEqual(handoff["release_state"], "not-created")
            graph_root = run_root / "handoff" / "graph-candidates"
            self.assertTrue(graph_root.exists())
            graph_rows = [json.loads(line) for line in (graph_root / "records.jsonl").read_text().splitlines()]
            self.assertEqual(len(graph_rows), 2)
            self.assertTrue(all(row["facilities"] for row in graph_rows))
            self.assertTrue(all(row["name_assertions"] for row in graph_rows))
            self.assertTrue(all(row["location_role"] == "city_reference" for row in graph_rows))
            self.assertTrue(all(row["publication"]["publication_status"] == "not_eligible" for row in graph_rows))
            handed = [json.loads(line) for line in (run_root / "handoff" / "normalized" / "records.jsonl").read_text().splitlines()]
            fish = next(row for row in handed if row["normalized"]["establishment_id"] == "SYN-FISH")
            self.assertEqual(fish["normalized"]["facility_name"], "Synthetic SYN-FISH")
            self.assertEqual(fish["normalized"]["source_feature_count"], 2)
            self.assertEqual(len(fish["source_values"]["source_observations"]), 2)
            self.assertTrue(all("scotaqurl" in value for value in fish["source_values"]["source_observations"]))

    def test_shared_refresh_adapter_creates_only_private_candidate_handoff(self):
        raw = payload()
        staging = Path(__file__).resolve().parents[2] / "data" / "staging" / "source-expansion-20261020" / "scotland" / "test-runs"
        staging.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=staging) as directory:
            root = Path(directory)
            artifact_path = root / "synthetic.geojson"
            artifact_path.write_bytes(raw)
            result = ScotlandAquacultureRefreshAdapter().refresh(
                mode="private-preview", run_dir=root / "refresh", artifact=artifact_path,
                options={"acquisition": {"retrieved_at_utc": "2026-10-20T12:00:00Z",
                                         "sha256": hashlib.sha256(raw).hexdigest(),
                                         "byte_size": len(raw), "effective_date": "2026-10-20T12:00:00Z"}},
            )
            self.assertEqual(result["lifecycle_status"], "candidate-ready")
            self.assertTrue(result["candidate_handoff"])
            self.assertEqual(result["candidate_observation_rows"], 2)
            self.assertEqual(result["publication"], "not-created")
            self.assertEqual(result["source_canonical_url"], CATALOG_URL)

    def test_catalog_link_resolves_without_checking_token_into_code(self):
        from io import BytesIO

        class Response(BytesIO):
            status = 200
            headers = {"Content-Type": "text/html; charset=utf-8"}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                self.close()

        class Opener:
            def urlopen(self, _request, timeout):
                self.asserted_timeout = timeout
                html = ("<a href=\"https://msmap1.atkinsgeospatial.com/geoserver/nmpwfs/ows?"
                        "token=synthetic-token&amp;service=wfs&amp;request=getFeature&amp;"
                        "typeName=nmpwfs:aquaculture_sites&amp;outputFormat=CSV&amp;srsName=EPSG:27700\">x</a>")
                return Response(html.encode())

        url = acquire.discover_download_url(opener=Opener())
        self.assertIn("outputFormat=application%2Fjson", url)
        self.assertIn("srsName=EPSG%3A4326", url)
        self.assertIn("token=synthetic-token", url)
        self.assertNotIn("synthetic-token", acquire._redact_token(url))

    def test_platform_tls_context_is_verified_and_used_for_catalog_and_wfs(self):
        import ssl
        context = acquire._tls_context()
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)
        from io import BytesIO

        class Response(BytesIO):
            status = 200
            headers = {"Content-Type": "text/html; charset=utf-8"}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                self.close()

        response = Response(b'<a href="https://msmap1.atkinsgeospatial.com/geoserver/nmpwfs/ows?token=synth&amp;service=wfs&amp;request=getFeature&amp;typeName=nmpwfs:aquaculture_sites">x</a>')
        with patch("pipeline.sources.scotland_aquaculture.acquire.urllib.request.urlopen", return_value=response) as urlopen:
            acquire.discover_download_url()
        catalog_context = urlopen.call_args.kwargs["context"]
        self.assertIsInstance(catalog_context, type(context))
        self.assertEqual(catalog_context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(catalog_context.check_hostname)

        staging = Path(__file__).resolve().parents[2] / "data" / "staging" / "source-expansion-20261020" / "scotland" / "test-runs"
        staging.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=staging) as directory:
            root = Path(directory)
            review = root / "review.json"
            review.write_text(json.dumps({"source_id": SOURCE_ID, "decision": "approved", "license": "Open Government Licence v3.0", "private_preview_only": True}), encoding="utf-8")
            artifact = root / "synthetic.geojson"
            artifact.write_text(json.dumps({"type": "FeatureCollection", "numberMatched": 0, "numberReturned": 0,
                                            "totalFeatures": 0, "timeStamp": "2026-10-20T00:00:00Z", "features": []}), encoding="utf-8")
            with patch.object(acquire, "discover_download_url", return_value="https://msmap1.atkinsgeospatial.com/geoserver/nmpwfs/ows?token=synth"), \
                    patch.object(acquire, "fetch_source", return_value={"artifact_path": str(artifact), "retrieved_at_utc": "2026-10-20T00:00:00Z"}) as fetch_source:
                acquire.fetch(output_root=root / "out", run_id="tls-context-test", terms_review_path=review)
            self.assertEqual(fetch_source.call_args.kwargs["ssl_context"].verify_mode, ssl.CERT_REQUIRED)
            self.assertTrue(fetch_source.call_args.kwargs["ssl_context"].check_hostname)

    def test_fetch_requires_source_scoped_operator_terms_review(self):
        staging = Path(__file__).resolve().parents[2] / "data" / "staging" / "source-expansion-20261020" / "scotland" / "test-runs"
        staging.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=staging) as directory:
            review = Path(directory) / "review.json"
            review.write_text(json.dumps({"source_id": "some.other.source", "decision": "approved",
                                          "license": "Open Government Licence v3.0",
                                          "private_preview_only": True}), encoding="utf-8")
            with self.assertRaisesRegex(acquire.ScotlandAcquisitionError, "exact OGL source"):
                acquire.fetch(output_root=Path(directory), run_id="test", terms_review_path=review)

    def test_invalid_wfs_envelope_uses_acquisition_failure_path(self):
        # This validator is called against the shared primitive's private
        # temporary download. It must raise its typed failure, not allow a
        # parse error to bypass cleanup/failure evidence handling.
        from pipeline.common.acquisition import AcquisitionError
        staging = Path(__file__).resolve().parents[2] / "data" / "staging" / "source-expansion-20261020" / "scotland" / "test-runs"
        staging.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=staging) as directory:
            artifact = Path(directory) / "invalid.geojson"
            artifact.write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")
            with self.assertRaises(AcquisitionError) as caught:
                acquire._artifact_validator(artifact, {})
            self.assertEqual(caught.exception.failure_class, "source-validation")


if __name__ == "__main__":
    unittest.main()
