"""Bounded resolver/acquisition for the public Scottish Government WFS."""
from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from pipeline.common.acquisition import AcquisitionError, fetch_source
from pipeline.contracts.source_lifecycle import atomic_json

from .adapter import (
    ADAPTER_VERSION, ATTRIBUTION, CATALOG_URL, COVERAGE, LICENSE, LICENSE_URL, SCHEMA_VERSION,
    SOURCE_ID, parse_geojson,
)

DATA_HOST = "msmap1.atkinsgeospatial.com"
CATALOG_HOST = "www.data.gov.uk"
MAX_CATALOG_BYTES = 8 * 1024 * 1024
DEFAULT_MAX_BYTES = 32 * 1024 * 1024


class ScotlandAcquisitionError(ValueError):
    """A source response or catalog contract failed closed."""


def _tls_context() -> ssl.SSLContext:
    """Use the platform trust store while retaining TLS verification."""
    try:
        import truststore
    except ImportError as error:
        raise ScotlandAcquisitionError("platform TLS truststore dependency is unavailable") from error
    context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    if context.verify_mode != ssl.CERT_REQUIRED or not context.check_hostname:
        raise ScotlandAcquisitionError("platform TLS context does not enforce certificate and hostname verification")
    return context


class _Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "a":
            href = dict(attrs).get("href")
            if href:
                self.hrefs.append(href)


def _validate_https_host(url: str, host: str) -> None:
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme != "https" or parsed.hostname != host or parsed.username
            or parsed.password or parsed.fragment):
        raise ScotlandAcquisitionError("request escaped an approved official-source HTTPS host")


def discover_download_url(*, timeout_seconds: float = 30.0, opener: Any = None) -> str:
    """Resolve the publisher's current WFS link; never store its token in code."""
    _validate_https_host(CATALOG_URL, CATALOG_HOST)
    request = urllib.request.Request(CATALOG_URL, headers={"Accept": "text/html"})
    try:
        response = (opener or urllib.request).urlopen(
            request, timeout=timeout_seconds,
            **({} if opener is not None else {"context": _tls_context()}),
        )
    except (urllib.error.URLError, OSError) as error:
        raise ScotlandAcquisitionError("official catalog could not be retrieved") from error
    with response:
        if not 200 <= response.status < 300:
            raise ScotlandAcquisitionError(f"official catalog returned HTTP {response.status}")
        content_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
        if content_type not in {"text/html", "application/xhtml+xml"}:
            raise ScotlandAcquisitionError("official catalog response was not HTML")
        content = response.read(MAX_CATALOG_BYTES + 1)
        if len(content) > MAX_CATALOG_BYTES:
            raise ScotlandAcquisitionError("official catalog exceeded the bounded response size")
    try:
        html = content.decode("utf-8-sig", errors="strict")
    except UnicodeDecodeError as error:
        raise ScotlandAcquisitionError("official catalog encoding changed") from error
    parser = _Links()
    parser.feed(html)
    candidates: list[str] = []
    for href in parser.hrefs:
        url = urllib.parse.urljoin(CATALOG_URL, href)
        parts = urllib.parse.urlsplit(url)
        if parts.hostname != DATA_HOST or parts.path != "/geoserver/nmpwfs/ows":
            continue
        query = urllib.parse.parse_qs(parts.query, keep_blank_values=True)
        if (query.get("service", [""])[0].lower() == "wfs"
                and query.get("request", [""])[0].lower() == "getfeature"
                and query.get("typename", query.get("typeName", [""]))[0].lower() == "nmpwfs:aquaculture_sites"
                and query.get("token", [""])[0]):
            candidates.append(url)
    if len(set(candidates)) != 1:
        raise ScotlandAcquisitionError("catalog no longer exposes one unambiguous aquaculture-sites WFS link")
    return _json_query_url(candidates[0])


def _json_query_url(url: str) -> str:
    _validate_https_host(url, DATA_HOST)
    parts = urllib.parse.urlsplit(url)
    values = urllib.parse.parse_qs(parts.query, keep_blank_values=True)
    values.update({"outputFormat": ["application/json"], "srsName": ["EPSG:4326"]})
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path,
                                    urllib.parse.urlencode(values, doseq=True), ""))


def _redact_token(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    values = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
    safe = [(key, value) for key, value in values if key.lower() != "token"]
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path,
                                    urllib.parse.urlencode(safe), ""))


def _artifact_validator(path: Path, _headers: dict[str, str]) -> None:
    try:
        parse_geojson(path.read_bytes())
    except (ValueError, KeyError, TypeError) as error:
        # fetch_source only writes failure evidence and removes its temporary
        # download for acquisition-contract failures. Do not let malformed or
        # incomplete WFS envelopes escape that fail-closed path.
        raise AcquisitionError("official WFS GeoJSON failed envelope/count validation",
                               failure_class="source-validation",
                               action="inspect the bounded response privately; retry only after the publisher response is reviewed") from error


def _terms(path: Path) -> None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ScotlandAcquisitionError("source terms review could not be read") from error
    if (not isinstance(value, dict) or value.get("source_id") != SOURCE_ID
            or value.get("decision") != "approved" or value.get("license") != LICENSE
            or value.get("private_preview_only") is not True):
        raise ScotlandAcquisitionError("terms review must approve this exact OGL source for private preview only")


def fetch(*, output_root: Path, run_id: str, terms_review_path: Path,
          timeout_seconds: float = 60.0, max_bytes: int = DEFAULT_MAX_BYTES,
          opener: Any = None) -> dict[str, Any]:
    _terms(terms_review_path)
    url = discover_download_url(timeout_seconds=timeout_seconds, opener=opener)
    # The resolver follows only a link printed on the publisher's public
    # catalog. fetch_source retains the exact endpoint privately in staging;
    # callers and reports use CATALOG_URL so bearer-like query data is never
    # copied into tracked metadata or console output.
    metadata = fetch_source(
        source_id=SOURCE_ID, url=url, output_root=output_root,
        artifact_name="aquaculture-sites.geojson", run_id=run_id,
        terms_review_path=terms_review_path, timeout_seconds=timeout_seconds,
        max_bytes=max_bytes,
        allowed_content_types=("application/json", "application/geo+json", "text/plain", "application/octet-stream"),
        code_version=ADAPTER_VERSION, config_version=SCHEMA_VERSION,
        coverage=COVERAGE,
        rights_caveat=f"{LICENSE}; {ATTRIBUTION}",
        privacy_caveat="private staging; source location precision and publication eligibility require separate review",
        artifact_validator=_artifact_validator,
        ssl_context=_tls_context(),
    )
    document = parse_geojson(Path(metadata["artifact_path"]).read_bytes())
    metadata["effective_date"] = document["timeStamp"]
    metadata["source_timestamp_utc"] = document["timeStamp"]
    atomic_json(Path(metadata["artifact_path"]).parent / "acquisition-metadata.json", metadata)
    # fetch_source's canonical acquisition-metadata.json retains the exact
    # token-bearing URL privately for audit; never pass it to shared runner
    # manifests, terminal output, or tracked metadata.
    safe = dict(metadata)
    safe["source_url"] = CATALOG_URL
    safe["requested_url"] = CATALOG_URL
    safe["final_url"] = CATALOG_URL
    safe["resource_url_redacted"] = _redact_token(url)
    safe["effective_date"] = document["timeStamp"]
    safe["source_timestamp_utc"] = document["timeStamp"]
    safe["redirects"] = []
    safe["attempts"] = [{key: value for key, value in attempt.items() if key != "redirects"}
                        for attempt in metadata.get("attempts", [])]
    return safe
