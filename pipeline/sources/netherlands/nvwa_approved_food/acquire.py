"""Bounded live acquisition for NVWA's published approved-food SOAP lists."""
from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pipeline.common.acquisition import (
    AcquisitionError, _atomic_bytes, fetch_source, require_terms_review, selected_headers, utc_now,
)

from .adapter import CONFIG, LIST_CODES, NvwaContractError, _parse_control, _parse_response


def _soap_request(list_code: str, offset: int, limit: int) -> bytes:
    tns = CONFIG["soap_type_namespace"]
    op = CONFIG["soap_operation_namespace"]
    nil = 'xsi:nil="true"'
    # The generated service leaves its four collection properties uninitialized
    # when they are sent as xsi:nil. Send empty collection wrappers instead.
    fields = "<typ:productGroup " + nil + "/>"
    fields += "<typ:categorieen/><typ:diersoorten/>"
    fields += f"<typ:lijstcode>{list_code}</typ:lijstcode>"
    fields += f"<typ:activiteiten/><typ:handelsnaam {nil}/><typ:producten/><typ:erkenningsnummer {nil}/><typ:taal>NL</typ:taal>"
    fields += (
        "<typ:pagination>"
        f"<typ:cvgLimit>{limit}</typ:cvgLimit>"
        f"<typ:cvgTotal {nil}/>"
        f"<typ:cvgReturned {nil}/>"
        f"<typ:cvgOffset>{offset}</typ:cvgOffset>"
        "</typ:pagination>"
        f"<typ:exportland {nil}/><typ:postcode {nil}/>"
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" '
        f'xmlns:op="{op}" xmlns:typ="{tns}" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        "<soapenv:Header/><soapenv:Body>"
        "<typ:zoekBedrijfElement><typ:iZoekCriteria>"
        f"{fields}"
        "</typ:iZoekCriteria></typ:zoekBedrijfElement>"
        "</soapenv:Body></soapenv:Envelope>"
    ).encode("utf-8")


def _store(path: Path, content: bytes) -> dict[str, Any]:
    if path.exists():
        if path.read_bytes() != content:
            raise AcquisitionError("existing NVWA artifact differs; choose a new run ID", failure_class="artifact-collision")
    else:
        _atomic_bytes(path, content)
    return {"file": path.name, "sha256": hashlib.sha256(content).hexdigest(), "byte_size": len(content)}


def _post_page(*, list_code: str, offset: int, limit: int, timeout_seconds: float) -> tuple[bytes, dict[str, str], str]:
    body = _soap_request(list_code, offset, limit)
    request = urllib.request.Request(
        CONFIG["soap_endpoint"],
        data=body,
        headers={
            "Accept": "text/xml",
            "Content-Type": "text/xml; charset=UTF-8",
            "SOAPAction": f'"{CONFIG["soap_action"]}"',
            "User-Agent": "UntilEveryCage/private-NVWA-acquisition-v0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            if not 200 <= response.status < 300:
                raise AcquisitionError(f"NVWA returned HTTP {response.status}", failure_class=f"http-{response.status}")
            content_type = (response.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
            if content_type and content_type not in {"text/xml", "application/xml", "application/soap+xml"}:
                raise AcquisitionError("NVWA SOAP response has an unexpected content type", failure_class="content-type")
            raw = response.read(int(CONFIG["max_bytes_per_response"]) + 1)
            if len(raw) > int(CONFIG["max_bytes_per_response"]):
                raise AcquisitionError("NVWA SOAP page exceeds configured byte bound", failure_class="size-bound")
            return raw, selected_headers(response.headers), response.geturl()
    except urllib.error.HTTPError as error:
        retryable = error.code == 429 or 500 <= error.code <= 599
        raise AcquisitionError(f"NVWA SOAP returned HTTP {error.code}", failure_class=f"http-{error.code}", retryable=retryable) from error
    except urllib.error.URLError as error:
        raise AcquisitionError(f"NVWA SOAP network error: {error.reason}", failure_class="network", retryable=True) from error


def acquire_bundle(
    *, output_root: str | Path = "data/raw", run_id: str, terms_review_path: str | Path,
    timeout_seconds: float = 60.0,
) -> dict[str, Any]:
    """Fetch the current control XML and all pages for the eight scoped lists."""
    if not run_id or Path(run_id).name != run_id or run_id in {".", ".."}:
        raise AcquisitionError("run_id must be a single safe path component", failure_class="configuration")
    terms_review = require_terms_review(Path(terms_review_path))
    source_root = Path(output_root) / CONFIG["source_id"] / run_id
    if source_root.exists() and (source_root / "bundle-manifest.json").exists():
        raise AcquisitionError("NVWA acquisition run already exists; choose a new run ID", failure_class="artifact-collision")
    source_root.mkdir(parents=True, exist_ok=True)
    control_meta = fetch_source(
        source_id=CONFIG["source_id"], url=CONFIG["source_url"], output_root=output_root,
        artifact_name="control.xml", terms_review_path=terms_review_path, run_id=run_id,
        timeout_seconds=timeout_seconds, max_bytes=int(CONFIG["max_bytes_per_response"]),
        allowed_content_types=("application/xml", "text/xml", "application/octet-stream"),
        user_agent="UntilEveryCage/private-NVWA-acquisition-v0",
        code_version=CONFIG["adapter_version"], config_version=CONFIG["config_version"],
        coverage=CONFIG["coverage"],
        rights_caveat="NVWA site content is stated to be CC0 unless an item says otherwise; do not imply NVWA endorsement; separate publication review remains required.",
        privacy_caveat="Restricted private acquisition; source addresses are retained for separate geocoding and privacy screening; publication stays blocked.",
    )
    control_path = Path(control_meta["artifact_path"])
    control_bytes = control_path.read_bytes()
    labels = _parse_control(control_bytes)
    control_item = {
        **{key: value for key, value in _store(control_path, control_bytes).items() if key != "file"},
        "kind": "control", "file": control_path.name, "content_type": control_meta.get("response_headers", {}).get("Content-Type"),
        "retrieved_at_utc": control_meta.get("retrieved_at_utc"), "final_url": control_meta.get("final_url"),
        "list_codes_advertised": sorted(labels),
    }
    artifacts: list[dict[str, Any]] = [control_item]
    artifacts_by_list: dict[str, dict[str, int]] = {}
    for list_index, list_code in enumerate(LIST_CODES):
        if list_code not in labels:
            raise NvwaContractError("required list code missing from current control XML: " + list_code)
        offset = 0
        page_index = 0
        total: int | None = None
        observations = 0
        recognition_numbers: set[str] = set()
        while page_index < int(CONFIG["max_pages_per_list"]):
            request_started = utc_now()
            raw, headers, final_url = _post_page(
                list_code=list_code, offset=offset, limit=int(CONFIG["page_size"]),
                timeout_seconds=timeout_seconds,
            )
            page_rows, pagination = _parse_response(raw, list_code=list_code)
            if pagination["cvgOffset"] is not None and pagination["cvgOffset"] != offset:
                raise AcquisitionError("NVWA returned an unexpected pagination offset", failure_class="pagination")
            if pagination["cvgTotal"] is not None:
                if total is not None and pagination["cvgTotal"] != total:
                    raise AcquisitionError("NVWA total changed while paging a list", failure_class="pagination")
                total = pagination["cvgTotal"]
            filename = f"{list_code}-page-{page_index:03d}.xml"
            page_path = source_root / filename
            saved = _store(page_path, raw)
            page_item = {
                **saved, "kind": "soap", "file": filename, "list_code": list_code,
                "list_label": labels[list_code], "page": page_index, "offset": offset,
                "limit": int(CONFIG["page_size"]), "observation_rows": len(page_rows),
                "cvg_total": pagination["cvgTotal"], "cvg_returned": pagination["cvgReturned"],
                "retrieved_at_utc": request_started, "response_headers": headers,
                "final_url": final_url,
            }
            artifacts.append(page_item)
            observations += len(page_rows)
            recognition_numbers.update(
                value for row in page_rows if (value := (row.get("erkenningsnummer") or "").strip())
            )
            page_index += 1
            if len(page_rows) == 0:
                break
            offset += len(page_rows)
            if total is not None and offset >= total and len(page_rows) == total:
                break
            if len(page_rows) < int(CONFIG["page_size"]):
                break
            if page_index < int(CONFIG["max_pages_per_list"]):
                time.sleep(float(CONFIG["request_delay_seconds"]))
        else:
            raise AcquisitionError(f"NVWA list exceeded configured page bound: {list_code}", failure_class="pagination-bound")
        artifacts_by_list[list_code] = {
            "observation_rows": observations,
            "unique_recognition_numbers_within_list": len(recognition_numbers),
            "pages": page_index,
        }
        if list_index < len(LIST_CODES) - 1:
            time.sleep(float(CONFIG["request_delay_seconds"]))

    completed_at = utc_now()
    bundle = {
        "bundle_version": "nvwa-approved-food-bundle-v1",
        "source_id": CONFIG["source_id"],
        "source_url": CONFIG["source_url"],
        "viewer_url": CONFIG["viewer_url"],
        "soap_endpoint": CONFIG["soap_endpoint"],
        "soap_action": CONFIG["soap_action"],
        "requested_at_utc": control_meta.get("requested_at_utc"),
        "completed_at_utc": completed_at,
        "retrieved_at_utc": completed_at,
        "terms_review": {key: terms_review[key] for key in ("decision", "reference", "reviewed_at")},
        "artifacts": artifacts,
        "observation_rows_by_list": artifacts_by_list,
        "count_semantics": "Observations and unique recognition numbers are reported within list only. No cross-list facility total is computed.",
    }
    manifest_path = source_root / "bundle-manifest.json"
    from pipeline.contracts.source_lifecycle import atomic_json
    atomic_json(manifest_path, bundle)
    return {
        "source_id": CONFIG["source_id"], "run_id": run_id,
        "bundle_path": str(manifest_path), "retrieved_at_utc": completed_at,
        "artifact_count": len(artifacts), "observation_rows_by_list": artifacts_by_list,
        "publication_state": "private-only", "release_state": "not-created",
    }
