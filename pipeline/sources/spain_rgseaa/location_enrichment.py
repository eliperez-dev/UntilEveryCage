"""Bounded private enrichment from AESAN's public RGSEAA search results."""
from __future__ import annotations

import html.parser
import hashlib
import json
import os
import re
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import http.cookiejar
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

FINDER_URL = "https://rgsa-web-aesan.mscbs.es/rgsa/formulario_principal_js.jsp"
FINDER_HOST = "rgsa-web-aesan.mscbs.es"
MAX_LOOKUPS = 24
SOURCE_ID = "es.locations"
LOOKUP_SOURCE_ID = "es.locations.aesan-rgseaa-public-finder"
LOOKUP_METHOD_VERSION = "es-aesan-rgseaa-locality-v1"


def _fold(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    return " ".join("".join(ch for ch in decomposed if not unicodedata.combining(ch)).split())


def registration_components(value: str) -> tuple[str, str, str] | None:
    """Return AESAN's documented sector, serial and territorial components."""
    if not isinstance(value, str):
        return None
    match = re.fullmatch(r"\s*(\d{1,2})\s*[.\-/]\s*(\d{1,6})(?:\s*/\s*([A-Za-z]{1,2}))?\s*", value)
    if not match:
        return None
    return (str(int(match.group(1))), str(int(match.group(2))), (match.group(3) or "").upper())


def registration_key_sha256(value: str) -> str | None:
    """Hash canonical AESAN key components so the registration is not copied into map provenance."""
    components = registration_components(value)
    if components is None:
        return None
    return hashlib.sha256("\x1f".join(components).encode("ascii")).hexdigest()


def _decode_response(response: Any) -> str:
    payload = response.read()
    headers = getattr(response, "headers", None)
    charset = headers.get_content_charset() if headers is not None and hasattr(headers, "get_content_charset") else None
    try:
        return payload.decode(charset or "utf-8")
    except (LookupError, UnicodeDecodeError):
        return payload.decode("utf-8", "replace")


class _FormParser(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.forms: list[dict[str, Any]] = []
        self.current: dict[str, Any] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs = dict(attrs)
        if tag == "form":
            self.current = {"action": attrs.get("action", ""), "method": attrs.get("method", "get").lower(), "fields": []}
            self.forms.append(self.current)
        elif tag in {"input", "select", "textarea"} and self.current is not None and attrs.get("name"):
            self.current["fields"].append((attrs["name"], attrs.get("value", ""), attrs.get("type", "")))

    def handle_endtag(self, tag: str) -> None:
        if tag == "form":
            self.current = None


class _TableParser(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self.table: list[list[str]] | None = None
        self.row: list[str] | None = None
        self.cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            self.table = []
        elif tag == "tr" and self.table is not None:
            self.row = []
        elif tag in {"td", "th"} and self.row is not None:
            self.cell = []

    def handle_data(self, data: str) -> None:
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self.cell is not None and self.row is not None:
            self.row.append(" ".join("".join(self.cell).split()))
            self.cell = None
        elif tag == "tr" and self.row is not None and self.table is not None:
            if self.row:
                self.table.append(self.row)
            self.row = None
        elif tag == "table" and self.table is not None:
            self.tables.append(self.table)
            self.table = None


def parse_official_results(document: str) -> list[dict[str, str]]:
    """Extract only registration key, industrial address, locality and province."""
    parser = _TableParser()
    parser.feed(document)
    output: list[dict[str, str]] = []
    for table in parser.tables:
        for header_row in table:
            headers = [_fold(cell) for cell in header_row]
            def locate(*terms: str) -> int | None:
                return next((i for i, header in enumerate(headers) if all(term in header for term in terms)), None)
            def first_index(*choices: int | None) -> int | None:
                return next((choice for choice in choices if choice is not None), None)
            reg_i = first_index(locate("rgseaa"), locate("registration number"))
            locality_i = first_index(locate("localidad"), locate("town"))
            province_i = first_index(locate("provincia"), locate("province"))
            address_i = first_index(locate("dom", "indl"), locate("physicaladress"), locate("address"))
            if None in (reg_i, locality_i, province_i, address_i):
                continue
            start = table.index(header_row) + 1
            for row in table[start:]:
                if max(reg_i, locality_i, province_i, address_i) >= len(row):
                    continue
                registration = row[reg_i].strip()
                if registration_components(registration) is None:
                    continue
                output.append({"registration": registration, "address": row[address_i].strip(),
                               "municipality": row[locality_i].strip(), "province": row[province_i].strip()})
            break
    return output


def match_official_result(record: dict[str, Any], results: Iterable[dict[str, str]], *,
                          retrieved_at: str, result_url: str,
                          request_url: str | None = None) -> dict[str, Any]:
    """Create an append-only private evidence event for an exact source key."""
    normalized = record.get("normalized") or {}
    source_values = record.get("source_values") or {}
    source_key = source_values.get("N_RGSEAA") or normalized.get("establishment_id")
    source_parts = registration_components(source_key)
    base = {"event_type": "official_locality_lookup", "source_id": SOURCE_ID,
            "source_record_key": record.get("source_record_key"), "source_url": result_url,
            "request_url": request_url or FINDER_URL, "retrieved_at": retrieved_at,
            "method_source_id": LOOKUP_SOURCE_ID, "method_version": LOOKUP_METHOD_VERSION}
    if not source_parts:
        return {**base, "outcome": "invalid_source_registration_key"}
    base["registration_key_sha256"] = hashlib.sha256("\x1f".join(source_parts).encode("ascii")).hexdigest()
    matches = [item for item in results if registration_components(item.get("registration", "")) == source_parts]
    if not matches:
        return {**base, "outcome": "not_found"}
    if len(matches) != 1:
        return {**base, "outcome": "ambiguous_exact_registration"}
    result = matches[0]
    source_province = normalized.get("province") or source_values.get("Provincia") or ""
    if not source_province or not result.get("province") or _fold(source_province) != _fold(result["province"]):
        return {**base, "outcome": "province_conflict"}
    if not result.get("municipality", "").strip():
        return {**base, "outcome": "municipality_missing"}
    return {**base, "outcome": "matched", "location_evidence_addition": {
        "municipality": result["municipality"].strip(), "city": result["municipality"].strip(),
        "province": result["province"].strip(), "precision": "municipality",
        "source_id": LOOKUP_SOURCE_ID, "source_url": result_url,
        "retrieved_at": retrieved_at, "match_method": "exact_rgseaa_components_and_province"}}


def _fetch_form(opener: Any) -> tuple[str, dict[str, Any], str]:
    request = urllib.request.Request(FINDER_URL, headers={"User-Agent": "UntilEveryCage/2 AESAN source verification"})
    with opener.open(request, timeout=30) as response:
        page = _decode_response(response)
        page_url = response.geturl()
    if urllib.parse.urlparse(page_url).hostname != FINDER_HOST:
        raise ValueError("AESAN public finder redirected outside its official host")
    parser = _FormParser()
    parser.feed(page)
    form = next((item for item in parser.forms if {"numero1", "numero2", "numero3"}.issubset({f[0] for f in item["fields"]})), None)
    if form is None:
        raise ValueError("AESAN public finder registration fields changed")
    action = urllib.parse.urljoin(page_url, form["action"])
    if urllib.parse.urlparse(action).hostname != FINDER_HOST or form["method"] != "post":
        raise ValueError("AESAN public finder request contract changed")
    return page_url, form, action


def fetch_registration_results(registration_keys: Iterable[str], *, opener: Any | None = None) -> list[dict[str, Any]]:
    """Query at most 24 registration keys using AESAN's ordinary form workflow."""
    keys = list(registration_keys)
    if not 1 <= len(keys) <= MAX_LOOKUPS:
        raise ValueError(f"AESAN lookup batch must contain 1..{MAX_LOOKUPS} registration keys")
    if any(registration_components(key) is None for key in keys):
        raise ValueError("AESAN lookup contains an invalid registration key")
    cookie_jar = http.cookiejar.CookieJar()
    client = opener or urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))
    page_url, form, action = _fetch_form(client)
    # The published form expects every ordinary text/select control in the POST,
    # including empty controls. The unchecked feed checkbox and Clear button are
    # intentionally absent; Buscar is the submitted button.
    template = {name: value for name, value, _ in form["fields"]
                if name not in {"check_autorizaciones", "Limpiar", "Buscar"}}
    events: list[dict[str, Any]] = []
    for key in keys:
        sector, serial, territory = registration_components(key)  # type: ignore[misc]
        params = dict(template)
        params.update({"numero1": sector, "numero2": serial, "numero3": territory})
        params["Buscar"] = next((value for name, value, _ in form["fields"] if name == "Buscar" and value), "Buscar")
        request = urllib.request.Request(action, data=urllib.parse.urlencode(params).encode("utf-8"),
            headers={"User-Agent": "UntilEveryCage/2 AESAN source verification", "Referer": page_url,
                     "Origin": f"{urllib.parse.urlparse(page_url).scheme}://{FINDER_HOST}",
                     "Content-Type": "application/x-www-form-urlencoded"})
        try:
            with client.open(request, timeout=30) as response:
                html = _decode_response(response)
                response_url = response.geturl()
            if urllib.parse.urlparse(response_url).hostname != FINDER_HOST:
                raise ValueError("AESAN public finder result redirected outside its official host")
        except urllib.error.HTTPError as error:
            raise RuntimeError(f"AESAN finder returned HTTP {error.code}") from error
        results = parse_official_results(html)
        events.append({"results": results, "result_url": response_url, "request_url": action,
                       "retrieved_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")})
    return events


def enrich_records(records: Iterable[dict[str, Any]], *, limit: int = 1,
                   lookup: Any = fetch_registration_results) -> list[dict[str, Any]]:
    """Run the bounded source-key lookup and return new immutable evidence events."""
    if not 1 <= limit <= MAX_LOOKUPS:
        raise ValueError(f"AESAN enrichment limit must be 1..{MAX_LOOKUPS}")
    representatives: dict[str, dict[str, Any]] = {}
    for record in records:
        if record.get("source_id") != SOURCE_ID:
            continue
        normalized = record.get("normalized") or {}
        if not isinstance(normalized.get("address"), str) or not normalized["address"].strip():
            continue
        values = record.get("source_values") or {}
        key = values.get("N_RGSEAA") or normalized.get("establishment_id")
        key_hash = registration_key_sha256(key) if isinstance(key, str) else None
        record_key = record.get("source_record_key")
        if key_hash is None or not isinstance(record_key, str) or not record_key:
            continue
        current = representatives.get(key_hash)
        if current is None or record_key < current["source_record_key"]:
            representatives[key_hash] = record
    # The real-preview candidate groups duplicate source rows by the AESAN
    # registration number and selects the lexicographically first row key.
    # Use the same representative rule so each lookup can link to exactly one
    # accepted candidate without attaching a duplicate row's address.
    selected = list(representatives.values())[:limit]
    keys = []
    for record in selected:
        values = record.get("source_values") or {}
        normalized = record.get("normalized") or {}
        key = values.get("N_RGSEAA") or normalized.get("establishment_id")
        if registration_components(key) is None:
            raise ValueError("AESAN enrichment record lacks a valid source registration key")
        keys.append(key)
    responses = lookup(keys) if keys else []
    if len(responses) != len(selected):
        raise ValueError("AESAN lookup response count does not match requested records")
    events = []
    for record, response in zip(selected, responses):
        events.append(match_official_result(record, response.get("results", []),
            retrieved_at=response["retrieved_at"], result_url=response["result_url"],
            request_url=response.get("request_url")))
    return events


def query_with_verified_municipality(record: dict[str, Any], event: dict[str, Any]) -> str | None:
    """Build a fresh full-address query with verified locality context, preserving source evidence."""
    if event.get("outcome") != "matched":
        return None
    from pipeline.geocoding.source_queue import source_geocode_query
    normalized = dict(record.get("normalized") or {})
    private_location = dict(normalized.get("private_location_evidence") or {})
    addition = event["location_evidence_addition"]
    private_location.update({k: addition[k] for k in ("municipality", "city", "province")})
    normalized["private_location_evidence"] = private_location
    # The original normalized/source address is not replaced; the new query is derived only.
    return source_geocode_query({"normalized": normalized, "source_values": {}})


def append_private_events(path: str | Path, events: Iterable[dict[str, Any]]) -> int:
    """Append only minimized provenance events; never rewrite earlier lookup evidence."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    batch = list(events)
    for event in batch:
        if event.get("event_type") != "official_locality_lookup":
            raise ValueError("only AESAN locality lookup events may be appended")
        if any(key in event for key in ("name", "business_name", "address", "registration_key")):
            raise ValueError("private lookup event contains a disallowed raw field")
    count = 0
    with target.open("a", encoding="utf-8", newline="\n") as stream:
        for event in batch:
            stream.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
            count += 1
        stream.flush()
        os.fsync(stream.fileno())
    return count
