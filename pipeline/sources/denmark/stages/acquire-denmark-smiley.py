#!/usr/bin/env python3
"""Archive a Denmark Find Smiley artifact without importing or publishing it."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
import sys

for _candidate in Path(__file__).resolve().parents:
    if (_candidate / "pipeline").is_dir():
        sys.path.insert(0, str(_candidate))
        break
from pipeline.contracts.source_lifecycle import atomic_json


SOURCE_ID = "dk.smiley"
ADAPTER_VERSION = "denmark-smiley-acquisition-v1"
DEFAULT_URL = "https://pub.fvst.dk/publikationer/Smileydata.xml"
DEFAULT_MAX_BYTES = 128 * 1024 * 1024
APPROVED_DECISION = "approved"
SAFE_CONTENT_TYPES = {"application/xml", "text/xml", "application/octet-stream"}


class AcquisitionError(ValueError):
    """An acquisition was not authorized, valid, or complete."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def default_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]


def require_terms_review(path: Path) -> dict:
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
    if review["decision"] != APPROVED_DECISION:
        raise AcquisitionError(f"terms review decision must be {APPROVED_DECISION!r}")
    return {field: review[field] for field in sorted(required)}


def selected_headers(headers) -> dict[str, str]:
    """Persist response metadata relevant to reproducibility, not credentials."""
    return {
        name: headers[name]
        for name in ("Content-Type", "Content-Length", "ETag", "Last-Modified")
        if headers.get(name) is not None
    }


def content_type_is_safe(headers) -> bool:
    raw = headers.get("Content-Type")
    return raw is None or raw.split(";", 1)[0].strip().lower() in SAFE_CONTENT_TYPES


def archive_stream(stream, artifact_path: Path, *, max_bytes: int) -> tuple[str, int]:
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    digest = hashlib.sha256()
    total = 0
    try:
        with tempfile.NamedTemporaryFile("wb", delete=False, dir=artifact_path.parent, prefix=".download-", suffix=".part") as handle:
            temp_path = Path(handle.name)
            while chunk := stream.read(1024 * 1024):
                total += len(chunk)
                if total > max_bytes:
                    raise AcquisitionError(f"download exceeds max_bytes={max_bytes}")
                digest.update(chunk)
                handle.write(chunk)
        os.replace(temp_path, artifact_path)
        return digest.hexdigest(), total
    except Exception:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise


def write_metadata(path: Path, metadata: dict) -> None:
    atomic_json(path, metadata)


def _validate_timestamp(value: str, field: str) -> str:
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise AcquisitionError(f"{field} must be ISO-8601") from error
    return value


def archive_local_file(local_file: Path, output_root: Path, *, run_id: str,
                       retrieved_at: str | None = None,
                       source_url: str = DEFAULT_URL) -> dict:
    local_file = local_file.resolve()
    if not local_file.is_file():
        raise AcquisitionError(f"local file does not exist: {local_file}")
    run_dir = output_root / SOURCE_ID / run_id
    artifact_path = run_dir / "Smileydata.xml"
    retrieved_at = _validate_timestamp(retrieved_at, "retrieved_at_utc") if retrieved_at else utc_now()
    if not source_url.strip():
        raise AcquisitionError("source_url must be non-empty")
    with local_file.open("rb") as stream:
        sha256, byte_size = archive_stream(stream, artifact_path, max_bytes=DEFAULT_MAX_BYTES)
    metadata = {
        "acquisition_method": "local_file",
        "adapter_version": ADAPTER_VERSION,
        "artifact": artifact_path.name,
        "byte_size": byte_size,
        "config_version": ADAPTER_VERSION,
        "final_url": source_url,
        "publication_metadata": {},
        "requested_url": source_url,
        "response_headers": {},
        "retrieved_at_utc": retrieved_at,
        "run_id": run_id,
        "sha256": sha256,
        "source_id": SOURCE_ID,
        "source_local_path": str(local_file),
        "terms_review": "not_required_for_local_file",
    }
    write_metadata(run_dir / "acquisition-metadata.json", metadata)
    return metadata


def fetch(url: str, output_root: Path, *, run_id: str, terms_review_path: Path | None, timeout_seconds: float, max_bytes: int) -> dict:
    if terms_review_path is None:
        raise AcquisitionError("--terms-review is required with --fetch")
    if timeout_seconds <= 0 or max_bytes <= 0:
        raise AcquisitionError("timeout_seconds and max_bytes must be positive")
    terms_review = require_terms_review(terms_review_path)
    run_dir = output_root / SOURCE_ID / run_id
    artifact_path = run_dir / "Smileydata.xml"
    requested_at = utc_now()
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "UntilEveryCage/controlled-acquisition"})
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            if not 200 <= response.status < 300:
                raise AcquisitionError(f"source returned HTTP {response.status}")
            if not content_type_is_safe(response.headers):
                raise AcquisitionError(f"unexpected content type: {response.headers.get('Content-Type')}")
            sha256, byte_size = archive_stream(response, artifact_path, max_bytes=max_bytes)
            headers = selected_headers(response.headers)
            final_url = response.geturl()
    except urllib.error.HTTPError as error:
        raise AcquisitionError(f"source returned HTTP {error.code}") from error
    except urllib.error.URLError as error:
        raise AcquisitionError(f"network error: {error.reason}") from error
    metadata = {
        "acquisition_method": "network_fetch",
        "adapter_version": ADAPTER_VERSION,
        "artifact": artifact_path.name,
        "byte_size": byte_size,
        "config_version": ADAPTER_VERSION,
        "final_url": final_url,
        "publication_metadata": {key: headers[key] for key in ("ETag", "Last-Modified") if key in headers},
        "requested_at_utc": requested_at,
        "requested_url": url,
        "response_headers": headers,
        "retrieved_at_utc": utc_now(),
        "run_id": run_id,
        "sha256": sha256,
        "source_id": SOURCE_ID,
        "terms_review": terms_review,
    }
    write_metadata(run_dir / "acquisition-metadata.json", metadata)
    return metadata


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--fetch", action="store_true", help="Fetch the registry URL; requires a reviewed terms file.")
    mode.add_argument("--local-file", type=Path, help="Archive a local/synthetic XML file without network access.")
    parser.add_argument("--url", default=DEFAULT_URL, help="Requested URL for --fetch.")
    parser.add_argument("--source-url", default=DEFAULT_URL, help="Official source URL to record for --local-file.")
    parser.add_argument("--terms-review", type=Path, help="Approved JSON terms-review record; required for --fetch.")
    parser.add_argument("--output-root", type=Path, default=Path("data/raw"))
    parser.add_argument("--run-id", default=default_run_id())
    parser.add_argument("--retrieved-at-utc", help="Fixed ISO-8601 observation time for --local-file reruns.")
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    args = parser.parse_args()
    try:
        if args.fetch:
            metadata = fetch(args.url, args.output_root, run_id=args.run_id, terms_review_path=args.terms_review, timeout_seconds=args.timeout_seconds, max_bytes=args.max_bytes)
        else:
            metadata = archive_local_file(
                args.local_file,
                args.output_root,
                run_id=args.run_id,
                retrieved_at=args.retrieved_at_utc,
                source_url=args.source_url,
            )
    except AcquisitionError as error:
        print(json.dumps({"status": "failed", "error": str(error)}, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps({"status": "archived", "metadata": metadata}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
