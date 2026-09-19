"""Rehearse a private candidate handoff against the frontend preview boundary.

This tool consumes only an aggregate candidate manifest and optional HTTP
metadata.  It never starts a public server, creates a release, or emits source
rows.  Missing local handoffs are reported as unavailable private evidence,
not as zero coverage.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable


REPORT_VERSION = "candidate-private-frontend-rehearsal-v1"
FORBIDDEN_KEYS = frozenset({
    "source_values", "raw_fields", "address", "street", "latitude", "longitude",
    "coordinates", "records", "rows", "geocoder_query", "geocoder_response",
})


class RehearsalError(ValueError):
    """The private preview contract is incomplete or unsafe."""


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RehearsalError(f"invalid candidate manifest: {path}") from error
    if not isinstance(value, dict):
        raise RehearsalError("candidate manifest must be an object")
    return value


def _assert_safe(value: Any, path: str = "report") -> None:
    if isinstance(value, dict):
        leaked = sorted(FORBIDDEN_KEYS.intersection(value))
        if leaked:
            raise RehearsalError(f"row payload key in {path}: {leaked}")
        for key, child in value.items():
            _assert_safe(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _assert_safe(child, f"{path}[{index}]")


def _request(base_url: str, token: str) -> tuple[int, dict[str, Any]]:
    request = urllib.request.Request(
        base_url.rstrip("/") + "/api/dev/preview/candidates",
        headers={"X-UEC-Dev-Preview-Token": token, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            body = json.loads(response.read().decode("utf-8"))
            return response.status, body if isinstance(body, dict) else {}
    except urllib.error.HTTPError as error:
        return error.code, {}
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        raise RehearsalError(f"private preview request failed: {error}") from error


def rehearse_candidate(
    manifest_path: str | Path,
    *,
    root: str | Path = ".",
    base_url: str | None = None,
    token: str | None = None,
    request: Callable[[str, str], tuple[int, dict[str, Any]]] = _request,
) -> dict[str, Any]:
    """Validate an aggregate handoff and optionally probe the private preview."""
    manifest_file = Path(manifest_path)
    root_path = Path(root)
    manifest = _read(manifest_file)
    publication = manifest.get("publication")
    if not isinstance(publication, dict):
        raise RehearsalError("candidate manifest must contain a publication object")
    if publication.get("release_created") is not False or publication.get("release_promoted") is not False:
        raise RehearsalError("candidate rehearsal requires release_created=false and release_promoted=false")
    if publication.get("project_approval") not in {None, "not-approved", "pending"}:
        raise RehearsalError("candidate rehearsal cannot contain project approval")
    sources = manifest.get("sources")
    if not isinstance(sources, list) or not sources:
        raise RehearsalError("candidate manifest must contain sources")

    source_reports: list[dict[str, Any]] = []
    for entry in sources:
        if not isinstance(entry, dict) or not isinstance(entry.get("source_id"), str):
            raise RehearsalError("each candidate source must have a source_id")
        state = str(entry.get("status") or entry.get("acquisition") or "unknown")
        if "public" in state.lower() and "private" not in state.lower():
            raise RehearsalError(f"source {entry['source_id']} is not private-only")
        handoff_value = entry.get("candidate_handoff_manifest") or entry.get("private_manifest")
        handoff_state = "not-declared"
        normalized_rows = entry.get("normalized_rows")
        if isinstance(handoff_value, str):
            handoff = Path(handoff_value)
            if not handoff.is_absolute():
                handoff = root_path / handoff
            if handoff.is_file():
                handoff_data = _read(handoff)
                handoff_state = "available-private-handoff"
                normalized_rows = handoff_data.get("normalized_rows", normalized_rows)
                if handoff_data.get("release_state") not in {None, "not-created"}:
                    raise RehearsalError(f"source {entry['source_id']} handoff declares a release")
            else:
                handoff_state = "unavailable-private-handoff"
        source_reports.append({
            "source_id": entry["source_id"],
            "handoff_state": handoff_state,
            "normalized_rows": normalized_rows if isinstance(normalized_rows, int) else None,
            "publication_state": "private-only",
            "owner_review": "awaiting-owner-review",
        })

    preview = {
        "state": "not-run",
        "endpoint": "/api/dev/preview/candidates",
        "test_only": True,
        "private_preview": True,
        "raw_fields_absent": None,
    }
    if base_url is not None:
        if not token:
            raise RehearsalError("base_url requires a preview token")
        status, body = request(base_url, token)
        if status != 200:
            raise RehearsalError(f"private preview returned HTTP {status}")
        meta = body.get("meta") if isinstance(body.get("meta"), dict) else {}
        if meta.get("test_only") is not True or meta.get("private_preview") is not True:
            raise RehearsalError("private preview response did not carry test_only/private_preview metadata")
        encoded = json.dumps(body, ensure_ascii=False)
        if any(key in encoded for key in FORBIDDEN_KEYS):
            raise RehearsalError("private preview response contains a prohibited raw-field marker")
        preview.update({"state": "passed", "http_status": status, "raw_fields_absent": True})

    report = {
        "report_version": REPORT_VERSION,
        "status": "passed",
        "fail_closed": True,
        "candidate_state": "private-only; no publication decision implied",
        "manifest": {
            "path": manifest_file.name,
            "release_created": False,
            "release_promoted": False,
            "project_approval": "not-approved",
        },
        "frontend_preview": preview,
        "sources": source_reports,
        "limitations": [
            "This rehearsal validates the private preview boundary, not source factual accuracy, privacy eligibility, or release approval.",
            "Unavailable private handoffs are not counted as zero coverage.",
        ],
        "private_payloads_included": False,
        "publication_boundary": "awaiting-owner-review",
    }
    _assert_safe(report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--base-url")
    parser.add_argument("--token")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = rehearse_candidate(args.manifest, root=args.root, base_url=args.base_url, token=args.token)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"output": str(args.output), "status": report["status"]}, sort_keys=True))
        return 0
    except Exception as error:
        failure = {"report_version": REPORT_VERSION, "status": "blocked", "fail_closed": True, "blocker": str(error), "private_payloads_included": False}
        _assert_safe(failure)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(failure, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"output": str(args.output), "status": "blocked", "blocker": str(error)}, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
