"""Bounded private capture from EPA ECHO's public ArcGIS facility service."""
from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from pipeline.contracts.source_lifecycle import atomic_json
from pipeline.sources.italy.acquire import require_terms_review

from . import SOURCE_ID

SERVICE_URL = "https://echogeo.epa.gov/arcgis/rest/services/ECHO/Facilities/MapServer/0"
QUERY_URL = SERVICE_URL + "/query"
MAX_RECORDS = 20_000
DEFAULT_MAX_BYTES = 64 * 1024 * 1024
PAGE_SIZE = 300
SIC_CODES = ("0211", "0212", "0213", "0214", "0219", "0241", "0251", "0252", "0253", "0254", "0259")
FIELDS = (
    "OBJECTID", "REGISTRY_ID", "FAC_NAME", "FAC_STREET", "FAC_CITY", "FAC_STATE", "FAC_ZIP",
    "FAC_LAT", "FAC_LONG", "FAC_COLLECTION_METHOD", "FAC_REFERENCE_POINT", "FAC_ACCURACY_METERS",
    "FAC_ACTIVE_FLAG", "NPDES_FLAG", "NPDES_IDS", "CWA_PERMIT_TYPES", "CWA_NAICS", "CWA_SICS",
    "FAC_NAICS_CODES", "FAC_SIC_CODES",
)


class AcquisitionError(ValueError):
    """An unsafe, invalid, or incomplete EPA response."""


def build_where() -> str:
    """Return the deliberately narrow native EPA industry/permit filter."""
    return "NPDES_FLAG = 'Y' AND (CWA_NAICS LIKE '112%' OR CWA_SICS IN (" + ",".join(
        f"'{code}'" for code in SIC_CODES
    ) + "))"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _url(params: dict[str, Any]) -> str:
    return QUERY_URL + "?" + urllib.parse.urlencode(params)


def _get_json(url: str, *, timeout_seconds: float, max_bytes: int,
              opener: Callable[..., Any] | None = None) -> tuple[bytes, dict[str, Any]]:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "echogeo.epa.gov" or parsed.username or parsed.password:
        raise AcquisitionError("request URL is outside the approved EPA HTTPS host")
    request = urllib.request.Request(url, headers={"User-Agent": "UntilEveryCage-private-preview/1.0", "Accept": "application/json"})
    try:
        response = (opener or urllib.request.urlopen)(request, timeout=timeout_seconds)
    except (urllib.error.URLError, TimeoutError) as error:
        raise AcquisitionError("EPA request failed") from error
    with response:
        final = urllib.parse.urlparse(response.geturl())
        if not 200 <= int(response.status) < 300 or final.scheme != "https" or final.hostname != "echogeo.epa.gov" or final.username or final.password:
            raise AcquisitionError("EPA response status or redirect rejected")
        body = response.read(max_bytes + 1)
        if len(body) > max_bytes:
            raise AcquisitionError("EPA response exceeds configured byte bound")
        content_type = response.headers.get("Content-Type", "").lower()
        if content_type and "json" not in content_type:
            raise AcquisitionError("EPA response content type is not JSON")
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AcquisitionError("EPA response is not valid JSON") from error
    if not isinstance(payload, dict) or payload.get("error"):
        raise AcquisitionError("EPA service returned an error payload")
    return body, payload


def fetch(*, output_root: Path, run_id: str, terms_review_path: Path,
          timeout_seconds: float = 60.0, max_bytes: int = DEFAULT_MAX_BYTES,
          page_size: int = PAGE_SIZE, opener: Callable[..., Any] | None = None) -> dict[str, Any]:
    """Capture the bounded filtered result set and preserve exact response pages.

    No row values are returned to callers. The ZIP is restricted source
    evidence; the sidecar contains aggregate retrieval facts only.
    """
    if not 1 <= page_size <= 500 or max_bytes <= 0 or timeout_seconds <= 0:
        raise AcquisitionError("invalid acquisition bounds")
    review = require_terms_review(terms_review_path)
    started = _utc_now()
    where = build_where()
    common = {"where": where, "f": "json"}
    count_body, count_payload = _get_json(_url({**common, "returnCountOnly": "true"}), timeout_seconds=timeout_seconds, max_bytes=1024 * 1024, opener=opener)
    count = count_payload.get("count")
    if not isinstance(count, int) or count < 1 or count > MAX_RECORDS:
        raise AcquisitionError("EPA result count is empty or exceeds the configured record bound")
    ids_body, ids_payload = _get_json(_url({**common, "returnIdsOnly": "true"}), timeout_seconds=timeout_seconds, max_bytes=4 * 1024 * 1024, opener=opener)
    object_ids = ids_payload.get("objectIds")
    if not isinstance(object_ids, list) or len(object_ids) != count or any(not isinstance(value, int) for value in object_ids):
        raise AcquisitionError("EPA object-ID list does not reconcile to the result count")
    if len(set(object_ids)) != len(object_ids):
        raise AcquisitionError("EPA object-ID list contains duplicates")

    responses: list[tuple[str, bytes]] = [("result-count.json", count_body), ("object-ids.json", ids_body)]
    total_bytes = len(count_body) + len(ids_body)
    seen_ids: set[int] = set()
    for page_number, offset in enumerate(range(0, len(object_ids), page_size), start=1):
        page_ids = object_ids[offset:offset + page_size]
        page_url = _url({
            **common, "objectIds": ",".join(str(value) for value in page_ids),
            "outFields": ",".join(FIELDS), "returnGeometry": "false", "returnZ": "false", "returnM": "false",
        })
        body, payload = _get_json(page_url, timeout_seconds=timeout_seconds, max_bytes=max_bytes, opener=opener)
        features = payload.get("features")
        if not isinstance(features, list) or len(features) != len(page_ids):
            raise AcquisitionError("EPA feature page does not reconcile to requested IDs")
        page_found: set[int] = set()
        for feature in features:
            attributes = feature.get("attributes") if isinstance(feature, dict) else None
            object_id = attributes.get("OBJECTID") if isinstance(attributes, dict) else None
            if not isinstance(object_id, int) or object_id not in page_ids or object_id in seen_ids or object_id in page_found:
                raise AcquisitionError("EPA feature page has invalid or duplicate object IDs")
            page_found.add(object_id)
        if page_found != set(page_ids):
            raise AcquisitionError("EPA feature page IDs differ from the requested set")
        seen_ids.update(page_found)
        total_bytes += len(body)
        if total_bytes > max_bytes:
            raise AcquisitionError("combined EPA response pages exceed configured byte bound")
        responses.append((f"response-{page_number:04d}.json", body))
    if len(seen_ids) != count:
        raise AcquisitionError("EPA feature count does not reconcile")

    run_dir = output_root / SOURCE_ID / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = run_dir / "source-responses.zip"
    with zipfile.ZipFile(artifact_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name, body in responses:
            archive.writestr(name, body)
    artifact_bytes = artifact_path.read_bytes()
    if len(artifact_bytes) > max_bytes:
        artifact_path.unlink(missing_ok=True)
        raise AcquisitionError("preserved EPA archive exceeds configured byte bound")
    retrieved = _utc_now()
    metadata = {
        "source_id": SOURCE_ID, "run_id": run_id,
        "acquisition_method": "bounded_epa_arcgis_rest_query",
        "adapter_version": "us-epa-echo-animal-acquisition-v1",
        "config_version": "us-epa-echo-facilities-cwa-naics-sic-v1",
        "artifact": artifact_path.name, "artifact_path": str(artifact_path),
        "byte_size": len(artifact_bytes), "sha256": hashlib.sha256(artifact_bytes).hexdigest(),
        "response_bytes": total_bytes, "input_rows": count, "response_pages": max(0, len(responses) - 2),
        "requested_at_utc": started, "retrieved_at_utc": retrieved,
        "source_url": SERVICE_URL, "final_url": SERVICE_URL,
        "query_where": where, "fields": list(FIELDS), "page_size": page_size,
        "source_license_url": "https://pasteur.epa.gov/license/sciencehub-license.html",
        "terms_review": review,
        "coverage_caveat": "CWA/NPDES-associated ECHO records classified under selected livestock/poultry NAICS/SIC codes; not confirmed CAFO status, operating status, complete inventory, or publication approval",
    }
    atomic_json(run_dir / "acquisition-metadata.json", metadata)
    return metadata
