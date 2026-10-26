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
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

FINDER_URL = "https://rgsa-web-aesan.mscbs.es/rgsa/formulario_principal_js.jsp"
FINDER_HOST = "rgsa-web-aesan.mscbs.es"
MAX_LOOKUPS = 24
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
DEFAULT_REQUEST_INTERVAL_SECONDS = 1.0
MAX_FORM_BYTES = 1 * 1024 * 1024
SOURCE_ID = "es.locations"
LOOKUP_SOURCE_ID = "es.locations.aesan-rgseaa-public-finder"
LOOKUP_METHOD_VERSION = "es-aesan-rgseaa-locality-v1"


class UnsupportedAesanProvinceError(ValueError):
    """The source label has no unique equivalent in AESAN's published province dropdown."""

    def __init__(self, message: str, *, response_bytes: int) -> None:
        super().__init__(message)
        # The ordinary form page was read before inspecting its options.
        self.http_requests = 1
        self.response_bytes = response_bytes


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
    payload = response.read(MAX_RESPONSE_BYTES + 1)
    if len(payload) > MAX_RESPONSE_BYTES:
        raise ValueError("AESAN finder response exceeded the 2 MiB limit")
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


class _SearchFormParser(html.parser.HTMLParser):
    """Parse ordinary AESAN search and result forms, including select options."""
    def __init__(self) -> None:
        super().__init__()
        self.forms: list[dict[str, Any]] = []
        self.form: dict[str, Any] | None = None
        self.select: dict[str, Any] | None = None
        self.option: dict[str, Any] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs = dict(attrs)
        if tag == "form":
            self.form = {"action": attrs.get("action", ""), "method": attrs.get("method", "get"),
                         "fields": []}
            self.forms.append(self.form)
        elif tag == "input" and self.form is not None and attrs.get("name"):
            self.form["fields"].append({"name": attrs["name"], "value": attrs.get("value", ""),
                                        "type": attrs.get("type", ""), "checked": "checked" in attrs})
        elif tag == "select" and self.form is not None and attrs.get("name"):
            self.select = {"name": attrs["name"], "value": "", "options": []}
            self.form["fields"].append(self.select)
        elif tag == "option" and self.select is not None:
            self.option = {"value": attrs.get("value", ""), "text": "", "selected": "selected" in attrs}

    def handle_data(self, data: str) -> None:
        if self.option is not None:
            self.option["text"] += data

    def handle_endtag(self, tag: str) -> None:
        if tag == "option" and self.option is not None and self.select is not None:
            self.select["options"].append(self.option)
            if self.option["selected"]:
                self.select["value"] = self.option["value"]
            self.option = None
        elif tag == "select":
            self.select = None
        elif tag == "form":
            self.form = None


class _VisibleTextParser(html.parser.HTMLParser):
    """Extract visible page copy for recognizing an explicitly empty result."""
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def _explicit_empty_search_result(payload: bytes, charset: str | None) -> bool:
    parser = _VisibleTextParser()
    parser.feed(payload.decode(charset or "utf-8", "replace"))
    visible = _fold(" ".join(parser.parts))
    # Deliberately a small allowlist: a missing/changed export form is not
    # treated as zero rows unless AESAN explicitly says the search was empty.
    return any(message in visible for message in (
        "no se han encontrado resultados", "no se encontraron resultados",
        "no se ha encontrado ningun resultado", "no se encontro ningun resultado",
        "no existen resultados", "no hay resultados",
    ))


def _province_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", _fold(value))


_PROVINCE_ALIASES = (
    {"acoruna", "lacoruna", "coruna", "corunaa"}, {"alava", "araba", "arabaalava"}, {"bizkaia", "vizcaya"},
    {"gipuzkoa", "guipuzcoa"}, {"girona", "gerona"}, {"lleida", "lerida"},
    {"illesbalears", "baleares", "islasbaleares"},
    {"valencia", "valenciavalencia"},
    {"castellon", "castello", "castelloncastello"},
    {"alicante", "alacant", "alicantealacant"},
    {"ourense", "orense"},
    # AESAN spells these provinces with an article-order inversion in its
    # published dropdown ("Rioja, La" and "Palmas, Las"). Navarra's source
    # workbook uses its official coextensive one-province community name.
    {"larioja", "riojala"},
    {"laspalmas", "palmaslas"},
    {"navarra", "comunidadforaldenavarra"},
)


def same_official_province(left: str, right: str) -> bool:
    """Compare known official Spanish/Castilian province-name equivalents only."""
    return official_province_key(left) == official_province_key(right)


def official_province_key(value: str) -> str:
    """Return a stable key across only the explicit official province aliases."""
    key = _province_key(value)
    aliases = next((group for group in _PROVINCE_ALIASES if key in group), None)
    return min(aliases) if aliases else key


def _read_bounded(response: Any, limit: int) -> bytes:
    payload = response.read(limit + 1)
    if len(payload) > limit:
        raise ValueError("AESAN finder response exceeded the configured byte limit")
    return payload


def _select_option(field: dict[str, Any], wanted_value: str | None = None,
                   wanted_label: str | None = None) -> str:
    options = field.get("options", [])
    matches = [option for option in options
               if ((wanted_value is not None and option.get("value") == wanted_value)
                   or (wanted_label is not None and _province_key(option.get("text", ""))
                       == _province_key(wanted_label)))]
    if len(matches) != 1:
        raise ValueError("AESAN published search option missing or ambiguous")
    return str(matches[0].get("value", ""))


def fetch_filtered_export(province: str, sector: str, *, opener: Any | None = None,
                          request_interval_seconds: float = DEFAULT_REQUEST_INTERVAL_SECONDS,
                          retain_raw_export: bool = False
                          ) -> dict[str, Any]:
    """Use AESAN's regular province/sector form and its published Excel button.

    The result workbook is returned only as minimized location rows; the response
    body is bounded and never persisted. Registration-number search stays blank.
    """
    if not isinstance(province, str) or not province.strip() or "," in province:
        raise ValueError("AESAN bulk-search province invalid")
    if not re.fullmatch(r"\d{1,2}", str(sector)):
        raise ValueError("AESAN bulk-search sector invalid")
    if not 0 <= request_interval_seconds <= 60:
        raise ValueError("AESAN request interval must be between 0 and 60 seconds")
    jar = http.cookiejar.CookieJar()
    client = opener or urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    page_request = urllib.request.Request(FINDER_URL,
        headers={"User-Agent": "UntilEveryCage/2 AESAN source verification"})
    with client.open(page_request, timeout=30) as response:
        page_bytes = _read_bounded(response, MAX_FORM_BYTES)
        page_url = response.geturl()
        page_charset = response.headers.get_content_charset() if getattr(response, "headers", None) else None
    if urllib.parse.urlparse(page_url).hostname != FINDER_HOST:
        raise ValueError("AESAN public finder redirected outside its official host")
    form_parser = _SearchFormParser()
    form_parser.feed(page_bytes.decode(page_charset or "utf-8", "replace"))
    form = next((item for item in form_parser.forms
                 if {field.get("name") for field in item["fields"]}.issuperset(
                     {"numero1", "numero2", "numero3", "clave", "provincia"})), None)
    if form is None or form.get("method", "").lower() != "post":
        raise ValueError("AESAN published search form contract changed")
    fields: dict[str, str] = {}
    for field in form["fields"]:
        name = field.get("name")
        if not name:
            continue
        if "options" in field:
            fields[name] = str(field.get("value", ""))
        elif field.get("type") not in {"checkbox", "submit", "button", "reset"}:
            fields[name] = str(field.get("value", ""))
    province_field = next(field for field in form["fields"] if field.get("name") == "provincia")
    province_options = [option for option in province_field.get("options", [])
                        if same_official_province(option.get("text", ""), province)]
    if len(province_options) != 1:
        raise UnsupportedAesanProvinceError(
            "AESAN province has no unique supported official option",
            response_bytes=len(page_bytes))
    sector_field = next(field for field in form["fields"] if field.get("name") == "clave")
    fields["provincia"] = str(province_options[0].get("value", ""))
    fields["clave"] = _select_option(sector_field, wanted_value=str(sector))
    fields.update({"numero1": "", "numero2": "", "numero3": ""})
    buscar = next((field for field in form["fields"] if field.get("name") == "Buscar"), None)
    if buscar is None:
        raise ValueError("AESAN search submit control missing")
    fields["Buscar"] = str(buscar.get("value") or "Buscar")
    action = urllib.parse.urljoin(page_url, form["action"])
    if urllib.parse.urlparse(action).hostname != FINDER_HOST:
        raise ValueError("AESAN public finder form action is outside its official host")
    request_headers = {"User-Agent": "UntilEveryCage/2 AESAN source verification",
                       "Referer": page_url, "Origin": f"https://{FINDER_HOST}",
                       "Content-Type": "application/x-www-form-urlencoded"}
    search_request = urllib.request.Request(action, data=urllib.parse.urlencode(fields).encode("utf-8"),
                                           headers=request_headers)
    if request_interval_seconds:
        time.sleep(request_interval_seconds)
    with client.open(search_request, timeout=45) as response:
        result_page_bytes = _read_bounded(response, MAX_FORM_BYTES)
        result_page_url = response.geturl()
        result_charset = response.headers.get_content_charset() if getattr(response, "headers", None) else None
    if urllib.parse.urlparse(result_page_url).hostname != FINDER_HOST:
        raise ValueError("AESAN search result redirected outside its official host")
    result_parser = _SearchFormParser()
    result_parser.feed(result_page_bytes.decode(result_charset or "utf-8", "replace"))
    export_form = next((item for item in result_parser.forms
                        if any(field.get("name") == "excel" and field.get("type") == "submit"
                               for field in item["fields"])), None)
    if export_form is None:
        if _explicit_empty_search_result(result_page_bytes, result_charset):
            response_sha256 = hashlib.sha256(result_page_bytes).hexdigest()
            return {"results": [], "result_url": result_page_url,
                    "request_url": action,
                    "retrieved_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                    "response_bytes": len(result_page_bytes), "content_type": "text/html",
                    "response_sha256": response_sha256,
                    "result_page_sha256": response_sha256,
                    "response_kind": "explicit_empty_result_page",
                    "query_province": province, "query_sector": str(sector),
                    "query_province_option": str(province_options[0].get("text", "")).strip(),
                    "query_province_option_value": str(province_options[0].get("value", "")),
                    "http_requests": 2, "explicit_zero_results": True}
        raise ValueError("AESAN published Excel export control missing")
    export_fields = {}
    for field in export_form["fields"]:
        name = field.get("name")
        if (name and not name.isdigit() and name not in {"regresar", "excel"}
                and "options" not in field):
            export_fields[name] = str(field.get("value", ""))
    excel = next(field for field in export_form["fields"] if field.get("name") == "excel")
    export_fields["excel"] = str(excel.get("value") or "Excel")
    export_action = urllib.parse.urljoin(result_page_url, export_form["action"])
    if urllib.parse.urlparse(export_action).hostname != FINDER_HOST:
        raise ValueError("AESAN export form action is outside its official host")
    if request_interval_seconds:
        time.sleep(request_interval_seconds)
    export_request = urllib.request.Request(export_action,
        data=urllib.parse.urlencode(export_fields).encode("utf-8"), headers={**request_headers,
            "Referer": result_page_url})
    with client.open(export_request, timeout=60) as response:
        export_bytes = _read_bounded(response, MAX_RESPONSE_BYTES)
        export_url = response.geturl()
        content_type = (response.headers.get("Content-Type", "") if getattr(response, "headers", None) else "")
        export_charset = response.headers.get_content_charset() if getattr(response, "headers", None) else None
    parsed_url = urllib.parse.urlparse(export_url)
    if parsed_url.hostname != FINDER_HOST or parsed_url.path != "/rgsa/resultado_principal_excel.jsp":
        raise ValueError("AESAN export response route changed")
    if "excel" not in content_type.casefold() and "spreadsheet" not in content_type.casefold():
        raise ValueError("AESAN published export response type changed")
    text = export_bytes.decode(export_charset or "iso-8859-1", "replace")
    results = parse_official_results(text)
    result = {"results": results, "result_url": export_url, "request_url": action,
              "retrieved_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
              "response_bytes": len(export_bytes), "content_type": content_type,
              "response_sha256": hashlib.sha256(export_bytes).hexdigest(),
              "result_page_sha256": hashlib.sha256(result_page_bytes).hexdigest(),
              "response_kind": "official_excel_export",
              "query_province": province, "query_sector": str(sector),
              "query_province_option": str(province_options[0].get("text", "")).strip(),
              "query_province_option_value": str(province_options[0].get("value", "")),
              "http_requests": 3, "explicit_zero_results": False}
    if retain_raw_export:
        # The cohort worker writes this bounded response only beneath its
        # approved private artifact root; callers otherwise receive metadata.
        result["_raw_export_bytes"] = export_bytes
    return result


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
    if not source_province or not result.get("province") or not same_official_province(source_province, result["province"]):
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


def fetch_registration_results(registration_keys: Iterable[str], *, opener: Any | None = None,
                               request_interval_seconds: float = DEFAULT_REQUEST_INTERVAL_SECONDS) -> list[dict[str, Any]]:
    """Query one small batch through AESAN's ordinary form, pacing POST requests."""
    keys = list(registration_keys)
    if not 1 <= len(keys) <= MAX_LOOKUPS:
        raise ValueError(f"AESAN lookup batch must contain 1..{MAX_LOOKUPS} registration keys")
    if any(registration_components(key) is None for key in keys):
        raise ValueError("AESAN lookup contains an invalid registration key")
    if not 0 <= request_interval_seconds <= 60:
        raise ValueError("AESAN request interval must be between 0 and 60 seconds")
    cookie_jar = http.cookiejar.CookieJar()
    client = opener or urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))
    page_url, form, action = _fetch_form(client)
    # The published form expects every ordinary text/select control in the POST,
    # including empty controls. The unchecked feed checkbox and Clear button are
    # intentionally absent; Buscar is the submitted button.
    template = {name: value for name, value, _ in form["fields"]
                if name not in {"check_autorizaciones", "Limpiar", "Buscar"}}
    events: list[dict[str, Any]] = []
    for index, key in enumerate(keys):
        if index:
            time.sleep(request_interval_seconds)
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
                   lookup: Any = fetch_registration_results,
                   request_interval_seconds: float = DEFAULT_REQUEST_INTERVAL_SECONDS) -> list[dict[str, Any]]:
    """Run a resumable-cohort slice in network batches of at most 24 keys."""
    if not 1 <= limit <= 10000:
        raise ValueError("AESAN enrichment limit must be between 1 and 10000")
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
    events = []
    for start in range(0, len(selected), MAX_LOOKUPS):
        batch_records = selected[start:start + MAX_LOOKUPS]
        batch_keys = keys[start:start + MAX_LOOKUPS]
        if lookup is fetch_registration_results:
            responses = lookup(batch_keys, request_interval_seconds=request_interval_seconds)
        else:
            responses = lookup(batch_keys)
        if len(responses) != len(batch_records):
            raise ValueError("AESAN lookup response count does not match requested records")
        for record, response in zip(batch_records, responses):
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
