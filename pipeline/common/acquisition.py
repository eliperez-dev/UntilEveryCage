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
import socket
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable


class AcquisitionError(ValueError):
    """An acquisition was not bounded, authorized, valid, or complete."""

    def __init__(self, message: str, *, failure_class: str = "acquisition", retryable: bool = False, action: str = "inspect the private acquisition evidence and source terms") -> None:
        super().__init__(message)
        self.failure_class = failure_class
        self.retryable = retryable
        self.action = action


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
    max_attempts: int = 1,
    retry_delay_seconds: float = 0.0,
    max_retry_delay_seconds: float = 30.0,
    sleep_fn: Any = time.sleep,
    query_context: dict[str, Any] | None = None,
    artifact_validator: Callable[[Path, dict[str, str]], None] | None = None,
) -> dict[str, Any]:
    if not source_id or not url:
        raise AcquisitionError("source_id and url are required")
    if timeout_seconds <= 0:
        raise AcquisitionError("timeout_seconds must be positive")
    if not 1 <= max_attempts <= 10:
        raise AcquisitionError("max_attempts must be between 1 and 10", failure_class="configuration")
    if retry_delay_seconds < 0 or max_retry_delay_seconds < 0 or retry_delay_seconds > max_retry_delay_seconds:
        raise AcquisitionError("retry delay values are invalid", failure_class="configuration")
    terms_review = require_terms_review(Path(terms_review_path))
    run_id = run_id or default_run_id()
    run_dir = Path(output_root) / source_id / run_id
    artifact_path = run_dir / artifact_name
    requested_at = utc_now()
    # Always download to a private temporary sibling.  A repeated run_id must
    # never replace an existing raw artifact, even if a caller accidentally
    # reuses the identifier with different bytes.
    download_path = artifact_path.with_name(f".{artifact_path.name}.{uuid.uuid4().hex}.download")
    artifact_state = "stored"
    attempts: list[dict[str, Any]] = []
    headers: dict[str, str] = {}
    final_url = url
    for attempt_number in range(1, max_attempts + 1):
        recorder = _RedirectRecorder()
        try:
            opener = urllib.request.build_opener(recorder)
            request = urllib.request.Request(url, headers={"User-Agent": user_agent})
            with opener.open(request, timeout=timeout_seconds) as response:
                if not 200 <= response.status < 300:
                    retryable = response.status == 429 or 500 <= response.status <= 599
                    raise AcquisitionError(
                        f"source returned HTTP {response.status}", failure_class=f"http-{response.status}",
                        retryable=retryable,
                        action="retry a bounded server/rate-limit failure" if retryable else "verify URL, authorization, and terms before another run",
                    )
                content_type = response.headers.get("Content-Type")
                allowed = {item.lower() for item in allowed_content_types}
                if content_type and content_type.split(";", 1)[0].strip().lower() not in allowed:
                    raise AcquisitionError(
                        f"unexpected content type: {content_type}", failure_class="content-type",
                        action="inspect the source response and update the adapter contract only after review",
                    )
                sha256, byte_size = archive_stream(response, download_path, max_bytes=max_bytes)
                headers = selected_headers(response.headers)
                final_url = response.geturl()
                if headers.get("Content-Length") is not None:
                    try:
                        expected_size = int(headers["Content-Length"])
                    except ValueError as error:
                        raise AcquisitionError(
                            "source returned an invalid Content-Length header",
                            failure_class="content-length",
                            action="inspect the private response evidence before retrying",
                        ) from error
                    if expected_size != byte_size:
                        raise AcquisitionError(
                            f"source Content-Length={expected_size} but received {byte_size} bytes",
                            failure_class="truncated-response",
                            retryable=True,
                            action="retry a bounded incomplete response; use the assisted capture route if it persists",
                        )
                if artifact_validator is not None:
                    artifact_validator(download_path, headers)
            if artifact_path.exists():
                if artifact_path.read_bytes() != download_path.read_bytes():
                    raise AcquisitionError("existing run artifact differs from newly acquired bytes", failure_class="artifact-collision", action="use a new run_id and preserve both observations")
                download_path.unlink(missing_ok=True)
                artifact_state = "unchanged"
            else:
                artifact_path.parent.mkdir(parents=True, exist_ok=True)
                os.replace(download_path, artifact_path)
            attempts.append({"attempt": attempt_number, "outcome": "success", "redirects": recorder.redirects})
            break
        except urllib.error.HTTPError as error:
            retryable = error.code == 429 or 500 <= error.code <= 599
            details = {"attempt": attempt_number, "outcome": "failed", "failure_class": f"http-{error.code}", "retryable": retryable, "message": str(error)}
            attempts.append(details)
            if not retryable or attempt_number == max_attempts:
                failure = AcquisitionError(
                    f"source returned HTTP {error.code}", failure_class=details["failure_class"], retryable=retryable,
                    action="retry a bounded server/rate-limit failure" if retryable else "verify URL, authorization, and terms before another run",
                )
                _write_failure(run_dir, source_id, run_id, failure, attempts, query_context, url, requested_at, effective_date, publication_date)
                raise failure from error
        except urllib.error.URLError as error:
            details = {"attempt": attempt_number, "outcome": "failed", "failure_class": "network", "retryable": True, "message": str(error)}
            attempts.append(details)
            if attempt_number == max_attempts:
                failure = AcquisitionError(f"network error: {error.reason}", failure_class="network", retryable=True, action="retry within the source bound; verify connectivity if it persists")
                _write_failure(run_dir, source_id, run_id, failure, attempts, query_context, url, requested_at, effective_date, publication_date)
                raise failure from error
        except (TimeoutError, socket.timeout) as error:
            details = {"attempt": attempt_number, "outcome": "failed", "failure_class": "timeout", "retryable": True, "message": str(error)}
            attempts.append(details)
            if attempt_number == max_attempts:
                failure = AcquisitionError(f"timeout: {error}", failure_class="timeout", retryable=True, action="retry within the source bound; use the manual capture route if it persists")
                _write_failure(run_dir, source_id, run_id, failure, attempts, query_context, url, requested_at, effective_date, publication_date)
                raise failure from error
        except AcquisitionError as error:
            download_path.unlink(missing_ok=True)
            attempts.append({"attempt": attempt_number, "outcome": "failed", "failure_class": error.failure_class, "retryable": error.retryable, "message": str(error)})
            if not error.retryable or attempt_number == max_attempts:
                _write_failure(run_dir, source_id, run_id, error, attempts, query_context, url, requested_at, effective_date, publication_date)
                raise
        if attempt_number < max_attempts:
            delay = min(max_retry_delay_seconds, retry_delay_seconds * (2 ** (attempt_number - 1)))
            attempts[-1]["retry_delay_seconds"] = delay
            if delay:
                sleep_fn(delay)
    else:
        raise AcquisitionError("acquisition retry loop did not complete", failure_class="runtime")
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
        "attempts": attempts,
        "artifact_state": artifact_state,
        "retention": {"class": "restricted-research-evidence", "public_exposure": False, "review_required": True},
    }
    if query_context is not None:
        metadata["query_context"] = query_context
    _atomic_bytes(run_dir / "acquisition-metadata.json", (json.dumps(metadata, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode())
    return metadata


def _write_failure(
    run_dir: Path,
    source_id: str,
    run_id: str,
    error: AcquisitionError,
    attempts: list[dict[str, Any]],
    query_context: dict[str, Any] | None = None,
    requested_url: str | None = None,
    requested_at_utc: str | None = None,
    effective_date: str | None = None,
    publication_date: str | None = None,
) -> None:
    """Leave a private, actionable failure record without creating an artifact."""
    payload = {
        "schema_version": "acquisition-failure-v1", "source_id": source_id, "run_id": run_id,
        "failure_class": error.failure_class, "retryable": error.retryable, "error": str(error),
        "action": error.action, "attempts": attempts, "artifact_created": False,
        "public_exposure": False,
    }
    if requested_url is not None:
        payload["requested_url"] = requested_url
    if requested_at_utc is not None:
        payload["requested_at_utc"] = requested_at_utc
    if effective_date is not None:
        payload["effective_date"] = effective_date
    if publication_date is not None:
        payload["publication_date"] = publication_date
    if query_context is not None:
        payload["query_context"] = query_context
    try:
        _atomic_bytes(run_dir / "acquisition-failure.json", (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode())
    except OSError:
        # The original acquisition error is more useful than masking it with a
        # best-effort diagnostic write failure.
        pass
