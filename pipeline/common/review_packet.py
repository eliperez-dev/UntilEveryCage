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
ROW_FREE_REVIEW_PACKET_VERSION = "private-review-packet-v2"


def _assert_row_free(value: Any, path: str = "packet") -> None:
    """Reject row-shaped or location-bearing payloads in operator artifacts."""
    forbidden = {
        "source_values", "raw_fields", "address", "street", "latitude", "longitude",
        "coordinates", "geocoder_query", "geocoder_response", "phone", "email",
    }
    if isinstance(value, dict):
        leaked = sorted(forbidden.intersection(value))
        if leaked:
            raise ValueError(f"row-free review packet contains prohibited keys at {path}: {leaked}")
        for key, child in value.items():
            _assert_row_free(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _assert_row_free(child, f"{path}[{index}]")


def platform_context(source_id: str | None) -> dict[str, Any]:
    """Return safe attribution/coverage/readiness metadata for a source."""
    if not source_id:
        return {
            "registered": False,
            "owner_review": "awaiting-owner-review",
            "publication_state": "blocked",
            "readiness_state": "not-started",
        }
    try:
        from pipeline.platform_registry import source_metadata

        metadata = source_metadata(source_id)
    except Exception:
        metadata = None
    if metadata is None:
        return {
            "registered": False,
            "owner_review": "awaiting-owner-review",
            "publication_state": "blocked",
            "readiness_state": "not-started",
        }
    return {
        "registered": True,
        "country_code": metadata["country_code"],
        "coverage": metadata["coverage"],
        "attribution": metadata["attribution"],
        "readiness": metadata["readiness"],
        "owner_review": metadata["owner_review"],
        "publication": metadata["publication"],
    }


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
    packet_blockers: dict[str, list[str]] = {key: list(values) for key, values in (blockers or {}).items()}
    review_metrics = qa.get("review_metrics", {})
    facility_observation = review_metrics.get("facility_observation", {}) if isinstance(review_metrics, dict) else {}
    classification = review_metrics.get("classification", {}) if isinstance(review_metrics, dict) else {}
    geospatial = review_metrics.get("geospatial", {}) if isinstance(review_metrics, dict) else {}
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
        "review_metrics": review_metrics,
        "facility_observation": facility_observation,
        "classification": classification,
        "geospatial": geospatial,
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
        "platform": platform_context(manifest.get("source_id")),
        "publication_boundary": "awaiting-owner-review; this packet is row-free evidence and cannot approve or promote a release",
        "blockers": packet_blockers,
    }
    if not counts["reconciles"] or not counts["qa_matches_manifest"]:
        packet["blockers"].setdefault("validation", []).append("manifest and QA row counts must reconcile")
    if facility_observation.get("repeated_provisional_facility_groups", 0):
        packet["blockers"].setdefault("identity", []).append("repeated provisional facility groups require source-scoped identity review; rows were not merged")
    if classification.get("review_state_counts", {}).get("review_required", 0) or classification.get("review_state_counts", {}).get("unknown", 0):
        packet["blockers"].setdefault("classification", []).append("classification remains source-preserved or unresolved and requires scoped human review")
    pending_coordinates = sum(
        value for key, value in geospatial.get("coordinate_gate_counts", {}).items()
        if key not in {"passed", "not-required"} and isinstance(value, int)
    )
    if pending_coordinates:
        packet["blockers"].setdefault("geospatial", []).append("coordinate precision/privacy review remains open; coordinate success is not publication approval")
    if packet["gates"]["release_state"] != "not-created" or packet["gates"]["release_promoted"] is not False:
        packet["blockers"].setdefault("release", []).append("private review requires release_state=not-created and release_promoted=false")
    _assert_row_free(packet)
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
