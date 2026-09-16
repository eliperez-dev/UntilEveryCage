"""Deterministic, row-free private review packets for source runs.

The packet is an operator aid, not a release approval.  It contains only
aggregate counts, schema/provenance facts, and explicit gate state; source
values and addresses remain in the restricted run artifacts.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .delta import compare_normalized_paths
from pipeline.contracts.source_lifecycle import atomic_json


REVIEW_PACKET_VERSION = "private-review-packet-v1"


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"missing review input: {path.name}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"review input must be an object: {path.name}")
    return value


def _digest(path: Path) -> str | None:
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _counts(manifest: dict[str, Any], qa: dict[str, Any]) -> dict[str, Any]:
    values = {key: manifest.get(key) for key in ("input_rows", "normalized_rows", "quarantined_rows")}
    qa_values = {key: qa.get(key) for key in values}
    valid = all(isinstance(value, int) and value >= 0 for value in values.values())
    return {
        **values,
        "reconciles": valid and values["input_rows"] == values["normalized_rows"] + values["quarantined_rows"],
        "qa_matches_manifest": values == qa_values,
    }


def build_review_packet(
    run_dir: str | Path,
    *,
    previous_normalized_path: str | Path | None = None,
    blockers: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    root = Path(run_dir)
    manifest = _read_json(root / "manifest.json")
    qa = _read_json(root / "qa.json")
    status = _read_json(root / "run-status.json")
    counts = _counts(manifest, qa)
    normalized = root / "normalized" / "records.jsonl"
    packet: dict[str, Any] = {
        "schema_version": REVIEW_PACKET_VERSION,
        "source_id": manifest.get("source_id"),
        "run_dir_digest": _digest(root / "manifest.json"),
        "provenance": {
            key: manifest.get(key)
            for key in ("source_url", "retrieved_at_utc", "publication_date", "effective_date", "sha256", "byte_size", "code_version", "config_version")
            if manifest.get(key) is not None
        },
        "schema": {
            "adapter_version": manifest.get("adapter_version"),
            "schema_version": manifest.get("schema_version"),
            "schema_fingerprint": manifest.get("schema_fingerprint"),
            "schema_status": manifest.get("schema_status", "not-reported"),
        },
        "counts": counts,
        "quarantine": {
            "rows": manifest.get("quarantined_rows"),
            "reasons": manifest.get("anomaly_counts", {}),
        },
        "release_diff": compare_normalized_paths(previous_normalized_path, normalized) if previous_normalized_path else {
            "status": "not-run",
            "counts": {"added": None, "changed": None, "not_observed": None, "suppressed": 0},
            "disappearance_semantics": "not-observed; never inferred as closure",
        },
        "gates": {
            "release_state": manifest.get("release_state"),
            "publication_state": manifest.get("publication_state"),
            "release_promoted": status.get("release_promoted"),
            "public_surfaces": status.get("public_surfaces", {surface: False for surface in ("api", "map", "export", "cache", "history")}),
            "geocoding": manifest.get("geocoding", "disabled"),
        },
        "blockers": blockers or {},
    }
    if not counts["reconciles"] or not counts["qa_matches_manifest"]:
        packet["blockers"].setdefault("validation", []).append("manifest and QA row counts must reconcile")
    if packet["gates"]["release_state"] != "not-created" or packet["gates"]["release_promoted"] is not False:
        packet["blockers"].setdefault("release", []).append("private review requires release_state=not-created and release_promoted=false")
    return packet


def write_review_packet(
    run_dir: str | Path,
    *,
    previous_normalized_path: str | Path | None = None,
    blockers: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    packet = build_review_packet(run_dir, previous_normalized_path=previous_normalized_path, blockers=blockers)
    atomic_json(Path(run_dir) / "review-packet.json", packet)
    return packet
