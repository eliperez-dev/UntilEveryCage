"""Bounded, official ArcGIS REST acquisition for Norway aquaculture localities."""
from __future__ import annotations

import hashlib
import json
import math
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pipeline.contracts.source_lifecycle import atomic_bytes, atomic_json
from .aquaculture import (ADAPTER_VERSION, COVERAGE, LICENSE, LICENSE_URL, LICENSE_VERSION,
                          MAX_BYTES, MAX_PAGES, MAX_PAGE_SIZE, QUERY_URL, SCHEMA_VERSION,
                          SOURCE_ID, SOURCE_URL, bundle_digest)

MAX_METADATA_BYTES = 4 * 1024 * 1024
ALLOWED_HOST = "gis.fiskeridir.no"


class AcquisitionError(ValueError):
    """An official response failed a bounded acquisition check."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _terms(path: Path) -> dict[str, Any]:
    try:
        review = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AcquisitionError("terms review cannot be read") from error
    if (not isinstance(review, dict) or review.get("source_id") != SOURCE_ID
            or review.get("decision") != "approved"
            or review.get("license") != LICENSE
            or review.get("license_version") != LICENSE_VERSION
            or review.get("private_preview_only") is not True):
        raise AcquisitionError("terms review must approve the exact NLOD source for private preview only")
    return review


def _get(url: str, *, timeout: float, max_bytes: int, opener: Any = None) -> tuple[bytes, dict[str, Any]]:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != ALLOWED_HOST or parsed.username or parsed.password or parsed.fragment:
        raise AcquisitionError("request escaped the official GIS HTTPS host")
    request = urllib.request.Request(url, headers={"User-Agent": "UntilEveryCage-private-preview/1.0", "Accept": "application/geo+json, application/json"})
    try:
        response = (opener or urllib.request).urlopen(request, timeout=timeout)
    except urllib.error.HTTPError as error:
        raise AcquisitionError(f"official service returned HTTP {error.code}") from error
    except urllib.error.URLError as error:
        raise AcquisitionError(f"official service network error: {error.reason}") from error
    with response:
        final = urllib.parse.urlparse(response.geturl())
        if not 200 <= response.status < 300 or final.scheme != "https" or final.hostname != ALLOWED_HOST:
            raise AcquisitionError("official response status or redirect validation failed")
        raw = response.read(max_bytes + 1)
        if len(raw) > max_bytes:
            raise AcquisitionError("official response exceeded configured byte limit")
        headers = {str(key): str(value) for key, value in response.headers.items()}
        content_type = headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if content_type not in {"application/json", "application/geo+json", "text/plain"}:
            raise AcquisitionError("official response has unsupported content type")
        facts = {"requested_url": url, "final_url": response.geturl(),
                 "http_status": response.status, "content_type": headers.get("Content-Type"),
                 "response_headers": {key: headers[key] for key in ("ETag", "Last-Modified", "Content-Length") if key in headers},
                 "byte_size": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    return raw, facts


def _json_request(url: str, *, timeout: float, max_bytes: int, opener: Any = None) -> tuple[dict[str, Any], dict[str, Any]]:
    raw, facts = _get(url, timeout=timeout, max_bytes=max_bytes, opener=opener)
    try:
        value = json.loads(raw.decode("utf-8-sig", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AcquisitionError("official response is not valid UTF-8 JSON") from error
    if not isinstance(value, dict) or "error" in value:
        raise AcquisitionError("official ArcGIS response contains an error or invalid envelope")
    return value, facts


def fetch(*, output_root: Path, run_id: str, terms_review_path: Path,
          timeout_seconds: float = 60.0, max_bytes: int = MAX_BYTES,
          page_size: int = MAX_PAGE_SIZE, opener: Any = None) -> dict[str, Any]:
    """Fetch complete locality layer to private, response-page artifacts."""
    terms = _terms(terms_review_path)
    if not 1 <= page_size <= MAX_PAGE_SIZE:
        raise AcquisitionError(f"page_size must be between 1 and {MAX_PAGE_SIZE}")
    requested_at = _now()
    layer_url = SOURCE_URL + "?f=pjson"
    layer, layer_facts = _json_request(layer_url, timeout=timeout_seconds, max_bytes=MAX_METADATA_BYTES, opener=opener)
    if (layer.get("name") != "Lokaliteter" or layer.get("type") != "Feature Layer"
            or layer.get("geometryType") != "esriGeometryPoint"
            or int(layer.get("maxRecordCount", 0)) < page_size
            or not {field.get("name") for field in layer.get("fields", []) if isinstance(field, dict)} >= {
                "objectid", "loknr", "til_arter", "symbol", "status_lokalitet", "kommune", "fylke"}):
        raise AcquisitionError("ArcGIS layer metadata changed; acquisition held for schema review")
    if int(layer.get("spatialReference", {}).get("wkid", 0)) != 25833:
        raise AcquisitionError("ArcGIS native CRS changed; acquisition held for review")
    count_url = QUERY_URL + "?" + urllib.parse.urlencode({"where": "1=1", "returnCountOnly": "true", "f": "json"})
    count, count_facts = _json_request(count_url, timeout=timeout_seconds, max_bytes=MAX_METADATA_BYTES, opener=opener)
    expected_count = count.get("count")
    if isinstance(expected_count, bool) or not isinstance(expected_count, int) or expected_count < 0:
        raise AcquisitionError("ArcGIS count response is invalid")
    ids_url = QUERY_URL + "?" + urllib.parse.urlencode({"where": "1=1", "returnIdsOnly": "true", "f": "json"})
    id_doc, ids_facts = _json_request(ids_url, timeout=timeout_seconds, max_bytes=MAX_METADATA_BYTES, opener=opener)
    ids = id_doc.get("objectIds")
    if not isinstance(ids, list) or not all(isinstance(item, (int, str)) and not isinstance(item, bool) for item in ids):
        raise AcquisitionError("ArcGIS object-ID response is invalid")
    if len(ids) != expected_count or len({str(item) for item in ids}) != len(ids):
        raise AcquisitionError("ArcGIS count and complete unique object-ID list do not reconcile")
    page_count = (len(ids) + page_size - 1) // page_size
    if page_count > MAX_PAGES:
        raise AcquisitionError("ArcGIS dataset exceeds the configured page bound")
    target = output_root / SOURCE_ID / run_id
    pages = target / "source-pages"
    pages.mkdir(parents=True, exist_ok=True)
    atomic_json(pages / "layer-metadata.json", layer)
    page_facts: list[dict[str, Any]] = []
    acquired_ids: set[str] = set()
    total_bytes = 0
    coordinates_checked = 0
    for page_number, offset in enumerate(range(0, len(ids), page_size), start=1):
        batch = ids[offset:offset + page_size]
        page_url = QUERY_URL + "?" + urllib.parse.urlencode({
            "objectIds": ",".join(str(item) for item in batch),
            "outFields": "*", "returnGeometry": "true", "outSR": "4326", "f": "geojson",
        })
        raw, facts = _get(page_url, timeout=timeout_seconds, max_bytes=max_bytes, opener=opener)
        try:
            page = json.loads(raw.decode("utf-8-sig", errors="strict"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise AcquisitionError("ArcGIS feature page is not valid UTF-8 JSON") from error
        features = page.get("features") if isinstance(page, dict) else None
        if page.get("type") != "FeatureCollection" or not isinstance(features, list) or len(features) != len(batch):
            raise AcquisitionError("ArcGIS feature page count/schema changed; acquisition held")
        page_ids = []
        for feature in features:
            properties = feature.get("properties") if isinstance(feature, dict) else None
            if not isinstance(properties, dict) or "objectid" not in properties:
                raise AcquisitionError("ArcGIS feature page is missing its object identifier")
            page_ids.append(str(properties["objectid"]))
            geometry = feature.get("geometry")
            pair = geometry.get("coordinates") if isinstance(geometry, dict) and geometry.get("type") == "Point" else None
            if not isinstance(pair, list) or len(pair) < 2:
                raise AcquisitionError("ArcGIS feature page has missing or non-point geometry")
            try:
                longitude, latitude = float(pair[0]), float(pair[1])
            except (TypeError, ValueError, OverflowError) as error:
                raise AcquisitionError("ArcGIS returned nonnumeric WGS84 geometry") from error
            west, east, south, north = (3.0, 32.0, 57.0, 72.0)
            if not (math.isfinite(longitude) and math.isfinite(latitude)
                    and west <= longitude <= east and south <= latitude <= north):
                raise AcquisitionError("ArcGIS full-layer coordinates are outside the reviewed Norway envelope")
            coordinates_checked += 1
        if len(set(page_ids)) != len(page_ids) or set(page_ids) != {str(item) for item in batch}:
            raise AcquisitionError("ArcGIS feature-page IDs do not match the requested page")
        acquired_ids.update(page_ids)
        total_bytes += len(raw)
        if total_bytes > max_bytes:
            raise AcquisitionError("ArcGIS full layer exceeded configured aggregate byte limit")
        filename = f"page-{page_number:04d}.geojson"
        atomic_bytes(pages / filename, raw)
        page_facts.append({"artifact": filename, "requested_url": facts["requested_url"],
                           "final_url": facts["final_url"], "http_status": facts["http_status"],
                           "content_type": facts["content_type"], "byte_size": facts["byte_size"],
                           "sha256": facts["sha256"], "features": len(features)})
    if len(acquired_ids) != expected_count or len(acquired_ids) != len(ids):
        raise AcquisitionError("retrieved ArcGIS feature IDs do not cover the full count")
    bundle_sha256, bundle_size = bundle_digest(pages)
    retrieved_at = _now()
    metadata = {
        "source_id": SOURCE_ID, "run_id": run_id, "acquisition_method": "official_arcgis_ids_then_bounded_geojson_pages",
        "canonical_url": SOURCE_URL, "query_url": QUERY_URL, "retrieved_at_utc": retrieved_at,
        "requested_at_utc": requested_at, "source_native_crs": "EPSG:25833",
        "requested_geometry_crs": "EPSG:4326", "source_geometry_semantics": "registered aquaculture locality point",
        "feature_count": expected_count, "object_id_count": len(ids), "retrieved_unique_object_id_count": len(acquired_ids),
        "page_size": page_size, "page_count": page_count, "coordinates_checked": coordinates_checked,
        "coordinate_bounds_validation": "passed for every retrieved feature; bounds omitted from manifest",
        "pages": page_facts,
        "layer_metadata": layer_facts, "count_response": count_facts, "id_response": ids_facts,
        "total_page_bytes": total_bytes, "artifact_sha256": bundle_sha256, "artifact_byte_size": bundle_size,
        "license": LICENSE, "license_version": LICENSE_VERSION, "license_url": LICENSE_URL,
        "license_text_url": "https://data.norge.no/nlod/en/2.0", "attribution": "Source: Fiskeridirektoratet",
        "coverage": COVERAGE, "terms_review": terms,
        "adapter_version": ADAPTER_VERSION, "schema_version": SCHEMA_VERSION,
        "publication_status": "private-candidate-only; project approval required",
    }
    atomic_json(target / "acquisition-metadata.json", metadata)
    return {**metadata, "artifact_path": str(pages)}


__all__ = ["AcquisitionError", "fetch"]
