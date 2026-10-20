"""Synthetic contracts for Norway aquaculture acquisition and private refresh."""
from __future__ import annotations

import hashlib
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
        "fylke": "Example region", "til_innehavere": "synthetic holder",
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
        self.assertEqual(parsed["accepted"][0]["normalized"]["coordinates"]["source_crs"], "EPSG:4326")
        self.assertIn("not permit-holder mailing address", parsed["accepted"][0]["normalized"]["coordinates"]["location_semantics"])
        self.assertEqual(parsed["quarantined"][0]["reasons"], ["out_of_animal_aquaculture_scope"])
        self.assertNotIn("til_innehavere", json.dumps(parsed["accepted"]))

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
                      "fields": [{"name": key} for key in ("objectid", "loknr", "til_arter", "symbol", "status_lokalitet", "kommune", "fylke")]}

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
        self.assertEqual(result["exit_status"], "ok")
        self.assertTrue(summary["candidate_handoff"])
        self.assertEqual(summary["normalized_rows"], 1)
        self.assertEqual(handoff_doc["release_state"], "not-created")
        self.assertEqual(handoff_doc["publication_state"], "private-candidate")
        self.assertEqual(handoff_doc["normalized_rows"], 1)


if __name__ == "__main__":
    unittest.main()
