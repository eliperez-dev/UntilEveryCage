"""Synthetic contracts for Norway aquaculture acquisition and private refresh."""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from pipeline.common.refresh_runner import RefreshCatalog, RefreshRunner
from pipeline.contracts.refresh import AdapterCapabilities, RefreshRequest
from pipeline.sources.norway.acquire import fetch
from pipeline.sources.norway.aquaculture import (
    ADAPTER_VERSION, LICENSE, LICENSE_VERSION, SCHEMA_VERSION, SOURCE_ID,
    NorwayAquacultureAdapter, bundle_digest,
)
from pipeline.sources.norway.refresh import NorwayAquacultureRefreshAdapter

TEST_TEMP_ROOT = Path(__file__).resolve().parents[2] / "data" / "staging" / "source-expansion-20261020" / "norway" / "test-temp"


def temporary_directory():
    TEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)
    return tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT)


def feature(object_id: int, locality_id: int, *, species: str = "Salmon", symbol: str = "Matfisk",
            coordinates: tuple[float, float] = (8.0, 61.0)) -> dict:
    return {"type": "Feature", "properties": {
        "objectid": object_id, "loknr": locality_id, "til_arter": species,
        "symbol": symbol, "status_lokalitet": "Active", "kommune": "Example",
        "fylke": "Example region", "navn": f"Synthetic locality {locality_id}",
        "til_innehavere": "synthetic holder",
        "kapasitet_lok": 100, "tempcapacity": 80, "kapasitet_unittype": "TONN",
        "til_produksjonsform": "Synthetic production", "til_formaal": "Synthetic purpose", "vannmiljo": "Sea",
    }, "geometry": {"type": "Point", "coordinates": list(coordinates)}}


def collection(features: list[dict]) -> bytes:
    return json.dumps({"type": "FeatureCollection", "features": features}).encode()


class NorwayAquacultureParserTests(unittest.TestCase):
    def test_animals_are_normalized_and_algal_only_is_quarantined(self):
        with temporary_directory() as temporary:
            path = Path(temporary) / "source.geojson"
            path.write_bytes(collection([feature(1, 10), feature(2, 20, species="Alger", symbol="Alger")]))
            parsed = NorwayAquacultureAdapter().parse(path)
        self.assertEqual(parsed["input_rows"], 2)
        self.assertEqual(len(parsed["accepted"]), 1)
        self.assertEqual(parsed["accepted"][0]["normalized"]["country_code"], "NO")
        self.assertEqual(parsed["accepted"][0]["normalized"]["facility_name"], "Synthetic locality 10")
        self.assertEqual(parsed["accepted"][0]["normalized"]["source_locality_name"], "Synthetic locality 10")
        self.assertEqual(parsed["accepted"][0]["source_values"]["navn"], "Synthetic locality 10")
        self.assertEqual(parsed["accepted"][0]["normalized"]["coordinates"]["source_crs"], "EPSG:4326")
        self.assertIn("not permit-holder mailing address", parsed["accepted"][0]["normalized"]["coordinates"]["location_semantics"])
        self.assertEqual(parsed["quarantined"][0]["reasons"], ["out_of_animal_aquaculture_scope"])
        self.assertNotIn("til_innehavere", json.dumps(parsed["accepted"]))
        normalized = parsed["accepted"][0]["normalized"]
        self.assertEqual(normalized["source_capacity"], {"approved": 100, "current": 80, "unit": "TONN"})
        self.assertEqual(normalized["source_species_scope"], "Salmon")
        self.assertEqual(normalized["source_production_form"], "Synthetic production")

    def test_release_projection_preserves_names_species_capacity_and_crosswalk(self):
        from pipeline.taxonomy_crosswalk import crosswalk_document, project_observation
        with temporary_directory() as temporary:
            root = Path(temporary)
            path = root / "source.geojson"
            path.write_bytes(collection([feature(1, 10)]))
            row = NorwayAquacultureAdapter().parse(path)["accepted"][0]
            spec = importlib.util.spec_from_file_location("norway_bridge_test", Path(__file__).parents[1] / "scripts/maintenance/bridge-v0-candidates.py")
            bridge = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(bridge)
            safe = bridge._safe_normalized(row["normalized"], SOURCE_ID, row["source_values"])
            self.assertEqual(safe["facility_display_name"], "Synthetic locality 10")
            for key in ("source_species_scope", "source_locality_status", "source_capacity", "source_production_form"):
                self.assertEqual(safe[key], row["normalized"][key])
            self.assertEqual(project_observation(row)["taxonomy_display_category"], "animal_keeping_and_production")
            self.assertTrue(crosswalk_document(SOURCE_ID)["rules"])

    def test_blank_species_and_projected_crs_never_become_map_points(self):
        with temporary_directory() as temporary:
            path = Path(temporary) / "source.geojson"
            path.write_bytes(collection([feature(1, 10, species=""), feature(2, 20, coordinates=(500000, 6800000))]))
            parsed = NorwayAquacultureAdapter().parse(path)
        self.assertEqual(len(parsed["accepted"]), 0)
        self.assertEqual(len(parsed["quarantined"]), 2)

    def test_duplicate_locality_and_out_of_envelope_point_are_quarantined(self):
        with temporary_directory() as temporary:
            path = Path(temporary) / "source.geojson"
            path.write_bytes(collection([feature(1, 10), feature(2, 10), feature(3, 30, coordinates=(0.0, 0.0))]))
            parsed = NorwayAquacultureAdapter().parse(path)
        self.assertEqual(len(parsed["accepted"]), 1)
        self.assertEqual({tuple(item["reasons"]) for item in parsed["quarantined"]},
                         {("duplicate_locality_identifier",), ("coordinates_outside_norway_envelope",)})

    def test_page_bundle_hash_and_parser_include_all_pages(self):
        with temporary_directory() as temporary:
            root = Path(temporary)
            (root / "page-0001.geojson").write_bytes(collection([feature(1, 10)]))
            (root / "page-0002.geojson").write_bytes(collection([feature(2, 20)]))
            digest, size = bundle_digest(root)
            parsed = NorwayAquacultureAdapter().parse(root)
        self.assertEqual(len(digest), 64)
        self.assertGreater(size, 0)
        self.assertEqual(parsed["input_rows"], 2)
        self.assertEqual(len(parsed["accepted"]), 2)


class _Response:
    def __init__(self, url: str, body: bytes, content_type: str) -> None:
        self._url = url
        self._body = io.BytesIO(body)
        self.status = 200
        self.headers = {"Content-Type": content_type}

    def __enter__(self): return self
    def __exit__(self, *_): self._body.close()
    def read(self, size=-1): return self._body.read(size)
    def geturl(self): return self._url


class _PagedOpener:
    def __init__(self):
        self.layer = {"name": "Lokaliteter", "type": "Feature Layer", "geometryType": "esriGeometryPoint",
                      "maxRecordCount": 2000, "spatialReference": {"wkid": 25833},
                      "fields": [{"name": key} for key in ("objectid", "loknr", "til_arter", "symbol", "status_lokalitet", "kommune", "fylke", "navn")]}

    def urlopen(self, request, timeout=60):
        url = request.full_url
        query = parse_qs(urlparse(url).query)
        if urlparse(url).path.endswith("/0"):
            body, content_type = json.dumps(self.layer).encode(), "text/plain"
        elif query.get("returnCountOnly") == ["true"]:
            body, content_type = b'{"count":3}', "application/json"
        elif query.get("returnIdsOnly") == ["true"]:
            body, content_type = b'{"objectIds":[1,2,3]}', "application/json"
        else:
            ids = [int(item) for item in query["objectIds"][0].split(",")]
            features = [feature(identifier, identifier * 10) for identifier in ids]
            body, content_type = collection(features), "application/geo+json"
        return _Response(url, body, content_type)


class NorwayAquacultureAcquisitionTests(unittest.TestCase):
    def test_central_catalog_registers_the_source_and_live_capability(self):
        catalog = RefreshCatalog()
        registered = catalog.adapters[SOURCE_ID]
        self.assertIsInstance(registered.adapter, NorwayAquacultureRefreshAdapter)
        self.assertTrue(registered.capabilities.live_callable)
        self.assertEqual(registered.capabilities.source_kind, "facility_master")

    def test_bounded_paging_reconciles_full_ids_count_and_all_geometry(self):
        with temporary_directory() as temporary:
            root = Path(temporary)
            review = root / "terms.json"
            review.write_text(json.dumps({"source_id": SOURCE_ID, "decision": "approved", "license": LICENSE,
                                         "license_version": LICENSE_VERSION, "private_preview_only": True}), encoding="utf-8")
            metadata = fetch(output_root=root / "raw", run_id="synthetic", terms_review_path=review,
                             page_size=2, opener=_PagedOpener())
            pages = Path(metadata["artifact_path"])
            digest, size = bundle_digest(pages)
        self.assertEqual(metadata["feature_count"], 3)
        self.assertEqual(metadata["retrieved_unique_object_id_count"], 3)
        self.assertEqual(metadata["page_count"], 2)
        self.assertEqual(metadata["coordinates_checked"], 3)
        self.assertEqual(metadata["coordinate_bounds_validation"].split(";", 1)[0], "passed for every retrieved feature")
        self.assertEqual(metadata["artifact_sha256"], digest)
        self.assertEqual(metadata["artifact_byte_size"], size)

    def test_release_bridge_accepts_paged_artifact_and_rejects_wrong_site_identity(self):
        from pipeline.contracts.adapter_contract import SourceArtifact
        from pipeline.contracts.candidate_handoff import write_handoff
        from datetime import datetime, timezone
        spec = importlib.util.spec_from_file_location("norway_bridge_identity_test", Path(__file__).parents[1] / "scripts/maintenance/bridge-v0-candidates.py")
        bridge = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(bridge)
        with temporary_directory() as temporary:
            root = Path(temporary)
            review = root / "terms.json"
            review.write_text(json.dumps({"source_id": SOURCE_ID, "decision": "approved", "license": LICENSE,
                                         "license_version": LICENSE_VERSION, "private_preview_only": True}), encoding="utf-8")
            facts = fetch(output_root=root / "raw", run_id="synthetic", terms_review_path=review, opener=_PagedOpener())
            self.assertEqual(bridge._retained_source_artifact_digest(SOURCE_ID, Path(facts["artifact_path"])),
                             (facts["artifact_sha256"], facts["artifact_byte_size"]))
            rows = NorwayAquacultureAdapter().parse(facts["artifact_path"])["accepted"]
            artifact = SourceArtifact(facts["canonical_url"], datetime.now(timezone.utc).isoformat(),
                                      facts["artifact_sha256"], facts["artifact_byte_size"],
                                      code_version=ADAPTER_VERSION, config_version=SCHEMA_VERSION)
            for wrong_identity in (False, True):
                if wrong_identity:
                    rows[0]["normalized"]["country_code"] = "SE"
                manifest = write_handoff(root / "handoff", rows, artifact, source_id=SOURCE_ID, emit_graph_candidates=False)
                inventory = {"snapshot": {"source_artifact_sha256": manifest["checksum_sha256"],
                    "normalized_sha256": manifest["normalized_sha256"], "retrieved_at": manifest["retrieved_at_utc"],
                    "handoff_code_version": ADAPTER_VERSION, "handoff_config_version": SCHEMA_VERSION,
                    "source_host": urlparse(facts["canonical_url"]).hostname}, "counts": {"imported_observation_count": 3}}
                entry = {"source_id": SOURCE_ID, "handoff_manifest_path": str((root / "handoff/manifest.json").resolve())}
                if wrong_identity:
                    with self.assertRaisesRegex(bridge.BridgeError, "norway_locality_identity_or_scope_invalid"):
                        bridge.verify_handoff(entry, inventory)
                else:
                    result = bridge.verify_handoff(entry, inventory)
                    self.assertEqual(len(result["groups"]), 3)
                    self.assertEqual(result["graph_handoff_state"], "not_applicable_locality_identity_only")

    def test_shared_refresh_runner_writes_private_candidate_handoff(self):
        with temporary_directory() as temporary:
            root = Path(temporary)
            raw = root / "source.geojson"
            raw.write_bytes(collection([feature(1, 10)]))
            raw_bytes = raw.read_bytes()
            acquisition = {"canonical_url": "https://gis.fiskeridir.no/test", "retrieved_at_utc": "2026-10-20T00:00:00Z",
                           "artifact_sha256": hashlib.sha256(raw_bytes).hexdigest(), "artifact_byte_size": len(raw_bytes)}
            catalog = RefreshCatalog()
            catalog.register(NorwayAquacultureRefreshAdapter(), AdapterCapabilities(
                source_id=SOURCE_ID, adapter_version=ADAPTER_VERSION, schema_version=SCHEMA_VERSION,
                acquisition="bounded_private_fetch", geocoding="disabled", publication="human_gate_required",
                country_code="NO", operational_classification="live", live_callable=True))
            result = RefreshRunner(catalog).run(RefreshRequest(
                source_ids=(SOURCE_ID,), mode="local-artifact", artifact_paths={SOURCE_ID: str(raw)},
                output_root=root / "refresh", options={"acquisition": acquisition}))
            summary = result["results"][0]["summary"]
            handoff_manifest = next((root / "refresh").rglob("candidate-handoff/manifest.json"))
            handoff_doc = json.loads(handoff_manifest.read_text(encoding="utf-8"))
            handoff_row = json.loads((handoff_manifest.parent / "normalized" / "records.jsonl").read_text(encoding="utf-8"))
        self.assertEqual(result["exit_status"], "ok")
        self.assertTrue(summary["candidate_handoff"])
        self.assertEqual(summary["normalized_rows"], 1)
        self.assertEqual(handoff_doc["release_state"], "not-created")
        self.assertEqual(handoff_doc["publication_state"], "private-candidate")
        self.assertEqual(handoff_doc["normalized_rows"], 1)
        self.assertEqual(handoff_row["normalized"]["facility_name"], "Synthetic locality 10")
        self.assertEqual(handoff_row["normalized"]["source_locality_name"], "Synthetic locality 10")
        self.assertEqual(handoff_row["source_values"]["navn"], "Synthetic locality 10")
        self.assertEqual(handoff_row["normalized"]["source_capacity"]["current"], 80)


if __name__ == "__main__":
    unittest.main()
