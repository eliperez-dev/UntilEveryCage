"""Build conservative, row-free health snapshots for private source runs."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class HealthEvidenceError(ValueError):
    """Evidence is missing, inconsistent, or contains a prohibited payload."""


HEALTH_SCHEMA_VERSION = "1.0"
HEALTH_STATES = {"not-run", "blocked", "failed", "degraded", "private-validated"}
_FORBIDDEN_KEYS = {"source_values", "raw_fields", "address", "coordinates", "latitude", "longitude"}


def _read_json(path: Path, label: str) -> dict[str, Any]:
    if not path.exists():
        raise HealthEvidenceError(f"missing {label}: {path.name}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HealthEvidenceError(f"invalid {label}: {path.name}") from exc
    if not isinstance(value, dict):
        raise HealthEvidenceError(f"{label} must be an object: {path.name}")
    return value


def _assert_row_free(value: Any, path: str = "evidence") -> None:
    if isinstance(value, dict):
        leaked = sorted(set(value) & _FORBIDDEN_KEYS)
        if leaked:
            raise HealthEvidenceError(f"prohibited payload in {path}: {', '.join(leaked)}")
        for key, child in value.items():
            _assert_row_free(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _assert_row_free(child, f"{path}[{index}]")


def _required_counts(value: dict[str, Any], label: str) -> tuple[int, int, int]:
    required = ("input_rows", "normalized_rows", "quarantined_rows")
    if any(key not in value for key in required):
        raise HealthEvidenceError(f"{label} is missing row counts")
    counts = tuple(value[key] for key in required)
    if any(not isinstance(count, int) or count < 0 for count in counts):
        raise HealthEvidenceError(f"{label} has invalid row counts")
    if counts[0] != counts[1] + counts[2]:
        raise HealthEvidenceError(f"{label} row counts do not reconcile")
    return counts


def _parse_time(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise HealthEvidenceError(f"missing {label}")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HealthEvidenceError(f"invalid {label}") from exc
    if parsed.tzinfo is None:
        raise HealthEvidenceError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def build_health_snapshot(
    run_dir: str | Path,
    *,
    as_of_utc: str | None = None,
    stale_after_hours: int = 24 * 7,
    import_evidence_path: str | Path | None = None,
) -> dict[str, Any]:
    """Build a deterministic aggregate snapshot from private run evidence."""
    if stale_after_hours <= 0:
        raise HealthEvidenceError("stale_after_hours must be positive")
    root = Path(run_dir)
    manifest = _read_json(root / "manifest.json", "manifest")
    qa = _read_json(root / "qa.json", "QA report")
    run_status = _read_json(root / "run-status.json", "run status")
    import_evidence = None
    if import_evidence_path is not None:
        import_evidence = _read_json(Path(import_evidence_path), "import evidence")
    _assert_row_free(qa, "qa")
    _assert_row_free(run_status, "run-status")
    if import_evidence is not None:
        _assert_row_free(import_evidence, "import")

    source_id = manifest.get("source_id")
    if not isinstance(source_id, str) or not source_id:
        raise HealthEvidenceError("manifest source_id is missing")
    if qa.get("source_id") != source_id:
        raise HealthEvidenceError("manifest and QA source_id differ")
    manifest_counts = _required_counts(manifest, "manifest")
    qa_counts = _required_counts(qa, "QA report")
    if manifest_counts != qa_counts:
        raise HealthEvidenceError("manifest and QA row counts differ")
    if manifest.get("release_state") != "not-created":
        raise HealthEvidenceError("private health cannot assess a released run")
    if manifest.get("publication_state") not in {"private-candidate", "not-staged", None}:
        raise HealthEvidenceError("manifest publication state is not private")
    if run_status.get("release_promoted") is not False:
        raise HealthEvidenceError("run status must explicitly keep release promotion false")
    if run_status.get("publication_state") not in {"human-gate-required", "terms-gate-blocked", "unchanged", "private-candidate"}:
        raise HealthEvidenceError("run status publication state is not restricted")

    retrieved = _parse_time(
        manifest.get("retrieved_at_utc") or (manifest.get("acquisition") or {}).get("retrieved_at_utc"),
        "retrieved_at_utc",
    )
    as_of = _parse_time(as_of_utc, "as_of_utc") if as_of_utc else datetime.now(timezone.utc)
    age_hours = max(0.0, (as_of - retrieved).total_seconds() / 3600)
    raw_drift_alarms = qa.get("drift_alarms", [])
    if not isinstance(raw_drift_alarms, list) or any(not isinstance(item, str) for item in raw_drift_alarms):
        raise HealthEvidenceError("drift_alarms must contain strings")
    drift_alarms = sorted(set(raw_drift_alarms))
    run_state = run_status.get("status")
    if run_state == "failed":
        health_state = "failed"
    elif run_state in {"staged-restricted", "blocked"}:
        health_state = "blocked"
    elif drift_alarms or age_hours > stale_after_hours:
        health_state = "degraded"
    elif run_state in {"candidate-ready", "success", "private-candidate"}:
        health_state = "private-validated"
    else:
        health_state = "not-run"

    if import_evidence is not None:
        if import_evidence.get("source_id") != source_id:
            raise HealthEvidenceError("manifest and import source_id differ")
        imported = import_evidence.get("imported_rows")
        if not isinstance(imported, int) or imported < 0 or imported > manifest_counts[1]:
            raise HealthEvidenceError("imported_rows is inconsistent with normalized_rows")
        if import_evidence.get("public_exposure") is not False:
            raise HealthEvidenceError("import evidence must set public_exposure=false")
        if import_evidence.get("publication_eligible_rows") != 0:
            raise HealthEvidenceError("private import must have zero publication-eligible rows")
        if import_evidence.get("default_visible_rows") != 0:
            raise HealthEvidenceError("private import must have zero default-visible rows")

    provenance = {
        key: manifest.get(key)
        for key in ("source_url", "retrieved_at_utc", "publication_date", "effective_date", "sha256", "checksum_sha256", "byte_size", "code_version", "config_version", "redirects")
        if manifest.get(key) is not None
    }
    snapshot = {
        "schema_version": HEALTH_SCHEMA_VERSION,
        "source_id": source_id,
        "health_state": health_state,
        "private_validation": True,
        "public_exposure": False,
        "publication_eligibility": "blocked",
        "provenance": provenance,
        "freshness": {
            "retrieved_at_utc": retrieved.isoformat().replace("+00:00", "Z"),
            "as_of_utc": as_of.isoformat().replace("+00:00", "Z"),
            "age_hours": round(age_hours, 3),
            "stale_after_hours": stale_after_hours,
            "state": "stale" if age_hours > stale_after_hours else "current",
        },
        "effective_date": {
            "value": manifest.get("effective_date"),
            "state": "known" if manifest.get("effective_date") else "unknown",
        },
        "run": {
            "status": run_state,
            "release_state": manifest.get("release_state"),
            "publication_state": manifest.get("publication_state"),
            "drift_alarms": drift_alarms,
            "input_rows": manifest_counts[0],
            "normalized_rows": manifest_counts[1],
            "quarantined_rows": manifest_counts[2],
            "disappeared_not_observed_count": qa.get("disappeared_not_observed_count", 0),
            "disappearance_semantics": "not-observed; never inferred as closure",
        },
        "import": {
            "state": "not-run" if import_evidence is None else import_evidence.get("status", "completed"),
            "imported_rows": None if import_evidence is None else import_evidence.get("imported_rows"),
            "rerun_imported_rows": None if import_evidence is None else import_evidence.get("rerun_imported_rows"),
            "default_visible_rows": None if import_evidence is None else import_evidence.get("default_visible_rows"),
            "publication_eligible_rows": None if import_evidence is None else import_evidence.get("publication_eligible_rows"),
        },
    }
    if health_state not in HEALTH_STATES:
        raise HealthEvidenceError("unknown health state")
    return snapshot


def write_health_snapshot(output_path: str | Path, snapshot: dict[str, Any]) -> None:
    _atomic_json(Path(output_path), snapshot)
