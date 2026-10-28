"""Synthetic EEA acquisition, field retention, taxonomy and private-import contracts."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from urllib.parse import parse_qs, urlsplit

from pipeline.common.refresh_runner import RefreshCatalog
from pipeline.contracts.adapter_contract import SourceArtifact
from pipeline.sources.eea.acquire import METADATA_URL, SameHostRedirect, fetch
from pipeline.sources.eea.adapter import (ADAPTER_VERSION, REQUIRED_FIELDS, SCHEMA_VERSION, SOURCE_ID,
                                           SOURCE_URL, EeaLivestockAdapter)
from pipeline.sources.eea.validation import validate_acquisition
from pipeline.taxonomy_crosswalk import project_observation


def feature(identifier=1):
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [10.2, 52.3]},
            "properties": {"OBJECTID": identifier, "InspireSiteId": f"SYNTHETIC-SITE-{identifier}",
                           "siteName": f"Synthetic animal site {identifier}", "countryCode": "DE",
                           "Site_reporting_year": 2024, "eea_activities": "Livestock",
                           "activity_details": "Synthetic native livestock activity", "eprtr_AnnexIActivity": "7(a)(i)",
                           "nFacilities": 1, "nInstallations": 2, "permit_years": "2020", "x_4258": 10.2, "y_4258": 52.3}}


def collection(features):
    return {"type": "FeatureCollection", "features": features}


class Response(io.BytesIO):
    status = 200

    def __init__(self, url, raw, content_type="application/json"):
        super().__init__(raw)
        self.url = url
        self.headers = {"Content-Type": content_type}

    def geturl(self):
        return self.url


class Opener:
    def __init__(self, fault=None):
        self.fault = fault
        self.id_calls = 0

    def open(self, request, timeout):
        url = request.full_url
        if url == METADATA_URL:
            raw = b'<metadata><licence>https://creativecommons.org/licenses/by/4.0/</licence></metadata>'
            return Response(url, raw, "application/xml")
        query = parse_qs(urlsplit(url).query)
        if urlsplit(url).path.endswith("/0"):
            value = {"name": "ied_SiteMap", "type": "Feature Layer", "geometryType": "esriGeometryPoint",
                     "maxRecordCount": 1000, "spatialReference": {"latestWkid": 3857},
                     "fields": [{"name": f} for f in REQUIRED_FIELDS]}
            if self.fault == "crs":
                value["spatialReference"] = {"wkid": 4326}
        elif "returnCountOnly" in query:
            value = {"count": 3}
        elif "returnIdsOnly" in query:
            self.id_calls += 1
            value = {"objectIds": [1, 2, 3]}
            if self.fault == "ids":
                value = {"objectIds": [1, 1, 3]}
            if self.fault == "membership" and self.id_calls > 1:
                value = {"objectIds": [1, 2, 4]}
        else:
            self_outer = query["outSR"][0]
            if self_outer != "4326" or "eea_activities='Livestock'" not in query["where"][0]:
                raise AssertionError("acquisition lost explicit coordinate or activity scope")
            features = [feature(int(x)) for x in query["objectIds"][0].split(",")]
            value = collection(features if self.fault != "page" else features[:0])
        return Response(url, json.dumps(value).encode())


class EeaContracts(unittest.TestCase):
    def parse(self, features):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "input.geojson"
            path.write_text(json.dumps(collection(features)), encoding="utf-8")
            return EeaLivestockAdapter().parse(path)

    def test_fields_identity_and_source_counts_are_preserved(self):
        row = self.parse([feature()])["accepted"][0]
        self.assertEqual(row["normalized"]["establishment_id"], "DE:SYNTHETIC-SITE-1")
        self.assertEqual(row["source_record_key"], "site:DE:SYNTHETIC-SITE-1:2024")
        self.assertEqual(row["source_values"]["nInstallations"], 2)
        self.assertEqual(row["source_values"]["permit_years"], "2020")
        self.assertEqual(row["source_values"]["x_4258"], 10.2)
        self.assertEqual(row["normalized"]["coordinate_precision"], "source-precision-unknown")
        self.assertEqual(row["normalized"]["privacy_gate"], "pending-review")

    def test_other_industry_mixed_activity_wrong_year_and_duplicates_are_not_imported(self):
        for field, value in (("eea_activities", "Livestock,Landfill"), ("eea_activities", "Mining"),
                             ("Site_reporting_year", 2023), ("siteName", ""), ("InspireSiteId", None)):
            with self.subTest(field=field, value=value):
                item = feature()
                item["properties"][field] = value
                result = self.parse([item])
                self.assertEqual(len(result["accepted"]), 0)
                self.assertEqual(len(result["quarantined"]), 1)
        result = self.parse([feature(), feature()])
        self.assertEqual(len(result["accepted"]), 1)
        self.assertEqual(len(result["quarantined"]), 1)

    def test_bad_point_remains_retained_but_unmapped(self):
        for pair in ([0, 0], [52.3, 10.2], [float("nan"), 52.3], [True, 52.3], [10.2, None]):
            with self.subTest(pair=pair):
                item = feature()
                item["geometry"]["coordinates"] = pair
                row = self.parse([item])["accepted"][0]
                self.assertEqual(row["normalized"]["coordinates"], {})
                self.assertEqual(row["normalized"]["coordinate_state"], "source-point-unusable")
                self.assertIn("source_geometry_wgs84", row["source_values"])

    def test_country_is_part_of_identity(self):
        item = feature()
        other = copy.deepcopy(item)
        other["properties"]["countryCode"] = "PL"
        other["geometry"]["coordinates"] = [20.5, 52.3]
        self.assertEqual(len(self.parse([item, other])["accepted"]), 2)

    def test_schema_drift_is_explicit_failure(self):
        item = feature()
        del item["properties"]["countryCode"]
        with self.assertRaisesRegex(ValueError, "schema changed"):
            self.parse([item])

    def test_lifecycle_provenance_and_rerun_are_deterministic(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            raw = json.dumps(collection([feature()])).encode()
            path = root / "source.geojson"
            path.write_bytes(raw)
            artifact = SourceArtifact(SOURCE_URL, "2026-10-28T12:00:00Z", hashlib.sha256(raw).hexdigest(), len(raw),
                                      code_version=ADAPTER_VERSION, config_version=SCHEMA_VERSION)
            adapter = EeaLivestockAdapter()
            first = adapter.run(path, root / "one", artifact)
            second = adapter.run(path, root / "two", artifact)
            self.assertEqual(first["normalized_sha256"], second["normalized_sha256"])
            self.assertEqual(first["release_state"], "not-created")
            path.write_bytes(raw + b" ")
            with self.assertRaisesRegex(ValueError, "provenance mismatch"):
                adapter.run(path, root / "three", artifact)

    def test_live_catalog_registration_and_taxonomy(self):
        registered = RefreshCatalog().adapters[SOURCE_ID]
        self.assertTrue(registered.capabilities.live_callable)
        row = self.parse([feature()])["accepted"][0]
        projection = project_observation(row)
        self.assertEqual(projection["taxonomy_display_category"], "animal_keeping_and_production")

    def fetch(self, root, opener):
        review = Path(__file__).parents[1] / "sources/eea/terms-review.json"
        return fetch(output_root=root, run_id="synthetic", terms_review_path=review, page_size=2, opener=opener)

    def test_id_paging_reconciles_and_import_revalidates_immutable_artifacts(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            facts = self.fetch(root / "acquisition", Opener())
            self.assertEqual((facts["feature_count"], facts["page_count"]), (3, 2))
            adapter = EeaLivestockAdapter()
            rows = adapter.parse(facts["artifact_path"])["accepted"]
            artifact = SourceArtifact(SOURCE_URL, facts["retrieved_at_utc"], facts["artifact_sha256"], facts["artifact_byte_size"])
            manifest = adapter.write_candidate_handoff(root / "handoff", artifact, rows)
            summary = {"input_rows": 3, "normalized_rows": 3, "quarantined_rows": 0,
                       "candidate_handoff_sha256": manifest["normalized_sha256"]}
            self.assertEqual(validate_acquisition(root, "synthetic", manifest, summary, 30)["feature_count"], 3)
            page = Path(facts["artifact_path"]) / "page-0001.geojson"
            page.write_bytes(page.read_bytes() + b" ")
            with self.assertRaises(ValueError):
                validate_acquisition(root, "synthetic", manifest, summary, 30)

    def test_count_ids_pages_native_crs_and_mid_fetch_membership_fail_closed(self):
        for fault in ("ids", "page", "crs", "membership"):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as d:
                with self.assertRaises(ValueError):
                    self.fetch(Path(d), Opener(fault))

    def test_redirects_cannot_downgrade_https_or_escape_the_publisher(self):
        from urllib.request import Request
        req = Request(SOURCE_URL)
        for url in (SOURCE_URL.replace("https:", "http:"), "https://other.example.invalid/data"):
            with self.assertRaises(ValueError):
                SameHostRedirect().redirect_request(req, None, 302, "redirect", {}, url)

    def test_private_import_projection_keeps_native_name_without_public_approval(self):
        spec = importlib.util.spec_from_file_location("eea_import_test", Path(__file__).parents[1] / "scripts/maintenance/import-real-preview.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        row = self.parse([feature()])["accepted"][0]
        result = module.parse_row(SOURCE_ID, row)
        self.assertIn("Synthetic animal site 1", result)
        self.assertEqual(row["normalized"]["publication_gate"], "blocked")

    def test_release_bridge_accepts_eea_paged_artifact_and_multicountry_publisher_only(self):
        spec = importlib.util.spec_from_file_location("eea_bridge_test", Path(__file__).parents[1] / "scripts/maintenance/bridge-v0-candidates.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module._publisher_country(SOURCE_ID, {"DE", "PL"}), "EU")
        with self.assertRaises(module.BridgeError):
            module._publisher_country("de.locations", {"DE", "PL"})
        with self.assertRaises(module.BridgeError):
            module._publisher_country(SOURCE_ID, {"DE", "US"})
        row = self.parse([feature()])["accepted"][0]
        self.assertEqual(module._facility_display_name(SOURCE_ID, row["normalized"]), "Synthetic animal site 1")
        safe = module._safe_normalized(row["normalized"], SOURCE_ID, row["source_values"])
        self.assertEqual(safe["source_reporting_year"], 2024)
        self.assertEqual(safe["source_installation_count"], 2)
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            facts = self.fetch(root / "acquisition", Opener())
            self.assertEqual(module._retained_source_artifact_digest(SOURCE_ID, Path(facts["artifact_path"])),
                             (facts["artifact_sha256"], facts["artifact_byte_size"]))
            adapter = EeaLivestockAdapter()
            rows = adapter.parse(facts["artifact_path"])["accepted"]
            artifact = SourceArtifact(SOURCE_URL, facts["retrieved_at_utc"], facts["artifact_sha256"], facts["artifact_byte_size"],
                                      code_version=ADAPTER_VERSION, config_version=SCHEMA_VERSION)
            manifest = adapter.write_candidate_handoff(root / "handoff", artifact, rows)
            snapshot = {"source_artifact_sha256": facts["artifact_sha256"], "normalized_sha256": manifest["normalized_sha256"],
                        "retrieved_at": facts["retrieved_at_utc"], "first_manifest_retrieved_at": facts["retrieved_at_utc"],
                        "handoff_code_version": ADAPTER_VERSION, "handoff_config_version": SCHEMA_VERSION,
                        "source_host": urlsplit(SOURCE_URL).hostname}
            inventory = {"snapshot": snapshot, "counts": {"imported_observation_count": 3}}
            entry = {"source_id": SOURCE_ID, "handoff_manifest_path": str((root / "handoff/manifest.json").resolve())}
            verified = module.verify_handoff(entry, inventory)
            self.assertEqual(len(verified["rows"]), 3)
            self.assertEqual(verified["graph_handoff_state"], "not_applicable_site_identity_only")

    def test_e2e_target_never_accepts_frozen_remote_or_wrong_databases(self):
        from pipeline.sources.eea.verify import validate_target
        validate_target("postgresql://127.0.0.1/uec_launch_sources_test_20261025")
        for url in ("postgresql://remote/uec_launch_sources_test_20261025", "postgresql://127.0.0.1/uec_country_release_test_20261027",
                    "postgresql://127.0.0.1/uec_launch_sources_test_20261025?host=remote"):
            with self.assertRaises(ValueError):
                validate_target(url)

    def test_overlap_is_geographic_country_scoped_and_does_not_merge_shared_names(self):
        from pipeline.sources.eea.overlap import screen
        result = screen([("DE", "Synthetic Farm", 52.3, 10.2), ("DE", "Synthetic Farm", 53.3, 10.2),
                         ("PL", "Other Farm", 52.3, 20.2)], [("DE", "Synthetic Farm", 52.3001, 10.2)])
        self.assertEqual(result["shared_normalized_name_in_same_country"], 2)
        self.assertEqual(result["near_existing_point"], 1)
        self.assertEqual(result["shared_name_and_near_existing_point"], 1)
        self.assertEqual(result["countries_absent_from_comparison_release"], ["PL"])
        self.assertEqual(result["automatic_merges"], 0)


if __name__ == "__main__":
    unittest.main()
