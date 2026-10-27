"""Bounded, token-backed DENUE API acquisition. Never logs request URLs."""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pipeline.contracts.source_lifecycle import atomic_bytes

from .adapter import ACTIVITY_CODES, API_BASE, SOURCE_FIELDS, SOURCE_ID

STATE_CODES = tuple(f"{number:02d}" for number in range(1, 33))
DEFAULT_PAGE_SIZE = 250
DEFAULT_MAX_RECORDS = 25_000
DEFAULT_MAX_REQUESTS = 300
DEFAULT_MAX_BYTES = 32 * 1024 * 1024
COUNT_ACTIVITY_CODE = "31161"  # SCIAN subrama; Cuantificar documents 5-digit codes.


class DenueAcquisitionError(ValueError):
    """Safe acquisition error; messages never include URLs or response data."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Keep the token-bearing path on the original official endpoint."""

    def redirect_request(self, request, fp, code, message, headers, new_url):
        return None


def _validate_official_url(url: str) -> None:
    parts = urllib.parse.urlsplit(url)
    if (parts.scheme != "https" or parts.hostname != "www.inegi.org.mx"
            or parts.username or parts.password or parts.port not in (None, 443)):
        raise DenueAcquisitionError("DENUE request is outside the approved official HTTPS host")


def _validate_bounds(page_size: int, max_records: int, max_requests: int,
                     max_bytes: int, timeout_seconds: float,
                     max_duration_seconds: float) -> None:
    if not 1 <= page_size <= 250:
        raise DenueAcquisitionError("page size is outside the configured bound")
    if not 1 <= max_records <= 100_000:
        raise DenueAcquisitionError("record limit is outside the configured bound")
    if not 1 <= max_requests <= 512:
        raise DenueAcquisitionError("request limit is outside the configured bound")
    if not 1024 <= max_bytes <= 128 * 1024 * 1024:
        raise DenueAcquisitionError("byte limit is outside the configured bound")
    if not 1 <= timeout_seconds <= 120 or not 1 <= max_duration_seconds <= 3600:
        raise DenueAcquisitionError("time limit is outside the configured bound")


def _request_json(url: str, *, timeout_seconds: float, max_response_bytes: int,
                  opener: Any = None) -> tuple[Any, int]:
    _validate_official_url(url)
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        if opener is None:
            response = urllib.request.build_opener(_NoRedirect()).open(request, timeout=timeout_seconds)
        else:
            response = opener.urlopen(request, timeout=timeout_seconds)
        with response:
            final_url = response.geturl() if hasattr(response, "geturl") else url
            _validate_official_url(final_url)
            status = getattr(response, "status", 200)
            if not 200 <= status < 300:
                raise DenueAcquisitionError("DENUE returned an unsuccessful HTTP status")
            content_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
            if content_type not in {"application/json", "text/json", "text/plain"}:
                raise DenueAcquisitionError("DENUE response was not JSON")
            body = response.read(max_response_bytes + 1)
    except DenueAcquisitionError:
        raise
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        # Do not interpolate exception text: urllib exceptions can include the token URL.
        raise DenueAcquisitionError("DENUE request failed") from None
    if len(body) > max_response_bytes:
        raise DenueAcquisitionError("DENUE response exceeded the byte limit")
    try:
        value = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DenueAcquisitionError("DENUE response was not valid UTF-8 JSON") from error
    return value, len(body)


def _safe_token(token: str | None) -> str:
    token = token or os.environ.get("INEGI_DENUE_TOKEN")
    if not token or not token.strip():
        raise DenueAcquisitionError("INEGI_DENUE_TOKEN is required")
    if len(token) > 256:
        raise DenueAcquisitionError("DENUE token has an invalid length")
    return token.strip()


def _url(path: str, token: str) -> str:
    return API_BASE + path + "/" + urllib.parse.quote(token, safe="")


def _count_value(rows: Any, activity: str, state: str) -> int:
    if not isinstance(rows, list):
        raise DenueAcquisitionError("DENUE count response schema changed")
    matching = [row for row in rows if isinstance(row, dict)
                and str(row.get("AE")) == activity and str(row.get("AG")) == state]
    if len(matching) != 1:
        raise DenueAcquisitionError("DENUE count response did not match the requested scope")
    try:
        total = int(matching[0]["Total"])
    except (KeyError, TypeError, ValueError) as error:
        raise DenueAcquisitionError("DENUE count value was invalid") from error
    if total < 0:
        raise DenueAcquisitionError("DENUE count value was invalid")
    return total


def _detail_page_records(value: Any) -> list[dict[str, Any]]:
    """Normalize only INEGI's two exact no-results response strings."""
    if isinstance(value, str):
        marker = value.strip()
        # DENUE sometimes JSON-encodes its plain-text message one extra time.
        # Decode at most one layer, then accept only this exact message after
        # trimming whitespace, including whitespace inside the quoted text.
        try:
            decoded = json.loads(marker)
        except json.JSONDecodeError:
            decoded = None
        if isinstance(decoded, str):
            marker = decoded.strip()
        if marker == "No hay resultados.":
            return []
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise DenueAcquisitionError("DENUE page count or schema did not match the bounded request")
    return value


def _page_path(state: str, activity: str, start: int, end: int) -> str:
    # Official BuscarAreaAct positional order: entity, municipality, locality,
    # AGEB, block, sector, subsector, branch, class, name, from, to, Id.
    return (f"BuscarAreaAct/{state}/0/0/0/0/0/0/0/{activity}/0/"
            f"{start}/{end}/0")


def fetch(*, output_root: str | Path, token: str | None = None,
          page_size: int = DEFAULT_PAGE_SIZE,
          max_records: int = DEFAULT_MAX_RECORDS,
          max_requests: int = DEFAULT_MAX_REQUESTS,
          max_bytes: int = DEFAULT_MAX_BYTES,
          timeout_seconds: float = 30,
          max_duration_seconds: float = 900,
          states: tuple[str, ...] = STATE_CODES,
          opener: Any = None) -> dict[str, Any]:
    """Preflight counts, fetch only SCIAN 311611–311614, and preserve a private artifact."""
    _validate_bounds(page_size, max_records, max_requests, max_bytes,
                     timeout_seconds, max_duration_seconds)
    if not states or any(state not in STATE_CODES for state in states) or len(set(states)) != len(states):
        raise DenueAcquisitionError("state scope is invalid")
    secret = _safe_token(token)
    deadline = time.monotonic() + max_duration_seconds
    requests = 0
    response_bytes = 0

    def query(path: str) -> Any:
        nonlocal requests, response_bytes
        if requests >= max_requests:
            raise DenueAcquisitionError("DENUE request limit reached")
        if time.monotonic() >= deadline:
            raise DenueAcquisitionError("DENUE acquisition time limit reached")
        value, size = _request_json(_url(path, secret), timeout_seconds=timeout_seconds,
                                    max_response_bytes=max_bytes-response_bytes,
                                    opener=opener)
        requests += 1
        response_bytes += size
        if response_bytes > max_bytes:
            raise DenueAcquisitionError("DENUE acquisition exceeded the byte limit")
        return value

    # Cuantificar accepts comma-separated activity classes and geographic keys.
    state_counts: dict[str, int] = {}
    for state in states:
        result = query(f"Cuantificar/{COUNT_ACTIVITY_CODE}/{state}/0")
        state_counts[state] = _count_value(result, COUNT_ACTIVITY_CODE, state)
    expected_total = sum(state_counts.values())
    if expected_total > max_records:
        raise DenueAcquisitionError("DENUE scope exceeds the configured record limit")

    records: list[dict[str, Any]] = []
    pages: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for state in states:
        state_start = len(records)
        state_limit = state_counts[state]
        for activity in ACTIVITY_CODES:
            for start in range(1, state_limit + 1, page_size):
                end = min(start + page_size - 1, state_limit)
                page = _detail_page_records(query(_page_path(state, activity, start, end)))
                if len(page) > end - start + 1:
                    raise DenueAcquisitionError("DENUE page count or schema did not match the bounded request")
                for row in page:
                    identifier = str(row.get("Id", "")).strip()
                    class_id = str(row.get("CLASE_ACTIVIDAD_ID", "")).strip()
                    area = str(row.get("AreaGeo", "")).strip()
                    if not identifier or class_id != activity:
                        raise DenueAcquisitionError("DENUE page contained a record outside its requested identifier/class scope")
                    if not re.fullmatch(r"\d{9}", area) or not area.startswith(state):
                        raise DenueAcquisitionError("DENUE page contained a record outside its requested state scope")
                    if identifier in seen_ids:
                        raise DenueAcquisitionError("DENUE page repeated an establishment identifier")
                    seen_ids.add(identifier)
                # Retain the source fields needed for facility identity and
                # review, excluding unnecessary phone/email/web contact data.
                records.extend({key: row[key] for key in SOURCE_FIELDS if key in row}
                               for row in page)
                pages.append({"activity_code": activity, "state_code": state,
                              "from": start, "to": end, "records": len(page)})
                if len(page) < end - start + 1:
                    break
        if len(records) - state_start != state_limit:
            raise DenueAcquisitionError("DENUE state results did not reconcile with the documented subrama count")
    if len(records) != expected_total:
        raise DenueAcquisitionError("DENUE results did not reconcile with preflight counts")

    retrieved = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    payload = {
        "source_id": SOURCE_ID,
        "schema_version": "denue-api-v1",
        "source_url": API_BASE,
        "retrieved_at_utc": retrieved,
        "activity_codes": list(ACTIVITY_CODES),
        "states": list(states),
        "preflight_counts": [
            {"activity_code": COUNT_ACTIVITY_CODE, "state_code": state,
             "count": state_counts[state], "scope": "SCIAN subrama"}
            for state in states
        ],
        "pages": pages,
        "records": records,
    }
    artifact_bytes = (json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                 separators=(",", ":")) + "\n").encode("utf-8")
    if len(artifact_bytes) > max_bytes:
        raise DenueAcquisitionError("preserved DENUE artifact exceeded the byte limit")
    path = Path(output_root) / "raw" / "denue-api.json"
    atomic_bytes(path, artifact_bytes)
    return {
        "source_id": SOURCE_ID,
        "source_url": API_BASE,
        "retrieved_at_utc": retrieved,
        "artifact_path": str(path),
        "sha256": hashlib.sha256(artifact_bytes).hexdigest(),
        "byte_size": len(artifact_bytes),
        "input_rows": len(records),
        "request_count": requests,
        "response_bytes": response_bytes,
        "preflight_rows": expected_total,
        "activity_counts": {COUNT_ACTIVITY_CODE: expected_total},
    }
