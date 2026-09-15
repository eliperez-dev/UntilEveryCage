"""Controlled acquisition for the Italian Ministry 853/2004 catalog.

The catalog page is the stable authority boundary.  The linked CSV filename
contains a publisher date and changes over time, so the downloader discovers
the current same-origin CSV link instead of embedding a transient filename.
Acquisition only preserves evidence; it never parses, imports, or publishes
rows.
"""
from __future__ import annotations

import argparse
import hashlib
import html.parser
import json
import os
import re
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from pipeline.contracts.source_lifecycle import atomic_json


SOURCE_ID = "it.853-2004"
ACQUISITION_VERSION = "it-853-acquisition-v1"
CATALOG_URL = "https://www.dati.salute.gov.it/it/dataset/stabilimenti-italiani-gli-alimenti-di-origine-animale/"
CATALOG_HOST = "www.dati.salute.gov.it"
DEFAULT_MAX_BYTES = 128 * 1024 * 1024
SAFE_CONTENT_TYPES = {"text/csv", "application/csv", "application/octet-stream", "text/plain"}
CSV_LINK = re.compile(r"^/sites/default/files/opendata/STAB_POA_8_(?P<date>\d{8})\.csv$", re.I)


class AcquisitionError(ValueError):
    """The source could not be safely acquired into private storage."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def default_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]


class _LinkParser(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self.links.append(href)


def require_terms_review(path: Path) -> dict[str, str]:
    try:
        review = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AcquisitionError(f"terms review cannot be read: {error}") from error
    required = {"reviewer", "reference", "reviewed_at", "decision", "notes"}
    if not isinstance(review, dict) or required - review.keys():
        raise AcquisitionError("terms review requires reviewer, reference, reviewed_at, decision, and notes")
    for field in required:
        if not isinstance(review[field], str) or not review[field].strip():
            raise AcquisitionError(f"terms review {field} must be a non-empty string")
    try:
        datetime.fromisoformat(review["reviewed_at"].replace("Z", "+00:00"))
    except ValueError as error:
        raise AcquisitionError("terms review reviewed_at must be ISO-8601") from error
    if review["decision"] != "approved":
        raise AcquisitionError("terms review decision must be 'approved'")
    return {field: review[field] for field in sorted(required)}


def _headers(response: Any) -> dict[str, str]:
    return {
        name: response.headers[name]
        for name in ("Content-Type", "Content-Length", "ETag", "Last-Modified")
        if response.headers.get(name) is not None
    }


def _safe_content_type(headers: Any, allowed: set[str]) -> bool:
    content_type = headers.get("Content-Type")
    return content_type is None or content_type.split(";", 1)[0].strip().lower() in allowed


def _archive_stream(stream: Any, destination: Path, *, max_bytes: int) -> tuple[str, int]:
    if max_bytes <= 0:
        raise AcquisitionError("max_bytes must be positive")
    destination.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    total = 0
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("wb", delete=False, dir=destination.parent, prefix=".download-", suffix=".part") as handle:
            temporary = Path(handle.name)
            while chunk := stream.read(1024 * 1024):
                total += len(chunk)
                if total > max_bytes:
                    raise AcquisitionError(f"download exceeds max_bytes={max_bytes}")
                digest.update(chunk)
                handle.write(chunk)
        os.replace(temporary, destination)
        return digest.hexdigest(), total
    except Exception:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise


def _request(url: str, *, timeout_seconds: float) -> Any:
    if timeout_seconds <= 0:
        raise AcquisitionError("timeout_seconds must be positive")
    request = urllib.request.Request(url, headers={"User-Agent": "UntilEveryCage/controlled-acquisition"})
    try:
        response = urllib.request.urlopen(request, timeout=timeout_seconds)
    except urllib.error.HTTPError as error:
        raise AcquisitionError(f"source returned HTTP {error.code}") from error
    except urllib.error.URLError as error:
        raise AcquisitionError(f"network error: {error.reason}") from error
    if not 200 <= response.status < 300:
        response.close()
        raise AcquisitionError(f"source returned HTTP {response.status}")
    return response


def discover_csv(catalog_bytes: bytes, catalog_url: str) -> tuple[str, str | None]:
    """Return the latest same-origin 853 CSV link and supplied date, if any."""
    parser = _LinkParser()
    try:
        parser.feed(catalog_bytes.decode("utf-8", errors="strict"))
    except UnicodeDecodeError as error:
        raise AcquisitionError("catalog is not valid UTF-8 HTML") from error
    catalog = urllib.parse.urlparse(catalog_url)
    if catalog.hostname != CATALOG_HOST:
        raise AcquisitionError("catalog host is not the authoritative Ministry host")
    matches: list[tuple[str, str]] = []
    for link in parser.links:
        absolute = urllib.parse.urljoin(catalog_url, link)
        parsed = urllib.parse.urlparse(absolute)
        match = CSV_LINK.fullmatch(parsed.path)
        if parsed.scheme != "https" or parsed.hostname != CATALOG_HOST or not match:
            continue
        matches.append((match.group("date"), absolute))
    if not matches:
        raise AcquisitionError("catalog has no supported 853/2004 CSV download link")
    date, url = max(matches)
    return url, f"{date[:4]}-{date[4:6]}-{date[6:]}"


def _catalog_metadata(catalog_bytes: bytes) -> dict[str, str]:
    text = catalog_bytes.decode("utf-8", errors="replace")
    # The catalog supplies this human-facing value; keep it as evidence and
    # never treat it as an observation date for individual rows.
    match = re.search(r"Data ultimo aggiornamento\s*</[^>]+>\s*[^<]*<[^>]+>\s*(\d{2}/\d{2}/\d{4})", text, re.I)
    if not match:
        match = re.search(r"Data ultimo aggiornamento.{0,200}?(\d{2}/\d{2}/\d{4})", text, re.I | re.S)
    supplied = None
    if match:
        day, month, year = match.group(1).split("/")
        supplied = f"{year}-{month}-{day}"
    return {"catalog_last_updated": supplied or "unknown"}


def fetch(
    *,
    output_root: Path,
    run_id: str,
    terms_review_path: Path,
    catalog_url: str = CATALOG_URL,
    timeout_seconds: float = 60.0,
    max_bytes: int = DEFAULT_MAX_BYTES,
    opener: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    terms_review = require_terms_review(terms_review_path)
    open_url = opener or urllib.request.urlopen
    requested_at = utc_now()
    catalog_request = urllib.request.Request(catalog_url, headers={"User-Agent": "UntilEveryCage/controlled-acquisition"})
    try:
        with open_url(catalog_request, timeout=timeout_seconds) as catalog_response:
            if not 200 <= catalog_response.status < 300:
                raise AcquisitionError(f"catalog returned HTTP {catalog_response.status}")
            if not _safe_content_type(catalog_response.headers, {"text/html", "application/xhtml+xml"}):
                raise AcquisitionError(f"unexpected catalog content type: {catalog_response.headers.get('Content-Type')}")
            catalog_bytes = catalog_response.read(4 * 1024 * 1024 + 1)
            if len(catalog_bytes) > 4 * 1024 * 1024:
                raise AcquisitionError("catalog exceeds bounded size")
            catalog_final_url = catalog_response.geturl()
            catalog_headers = _headers(catalog_response)
    except urllib.error.HTTPError as error:
        raise AcquisitionError(f"catalog returned HTTP {error.code}") from error
    except urllib.error.URLError as error:
        raise AcquisitionError(f"catalog network error: {error.reason}") from error
    csv_url, filename_date = discover_csv(catalog_bytes, catalog_final_url)
    try:
        csv_request = urllib.request.Request(csv_url, headers={"User-Agent": "UntilEveryCage/controlled-acquisition"})
        with open_url(csv_request, timeout=timeout_seconds) as response:
            if not 200 <= response.status < 300:
                raise AcquisitionError(f"CSV returned HTTP {response.status}")
            if not _safe_content_type(response.headers, SAFE_CONTENT_TYPES):
                raise AcquisitionError(f"unexpected CSV content type: {response.headers.get('Content-Type')}")
            run_dir = output_root / SOURCE_ID / run_id
            artifact_path = run_dir / "source.csv"
            digest, byte_size = _archive_stream(response, artifact_path, max_bytes=max_bytes)
            response_headers = _headers(response)
            final_url = response.geturl()
    except urllib.error.HTTPError as error:
        raise AcquisitionError(f"CSV returned HTTP {error.code}") from error
    except urllib.error.URLError as error:
        raise AcquisitionError(f"CSV network error: {error.reason}") from error
    metadata = {
        "acquisition_method": "catalog_discovered_network_fetch",
        "adapter_version": ACQUISITION_VERSION,
        "artifact": artifact_path.name,
        "byte_size": byte_size,
        "catalog_url": catalog_url,
        "catalog_final_url": catalog_final_url,
        "catalog_response_headers": catalog_headers,
        "catalog_sha256": hashlib.sha256(catalog_bytes).hexdigest(),
        "catalog_metadata": _catalog_metadata(catalog_bytes),
        "config_version": ACQUISITION_VERSION,
        "content_type": response_headers.get("Content-Type", "unknown").split(";", 1)[0].lower(),
        "effective_date": "unknown",
        "filename_publication_date": filename_date or "unknown",
        "final_url": final_url,
        "publication_metadata": {
            "catalog_last_updated": _catalog_metadata(catalog_bytes).get("catalog_last_updated", "unknown"),
            "filename_publication_date": filename_date or "unknown",
            **{key: response_headers[key] for key in ("ETag", "Last-Modified") if key in response_headers},
        },
        "requested_at_utc": requested_at,
        "requested_url": csv_url,
        "response_headers": response_headers,
        "retrieved_at_utc": utc_now(),
        "run_id": run_id,
        "sha256": digest,
        "source_id": SOURCE_ID,
        "terms_review": terms_review,
    }
    atomic_json(run_dir / "acquisition-metadata.json", metadata)
    return metadata


def archive_local_file(local_file: Path, output_root: Path, *, run_id: str, retrieved_at: str | None = None) -> dict[str, Any]:
    """Archive a local/synthetic CSV for tests without implying source access."""
    if not local_file.is_file():
        raise AcquisitionError(f"local file does not exist: {local_file}")
    run_dir = output_root / SOURCE_ID / run_id
    with local_file.open("rb") as stream:
        digest, byte_size = _archive_stream(stream, run_dir / "source.csv", max_bytes=DEFAULT_MAX_BYTES)
    metadata = {
        "acquisition_method": "local_file",
        "adapter_version": ACQUISITION_VERSION,
        "artifact": "source.csv",
        "byte_size": byte_size,
        "catalog_url": "unknown",
        "catalog_final_url": "unknown",
        "catalog_metadata": {},
        "config_version": ACQUISITION_VERSION,
        "content_type": "text/csv",
        "effective_date": "unknown",
        "filename_publication_date": "unknown",
        "final_url": "unknown",
        "publication_metadata": {},
        "requested_at_utc": retrieved_at or utc_now(),
        "requested_url": "unknown",
        "response_headers": {},
        "retrieved_at_utc": retrieved_at or utc_now(),
        "run_id": run_id,
        "sha256": digest,
        "source_id": SOURCE_ID,
        "terms_review": "not_required_for_local_file",
    }
    atomic_json(run_dir / "acquisition-metadata.json", metadata)
    return metadata


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--fetch", action="store_true")
    mode.add_argument("--local-file", type=Path)
    parser.add_argument("--terms-review", type=Path)
    parser.add_argument("--catalog-url", default=CATALOG_URL)
    parser.add_argument("--output-root", type=Path, default=Path("data/raw"))
    parser.add_argument("--run-id", default=default_run_id())
    parser.add_argument("--timeout-seconds", type=float, default=60.0)
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    args = parser.parse_args()
    try:
        if args.fetch:
            if args.terms_review is None:
                raise AcquisitionError("--terms-review is required with --fetch")
            metadata = fetch(output_root=args.output_root, run_id=args.run_id, terms_review_path=args.terms_review,
                             catalog_url=args.catalog_url, timeout_seconds=args.timeout_seconds, max_bytes=args.max_bytes)
        else:
            metadata = archive_local_file(args.local_file, args.output_root, run_id=args.run_id)
    except AcquisitionError as error:
        print(json.dumps({"status": "failed", "error": str(error)}, sort_keys=True))
        return 2
    print(json.dumps({"status": "archived", "metadata": metadata}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
