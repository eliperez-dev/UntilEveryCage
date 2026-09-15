"""Bounded, provenance-preserving acquisition primitives shared by sources.

The acquisition layer only preserves bytes and response facts.  It does not
parse, classify, import, or publish a source.  Network fetches require an
operator-authored terms record and always write to a caller-selected private
root; source packages provide only source identity and content-type policy.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


class AcquisitionError(ValueError):
    """An acquisition was not bounded, authorized, valid, or complete."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def default_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]


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


def selected_headers(headers: Any) -> dict[str, str]:
    """Keep response metadata useful for reproducibility, never credentials."""
    names = ("Content-Type", "Content-Length", "Content-Disposition", "ETag", "Last-Modified", "Date")
    return {name: headers[name] for name in names if headers.get(name) is not None}


def _atomic_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def archive_stream(stream: Any, artifact_path: Path, *, max_bytes: int) -> tuple[str, int]:
    if max_bytes <= 0:
        raise AcquisitionError("max_bytes must be positive")
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    digest = hashlib.sha256()
    total = 0
    try:
        with tempfile.NamedTemporaryFile("wb", delete=False, dir=artifact_path.parent, prefix=".download-", suffix=".part") as handle:
            temporary = Path(handle.name)
            while chunk := stream.read(1024 * 1024):
                total += len(chunk)
                if total > max_bytes:
                    raise AcquisitionError(f"download exceeds max_bytes={max_bytes}")
                digest.update(chunk)
                handle.write(chunk)
        os.replace(temporary, artifact_path)
        return digest.hexdigest(), total
    except Exception:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise


class _RedirectRecorder(urllib.request.HTTPRedirectHandler):
    def __init__(self) -> None:
        super().__init__()
        self.redirects: list[dict[str, Any]] = []

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        self.redirects.append({"status": code, "from_url": fp.geturl(), "to_url": newurl})
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_source(
    *,
    source_id: str,
    url: str,
    output_root: str | Path,
    artifact_name: str,
    terms_review_path: str | Path,
    run_id: str | None = None,
    timeout_seconds: float = 60.0,
    max_bytes: int = 64 * 1024 * 1024,
    user_agent: str = "UntilEveryCage/controlled-acquisition",
    allowed_content_types: Iterable[str] = ("text/csv", "application/csv", "application/octet-stream"),
    effective_date: str | None = None,
    publication_date: str | None = None,
    code_version: str = "unknown",
    config_version: str = "unknown",
    coverage: str | None = None,
    rights_caveat: str | None = None,
    privacy_caveat: str | None = None,
) -> dict[str, Any]:
    if not source_id or not url:
        raise AcquisitionError("source_id and url are required")
    if timeout_seconds <= 0:
        raise AcquisitionError("timeout_seconds must be positive")
    terms_review = require_terms_review(Path(terms_review_path))
    run_id = run_id or default_run_id()
    run_dir = Path(output_root) / source_id / run_id
    artifact_path = run_dir / artifact_name
    requested_at = utc_now()
    recorder = _RedirectRecorder()
    try:
        opener = urllib.request.build_opener(recorder)
        request = urllib.request.Request(url, headers={"User-Agent": user_agent})
        with opener.open(request, timeout=timeout_seconds) as response:
            if not 200 <= response.status < 300:
                raise AcquisitionError(f"source returned HTTP {response.status}")
            content_type = response.headers.get("Content-Type")
            allowed = {item.lower() for item in allowed_content_types}
            if content_type and content_type.split(";", 1)[0].strip().lower() not in allowed:
                raise AcquisitionError(f"unexpected content type: {content_type}")
            sha256, byte_size = archive_stream(response, artifact_path, max_bytes=max_bytes)
            headers = selected_headers(response.headers)
            final_url = response.geturl()
    except urllib.error.HTTPError as error:
        raise AcquisitionError(f"source returned HTTP {error.code}") from error
    except urllib.error.URLError as error:
        raise AcquisitionError(f"network error: {error.reason}") from error
    metadata = {
        "acquisition_method": "network_fetch",
        "source_id": source_id,
        "artifact": artifact_name,
        "artifact_path": str(artifact_path),
        "run_id": run_id,
        "requested_url": url,
        "final_url": final_url,
        "redirects": recorder.redirects,
        "response_headers": headers,
        "requested_at_utc": requested_at,
        "retrieved_at_utc": utc_now(),
        "effective_date": effective_date or headers.get("Last-Modified") or "unknown",
        "publication_date": publication_date,
        "sha256": sha256,
        "byte_size": byte_size,
        "adapter_version": code_version,
        "code_version": code_version,
        "config_version": config_version,
        "coverage": coverage,
        "rights_caveat": rights_caveat,
        "privacy_caveat": privacy_caveat,
        "terms_review": terms_review,
    }
    _atomic_bytes(run_dir / "acquisition-metadata.json", (json.dumps(metadata, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode())
    return metadata
