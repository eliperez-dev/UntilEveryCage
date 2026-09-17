"""Shared private-run validation and aggregate QA reporting."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from .adapter_contract import SourceAdapter, SourceArtifact
from pipeline.common.review_metrics import build_private_review_metrics
from pipeline.common.identity import record_key
from .source_lifecycle import atomic_json, validate_private_manifest


class PrivateRunError(ValueError):
    """A private run manifest or report violates the shared contract."""


def _manifest_value(manifest: dict[str, Any], key: str) -> Any:
    if key in manifest:
        return manifest[key]
    acquisition = manifest.get("acquisition")
    if isinstance(acquisition, dict):
        return acquisition.get(key)
    return None


def _record_ids(path: Path) -> set[str | tuple[str, str, str]]:
    if not path.exists():
        return set()
    ids: set[str | tuple[str, str, str]] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        row = json.loads(line)
        if row.get("source_id"):
            ids.add(record_key(row))
            normalized = row.get("normalized", {})
            legacy_value = normalized.get("establishment_id") or normalized.get("recognition_number")
            if isinstance(legacy_value, str) and legacy_value.strip():
                # Alias only for comparison with pre-envelope snapshots.
                ids.add(legacy_value.strip())
        else:
            # Accept older normalized snapshots that predate the shared
            # source-envelope.  They still contribute a conservative delta
            # signal, but cannot be mistaken for a source-qualified key.
            normalized = row.get("normalized", {})
            value = normalized.get("establishment_id") or normalized.get("recognition_number")
            if isinstance(value, str) and value.strip():
                ids.add(value.strip())
    return ids


def validate_manifest(manifest: dict[str, Any]) -> None:
    try:
        validate_private_manifest(manifest)
    except ValueError as exc:
        raise PrivateRunError(str(exc)) from exc


def summarize_private_run(
    manifest: dict[str, Any],
    *,
    normalized_path: str | Path | None = None,
    previous_normalized_path: str | Path | None = None,
    drift_alarms: Iterable[str] = (),
) -> dict[str, Any]:
    """Return a row-free deterministic QA summary for a private run."""
    validate_manifest(manifest)
    disappeared = 0
    if normalized_path is not None and previous_normalized_path is not None:
        disappeared = len(_record_ids(Path(previous_normalized_path)) - _record_ids(Path(normalized_path)))
    provenance = {
        key: _manifest_value(manifest, key)
        for key in ("source_url", "retrieved_at_utc", "publication_date", "effective_date", "sha256", "checksum_sha256", "byte_size", "code_version", "config_version")
        if _manifest_value(manifest, key) is not None
    }
    report = {
        "source_id": manifest["source_id"],
        "adapter_version": manifest.get("adapter_version"),
        "schema_version": manifest.get("schema_version"),
        "provenance": provenance,
        "input_rows": manifest["input_rows"],
        "normalized_rows": manifest["normalized_rows"],
        "quarantined_rows": manifest["quarantined_rows"],
        "coverage_counts": manifest.get("coverage_counts", {}),
        "anomaly_counts": manifest.get("anomaly_counts", {}),
        "drift_alarms": sorted(set(drift_alarms)),
        "disappeared_not_observed_count": disappeared,
        "disappearance_semantics": "not-observed; never inferred as closure",
        "geocoding": manifest.get("geocoding", "unavailable"),
        "release_state": manifest["release_state"],
        "publication_state": manifest.get("publication_state", "private-candidate"),
    }
    return report


def write_private_run_report(
    run_dir: str | Path,
    manifest: dict[str, Any],
    *,
    normalized_path: str | Path | None = None,
    previous_normalized_path: str | Path | None = None,
    drift_alarms: Iterable[str] = (),
) -> dict[str, Any]:
    run_root = Path(run_dir)
    normalized_path = normalized_path or run_root / "normalized" / "records.jsonl"
    quarantine_path = run_root / "quarantined" / "records.jsonl"
    normalized_rows = []
    quarantined_rows = []
    if Path(normalized_path).is_file():
        normalized_rows = [json.loads(line) for line in Path(normalized_path).read_text(encoding="utf-8").splitlines() if line.strip()]
    if quarantine_path.is_file():
        quarantined_rows = [json.loads(line) for line in quarantine_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    report = summarize_private_run(
        manifest,
        normalized_path=normalized_path,
        previous_normalized_path=previous_normalized_path,
        drift_alarms=drift_alarms,
    )
    report["review_metrics"] = build_private_review_metrics(normalized_rows, quarantined_rows)
    atomic_json(Path(run_dir) / "qa.json", report)
    return report


def run_typed_adapter(
    adapter: SourceAdapter,
    raw_path: str | Path,
    run_dir: str | Path,
    artifact: SourceArtifact,
    *,
    previous_normalized_path: str | Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run a typed adapter and emit the shared aggregate QA report."""
    manifest = adapter.run(raw_path, run_dir, artifact)
    report = write_private_run_report(
        run_dir,
        manifest,
        normalized_path=Path(run_dir) / "normalized" / "records.jsonl",
        previous_normalized_path=previous_normalized_path,
    )
    return manifest, report
