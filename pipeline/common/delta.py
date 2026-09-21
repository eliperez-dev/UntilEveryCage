"""Private, aggregate-only comparison of two validated adapter runs."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .identity import record_key

DELTA_VERSION = "v2-delta-1"


def _jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise ValueError(f"missing run state: {path}")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _manifest(run_dir: Path) -> dict[str, Any]:
    # Source adapters historically used both names.  The shared operations
    # layer treats them as the same private manifest contract so a wrapper
    # rename cannot erase the release diff for an otherwise valid run.
    path = run_dir / "run-manifest.json"
    if not path.exists():
        path = run_dir / "manifest.json"
    if not path.exists():
        raise ValueError(f"missing run manifest: {run_dir / 'run-manifest.json'}")
    return json.loads(path.read_text(encoding="utf-8"))


def compare_normalized_paths(previous_path: str | Path | None, current_path: str | Path) -> dict[str, Any]:
    """Compare normalized JSONL by stable source identity without row payloads."""
    if previous_path is None:
        return {"status": "not-run", "counts": {"added": 0, "changed": 0, "not_observed": 0, "suppressed": 0}, "disappearance_semantics": "not-observed; never inferred as closure"}
    previous = Path(previous_path)
    current = Path(current_path)
    if not previous.is_file() or not current.is_file():
        return {"status": "failed", "error": "normalized state is missing", "counts": {"added": 0, "changed": 0, "not_observed": 0, "suppressed": 0}, "disappearance_semantics": "not-observed; never inferred as closure"}
    try:
        old = {record_key(row): row for row in _jsonl(previous)}
        new = {record_key(row): row for row in _jsonl(current)}
        added = sum(key not in old for key in new)
        changed = sum(key in old and _fingerprint(old[key]) != _fingerprint(row) for key, row in new.items())
        not_observed = sum(key not in new for key in old)
    except Exception as exc:
        return {"status": "failed", "error_type": type(exc).__name__, "error": str(exc), "counts": {"added": 0, "changed": 0, "not_observed": 0, "suppressed": 0}, "disappearance_semantics": "not-observed; never inferred as closure"}
    return {"status": "delta-ready", "counts": {"added": added, "changed": changed, "not_observed": not_observed, "suppressed": 0}, "disappearance_semantics": "not-observed; never inferred as closure"}


def _fingerprint(row: dict[str, Any]) -> str:
    comparable = {key: value for key, value in row.items() if key not in {"provenance", "source_values", "source_columns"}}
    return hashlib.sha256(json.dumps(comparable, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def compare_runs(previous_dir: Path, current_dir: Path, suppressed_ids: set[str | tuple[str, str, str]] | None = None, prior_eligible_release: dict[str, Any] | None = None) -> dict[str, Any]:
    """Compare normalized states without interpreting absence as closure.

    Only identifiers, categories, counts, and run fingerprints are emitted. Source
    payloads remain in the restricted run directories and are never copied here.
    """
    try:
        previous_manifest = _manifest(previous_dir)
        current_manifest = _manifest(current_dir)
        if previous_manifest.get("schema_fingerprint") != current_manifest.get("schema_fingerprint"):
            return {"status": "schema-change-blocked", "delta_version": DELTA_VERSION, "publication_state": "unchanged", "release_promoted": False, "public_surfaces": _blocked_surfaces(), "geocoding": "disabled", "prior_eligible_release": prior_eligible_release, "previous": _summary(previous_manifest), "current": _summary(current_manifest), "counts": {"added": 0, "changed": 0, "not_observed": 0, "suppressed": 0}}
        previous = {record_key(row): row for row in _jsonl(previous_dir / "normalized" / "records.jsonl")}
        current = {record_key(row): row for row in _jsonl(current_dir / "normalized" / "records.jsonl")}
        suppressed = suppressed_ids or set()
        added = changed = not_observed = suppressed_count = 0
        for source_id, row in current.items():
            if source_id in suppressed:
                suppressed_count += 1
            elif source_id not in previous:
                added += 1
            elif _fingerprint(previous[source_id]) != _fingerprint(row):
                changed += 1
        # A missing source row is only an observation boundary, never a closure.
        for source_id in previous:
            if source_id not in current and source_id not in suppressed:
                not_observed += 1
        return {"status": "delta-ready", "delta_version": DELTA_VERSION, "publication_state": "terms-gate-blocked" if current_manifest.get("terms_status") == "pending_confirmation" else "human-gate-required", "release_promoted": False, "public_surfaces": _blocked_surfaces(), "geocoding": "disabled", "prior_eligible_release": prior_eligible_release, "previous": _summary(previous_manifest), "current": _summary(current_manifest), "counts": {"added": added, "changed": changed, "not_observed": not_observed, "suppressed": suppressed_count}}
    except Exception as exc:
        return {"status": "failed", "delta_version": DELTA_VERSION, "publication_state": "unchanged", "release_promoted": False, "public_surfaces": _blocked_surfaces(), "geocoding": "disabled", "error_type": type(exc).__name__, "error": str(exc), "prior_eligible_release": prior_eligible_release}


def _summary(manifest: dict[str, Any]) -> dict[str, Any]:
    return {key: manifest.get(key) for key in ("checksum_sha256", "schema_fingerprint", "config_fingerprint", "mapping_version", "adapter_version", "schema_version", "input_rows", "normalized_rows", "quarantined_rows")}


def _blocked_surfaces() -> dict[str, bool]:
    return {surface: False for surface in ("api", "map", "export", "cache", "history")}
