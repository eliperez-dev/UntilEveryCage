"""Bounded EEA ArcGIS acquisition; enumerate scoped IDs before fetching pages."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any
import urllib.parse
import urllib.request

from pipeline.contracts.source_lifecycle import atomic_bytes, atomic_json
from .adapter import (SOURCE_ID, SOURCE_URL, QUERY_URL, ADAPTER_VERSION, SCHEMA_VERSION,
                      REQUIRED_FIELDS, WHERE, YEAR, bundle_digest)

METADATA_URL = "https://sdi.eea.europa.eu/catalogue/datahub/api/records/3bbf28cb-70e8-4073-8fe9-8c1d9c513f52/formatters/xml"
MAX_BYTES = 64 * 1024 * 1024
MAX_PAGES = 100


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class SameHostRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if (urllib.parse.urlsplit(newurl).scheme != "https"
                or urllib.parse.urlsplit(newurl).netloc != urllib.parse.urlsplit(req.full_url).netloc):
            raise ValueError("EEA redirect escaped the publisher host")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _get(url: str, timeout: float, max_bytes: int, opener: Any = None) -> tuple[bytes, dict[str, Any]]:
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme != "https" or parsed.hostname not in {"air.discomap.eea.europa.eu", "sdi.eea.europa.eu"}
            or parsed.username or parsed.password or parsed.fragment):
        raise ValueError("EEA acquisition URL is outside the publisher HTTPS scope")
    client = opener or urllib.request.build_opener(SameHostRedirect())
    req = urllib.request.Request(url, headers={"User-Agent": "UntilEveryCage-source-pipeline/1.0"})
    with client.open(req, timeout=timeout) as response:
        if (response.status != 200 or urllib.parse.urlsplit(response.geturl()).scheme != "https"
                or urllib.parse.urlsplit(response.geturl()).netloc != parsed.netloc):
            raise ValueError("EEA response status or host changed")
        raw = response.read(max_bytes + 1)
        if len(raw) > max_bytes:
            raise ValueError("EEA response exceeds the byte limit")
        content_type = response.headers.get("Content-Type", "").split(";")[0].lower()
        allowed = {"application/xml", "text/xml"} if url == METADATA_URL else {"application/json", "application/geo+json", "text/plain"}
        if content_type not in allowed:
            raise ValueError("EEA response content type changed")
        return raw, {"requested_url": url, "final_url": response.geturl(), "retrieved_at_utc": now(),
                     "sha256": hashlib.sha256(raw).hexdigest(), "byte_size": len(raw), "content_type": content_type}


def _json(url: str, timeout: float, opener: Any = None) -> tuple[dict[str, Any], bytes, dict[str, Any]]:
    raw, facts = _get(url, timeout, 4 * 1024 * 1024, opener)
    doc = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(doc, dict) or "error" in doc:
        raise ValueError("EEA ArcGIS response is invalid")
    return doc, raw, facts


def fetch(*, output_root: Path, run_id: str, terms_review_path: Path, timeout_seconds: float = 60,
          max_bytes: int = MAX_BYTES, page_size: int = 500, opener: Any = None) -> dict[str, Any]:
    review = json.loads(terms_review_path.read_text(encoding="utf-8"))
    if (review.get("source_id") != SOURCE_ID or review.get("decision") != "approved"
            or review.get("license") != "Creative Commons Attribution" or review.get("license_version") != "4.0"
            or review.get("private_preview_only") is not True):
        raise ValueError("EEA requires the exact private CC BY 4.0 terms record")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,160}", run_id) or not 1 <= page_size <= 1000 or not 1 <= max_bytes <= MAX_BYTES:
        raise ValueError("EEA acquisition bounds are invalid")
    metadata_raw, metadata_facts = _get(METADATA_URL, timeout_seconds, 1024 * 1024, opener)
    # Check current exact-source metadata, not an unrelated EEA dataset licence.
    import xml.etree.ElementTree as ET
    metadata = ET.fromstring(metadata_raw)
    if not any("creativecommons.org/licenses/by/4.0" in (item.text or "") or
               any("creativecommons.org/licenses/by/4.0" in value for value in item.attrib.values()) for item in metadata.iter()):
        raise ValueError("EEA catalogue no longer confirms CC BY 4.0")
    layer, layer_raw, layer_facts = _json(SOURCE_URL + "?f=json", timeout_seconds, opener)
    if (layer.get("name") != "ied_SiteMap" or layer.get("geometryType") != "esriGeometryPoint"
            or layer.get("type") != "Feature Layer" or layer.get("maxRecordCount", 0) < page_size
            or layer.get("spatialReference", {}).get("latestWkid", layer.get("spatialReference", {}).get("wkid")) != 3857
            or not REQUIRED_FIELDS <= {field.get("name") for field in layer.get("fields", [])}):
        raise ValueError("EEA layer schema or native CRS changed")
    def query(**kwargs):
        return _json(QUERY_URL + "?" + urllib.parse.urlencode({"where": WHERE, "f": "json", **kwargs}), timeout_seconds, opener)
    count, count_raw, count_facts = query(returnCountOnly="true")
    ids_doc, ids_raw, ids_facts = query(returnIdsOnly="true")
    ids, expected = ids_doc.get("objectIds"), count.get("count")
    if (not isinstance(expected, int) or isinstance(expected, bool) or expected < 1 or not isinstance(ids, list)
            or not all(isinstance(x, int) and not isinstance(x, bool) for x in ids)
            or len(ids) != expected or len(set(ids)) != expected or ids_doc.get("exceededTransferLimit") is True):
        raise ValueError("EEA scoped count and complete unique ID enumeration do not reconcile")
    if (len(ids) + page_size - 1) // page_size > MAX_PAGES:
        raise ValueError("EEA source exceeds the reviewed page bound")
    root = output_root / SOURCE_ID / run_id
    pages = root / "source-pages"
    if root.exists():
        raise ValueError("EEA acquisition run must have a fresh immutable destination")
    pages.mkdir(parents=True)
    for name, raw in (("catalogue.xml", metadata_raw), ("layer.json", layer_raw), ("count.json", count_raw), ("ids.json", ids_raw)):
        atomic_bytes(root / name, raw)
    seen, page_facts, total = set(), [], 0
    ids.sort()
    for number, offset in enumerate(range(0, len(ids), page_size), 1):
        batch = ids[offset:offset + page_size]
        url = QUERY_URL + "?" + urllib.parse.urlencode({"where": WHERE, "objectIds": ",".join(map(str, batch)),
                    "outFields": "*", "outSR": "4326", "returnGeometry": "true", "orderByFields": "OBJECTID", "f": "geojson"})
        raw, facts = _get(url, timeout_seconds, min(max_bytes, 4 * 1024 * 1024), opener)
        doc = json.loads(raw.decode("utf-8-sig"))
        features = doc.get("features") if isinstance(doc, dict) else None
        if doc.get("type") != "FeatureCollection" or not isinstance(features, list) or doc.get("exceededTransferLimit") is True:
            raise ValueError("EEA feature page schema or transfer completeness changed")
        obtained = [f.get("properties", {}).get("OBJECTID") for f in features if isinstance(f, dict)]
        if len(obtained) != len(batch) or set(obtained) != set(batch) or seen.intersection(obtained):
            raise ValueError("EEA feature page IDs differ from the requested unique scope")
        seen.update(obtained)
        total += len(raw)
        if total > max_bytes:
            raise ValueError("EEA complete bundle exceeds the aggregate byte limit")
        name = f"page-{number:04d}.geojson"
        atomic_bytes(pages / name, raw)
        page_facts.append({"artifact": name, "features": len(features), **facts})
    end_ids, end_ids_raw, end_ids_facts = query(returnIdsOnly="true")
    if (not isinstance(end_ids.get("objectIds"), list) or sorted(end_ids["objectIds"]) != ids
            or seen != set(ids) or end_ids.get("exceededTransferLimit") is True):
        raise ValueError("EEA scoped membership changed during acquisition")
    atomic_bytes(root / "ids-after.json", end_ids_raw)
    digest, size = bundle_digest(pages)
    facts = {"source_id": SOURCE_ID, "run_id": run_id, "canonical_url": SOURCE_URL, "query_url": QUERY_URL,
             "retrieved_at_utc": now(), "reporting_year": YEAR, "where": WHERE,
             "source_native_crs": "EPSG:3857", "requested_geometry_crs": "EPSG:4326",
             "feature_count": expected, "object_id_count": len(ids), "retrieved_unique_object_id_count": len(seen),
             "page_count": len(page_facts), "pages": page_facts, "source_membership_rechecked": True,
             "artifact_sha256": digest, "artifact_byte_size": size, "terms_review": review,
             "catalogue": metadata_facts, "layer": layer_facts, "count": count_facts, "ids": ids_facts,
             "ids_after": end_ids_facts, "adapter_version": ADAPTER_VERSION, "schema_version": SCHEMA_VERSION,
             "license": "Creative Commons Attribution", "license_version": "4.0", "attribution": "European Environment Agency"}
    atomic_json(root / "acquisition-metadata.json", facts)
    return {**facts, "artifact_path": str(pages)}
