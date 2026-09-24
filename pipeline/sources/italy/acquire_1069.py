"""Bounded live acquisition for the Ministry's separate Regulation 1069 feed."""
from __future__ import annotations

import hashlib
import html.parser
import json
import re
import urllib.parse
from pathlib import Path
from typing import Any

from pipeline.contracts.source_lifecycle import atomic_json
from . import acquire as transport

SOURCE_ID = "it.1069-2009"
ACQUISITION_VERSION = "it-1069-acquisition-v1"
CATALOG_URL = "https://www.dati.salute.gov.it/it/dataset/stabilimenti-italiani-i-sottoprodotti-di-origine-animale/"
CATALOG_HOST = "www.dati.salute.gov.it"
CSV_LINK = re.compile(r"^/sites/default/files/opendata/STAB_SPOA_9_(?P<date>\d{8})\.csv$", re.I)
SAFE_TYPES = {"text/csv", "application/csv", "application/octet-stream", "text/plain"}


class _Links(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "a":
            href = dict(attrs).get("href")
            if href:
                self.hrefs.append(href)


def discover_csv(catalog_bytes: bytes, catalog_url: str = CATALOG_URL) -> tuple[str, str]:
    parser = _Links()
    parser.feed(catalog_bytes.decode("utf-8", errors="strict"))
    catalog = urllib.parse.urlparse(catalog_url)
    if catalog.scheme != "https" or catalog.hostname != CATALOG_HOST:
        raise transport.AcquisitionError("1069 catalog URL is outside the Ministry HTTPS host")
    matches = []
    for href in parser.hrefs:
        parsed = urllib.parse.urlparse(urllib.parse.urljoin(catalog_url, href))
        match = CSV_LINK.fullmatch(parsed.path)
        if parsed.scheme == "https" and parsed.hostname == CATALOG_HOST and match and not parsed.query and not parsed.fragment:
            matches.append((match.group("date"), parsed.geturl()))
    if not matches:
        raise transport.AcquisitionError("1069 catalog has no supported same-origin dated CSV link")
    date, url = max(matches)
    return url, f"{date[:4]}-{date[4:6]}-{date[6:]}"


def fetch(*, output_root: Path, run_id: str, terms_review_path: Path,
          timeout_seconds: float = 60.0, max_bytes: int = 64 * 1024 * 1024,
          opener: Any = None) -> dict[str, Any]:
    terms_review = transport.require_terms_review(terms_review_path)
    requested_at = transport.utc_now()
    with transport._open(CATALOG_URL, timeout_seconds=timeout_seconds, max_bytes=4 * 1024 * 1024, opener=opener) as response:
        if not 200 <= response.status < 300 or not transport._safe_content_type(response.headers, {"text/html", "application/xhtml+xml"}):
            raise transport.AcquisitionError("1069 catalog response failed status/content-type validation")
        catalog_bytes = response.read(4 * 1024 * 1024 + 1)
        if len(catalog_bytes) > 4 * 1024 * 1024:
            raise transport.AcquisitionError("1069 catalog exceeds bounded size")
        catalog_final_url = response.geturl()
        catalog_headers = transport._headers(response)
    csv_url, filename_date = discover_csv(catalog_bytes, catalog_final_url)
    with transport._open(csv_url, timeout_seconds=timeout_seconds, max_bytes=max_bytes, opener=opener) as response:
        if not 200 <= response.status < 300 or not transport._safe_content_type(response.headers, SAFE_TYPES):
            raise transport.AcquisitionError("1069 CSV response failed status/content-type validation")
        final = urllib.parse.urlparse(response.geturl())
        if final.scheme != "https" or final.hostname != CATALOG_HOST or final.username or final.password:
            raise transport.AcquisitionError("1069 CSV redirected outside the Ministry HTTPS host")
        run_dir = output_root / SOURCE_ID / run_id
        artifact_path = run_dir / "source.csv"
        digest, size = transport._archive_stream(response, artifact_path, max_bytes=max_bytes)
        headers = transport._headers(response)
        final_url = response.geturl()
    catalog_text = catalog_bytes.decode("utf-8", errors="replace")
    date_match = re.search(r"Data ultimo aggiornamento.{0,200}?(\d{2}/\d{2}/\d{4})", catalog_text, re.I | re.S)
    catalog_updated = "unknown"
    if date_match:
        day, month, year = date_match.group(1).split("/")
        catalog_updated = f"{year}-{month}-{day}"
    metadata = {
        "source_id": SOURCE_ID, "run_id": run_id, "acquisition_method": "catalog_discovered_network_fetch",
        "adapter_version": ACQUISITION_VERSION, "config_version": ACQUISITION_VERSION,
        "artifact": artifact_path.name, "artifact_path": str(artifact_path), "byte_size": size, "sha256": digest,
        "requested_at_utc": requested_at, "retrieved_at_utc": transport.utc_now(),
        "catalog_url": CATALOG_URL, "catalog_final_url": catalog_final_url,
        "catalog_sha256": hashlib.sha256(catalog_bytes).hexdigest(), "catalog_response_headers": catalog_headers,
        "requested_url": csv_url, "final_url": final_url, "response_headers": headers,
        "publication_metadata": {"catalog_last_updated": catalog_updated, "filename_publication_date": filename_date,
                                 **{key: headers[key] for key in ("ETag", "Last-Modified") if key in headers}},
        "effective_date": "unknown", "filename_publication_date": filename_date,
        "terms_review": terms_review,
    }
    atomic_json(run_dir / "acquisition-metadata.json", metadata)
    return metadata
