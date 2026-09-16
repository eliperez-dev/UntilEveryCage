"""Repeatable private acquisition, drift QA, and FSA monthly handoff."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from pipeline.contracts.adapter_contract import SourceArtifact
from pipeline.common.acquisition import AcquisitionError, fetch_source, utc_now
from pipeline.common.orchestrator import run_private_lifecycle

from .adapter import CONFIG, FsaApprovedEstablishmentsAdapter, _csv
from .handoff import write_private_monthly_handoff


REVIEW_BLOCKERS = {
    "terms": ["UK OGL v3 is indicated by the catalogue; attribution, national-scope terms, and project redistribution review remain separate gates."],
    "privacy": ["AddressWithheld rows and precise X/Y coordinates require privacy classification; withheld addresses remain suppressed and geocoding is disabled."],
    "completeness": ["The monthly feed covers England and Wales in this adapter; Northern Ireland remains a separate authority/source scope and disappearance is not closure."],
    "classification": ["Activity values are source-native and mapped conservatively; unknown activity, status, authority/nation mismatch, duplicates, and remarks quarantine."],
    "coverage": ["The inspected monthly schema/fingerprint and baseline are evidence for the retained snapshot only; live drift and source effective-date semantics require repeatable refresh review."],
}


class RefreshError(ValueError):
    """The source refresh cannot safely continue."""


def _header_fingerprint(raw: bytes) -> tuple[str, int]:
    headers, _, _ = _csv(raw)
    return hashlib.sha256(json.dumps(headers, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest(), len(headers)


def _read_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    ids: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        normalized = json.loads(line).get("normalized", {})
        value = normalized.get("establishment_id")
        if isinstance(value, str) and value:
            ids.add(value)
    return ids


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, default=list) + "\n", encoding="utf-8")


def _local_acquisition_metadata(path: Path, *, source_url: str, retrieved_at_utc: str, effective_date: str | None) -> dict[str, Any]:
    raw = path.read_bytes()
    existing = path.parent / "acquisition-metadata.json"
    if existing.exists():
        retained = json.loads(existing.read_text(encoding="utf-8"))
        if retained.get("sha256") == hashlib.sha256(raw).hexdigest() and int(retained.get("byte_size", -1)) == len(raw):
            return retained
    return {
        "acquisition_method": "preserved_local_artifact", "source_id": CONFIG["source_id"],
        "artifact": path.name, "artifact_path": str(path), "requested_url": source_url,
        "final_url": source_url, "redirects": [], "response_headers": {},
        "requested_at_utc": retrieved_at_utc, "retrieved_at_utc": retrieved_at_utc,
        "effective_date": effective_date or "unknown", "publication_date": None,
        "sha256": hashlib.sha256(raw).hexdigest(), "byte_size": len(raw),
        "code_version": CONFIG["adapter_version"], "config_version": CONFIG["contract_version"],
        "coverage": "England and Wales profile; Northern Ireland remains a separate source scope",
        "rights_caveat": "OGL v3 indicated by catalogue; project terms/attribution review remains recorded separately",
        "privacy_caveat": "restricted private staging; privacy and coordinate review pending",
        "terms_review": "not_required_for_already-preserved-local-artifact",
    }


def refresh_monthly(
    *,
    run_dir: str | Path,
    raw_path: str | Path | None = None,
    fetch: bool = False,
    source_url: str = CONFIG["source_url"],
    retrieved_at_utc: str | None = None,
    effective_date: str | None = None,
    code_version: str = CONFIG["adapter_version"],
    config_version: str = CONFIG["contract_version"],
    mode: str = "dry-run",
    previous_normalized: str | Path | None = None,
    bounded_sample: bool = False,
    terms_review_path: str | Path | None = None,
    max_bytes: int = 64 * 1024 * 1024,
) -> dict[str, Any]:
    """Run a private refresh; ``mode=handoff`` also emits candidate-handoff-v1."""
    if mode not in {"dry-run", "handoff"}:
        raise RefreshError("mode must be dry-run or handoff")
    if fetch == (raw_path is not None):
        raise RefreshError("specify exactly one of raw_path or fetch")
    root = Path(run_dir)
    if fetch:
        if terms_review_path is None:
            raise RefreshError("terms_review_path is required for network acquisition")
        try:
            acquisition = fetch_source(
                source_id=CONFIG["source_id"], url=source_url, output_root=root / "acquisition",
                artifact_name="source.csv", terms_review_path=terms_review_path, max_bytes=max_bytes,
                code_version=CONFIG["adapter_version"], config_version=CONFIG["contract_version"],
                coverage="England and Wales profile; Northern Ireland remains a separate source scope",
                rights_caveat="OGL v3 indicated by catalogue; project terms/attribution review is retained with this run",
                privacy_caveat="restricted private staging; privacy and coordinate review pending",
                effective_date=effective_date,
            )
        except AcquisitionError as exc:
            raise RefreshError(str(exc)) from exc
        effective_date = effective_date or acquisition.get("effective_date")
        input_path = Path(acquisition["artifact_path"])
        raw = input_path.read_bytes()
    else:
        input_path = Path(raw_path)  # type: ignore[arg-type]
        raw = input_path.read_bytes()
    retrieved_at_utc = retrieved_at_utc or utc_now()
    effective_date = effective_date or "unknown"
    if not fetch:
        acquisition = _local_acquisition_metadata(input_path, source_url=source_url, retrieved_at_utc=retrieved_at_utc, effective_date=effective_date)
    _write_json(root / "acquisition-metadata.json", acquisition)
    adapter = FsaApprovedEstablishmentsAdapter()
    result = adapter.parse_bytes(raw)
    if result.profile != "monthly":
        raise RefreshError("UK refresh requires the monthly FSA profile")
    fingerprint, columns = _header_fingerprint(raw)
    alarms: list[str] = []
    expected = CONFIG.get("monthly_schema_fingerprint")
    if expected and fingerprint != expected and not bounded_sample:
        alarms.append("schema_fingerprint_changed")
    baseline = int(CONFIG["monthly_baseline_rows"])
    if not bounded_sample and abs(len(result.accepted) + len(result.quarantined) - baseline) > max(100, baseline // 10):
        alarms.append("input_row_count_changed")
    previous_ids = _read_ids(Path(previous_normalized)) if previous_normalized else set()
    current_ids = {
        r["normalized"].get("establishment_id")
        for r in result.accepted
    } | {
        item["record"]["normalized"].get("establishment_id")
        for item in result.quarantined
    }
    current_ids.discard(None)
    disappeared = len(previous_ids - current_ids) if previous_ids else 0
    artifact = SourceArtifact(
        source_url=source_url,
        retrieved_at_utc=retrieved_at_utc,
        sha256=hashlib.sha256(raw).hexdigest(),
        byte_size=len(raw),
        effective_date=effective_date,
        code_version=code_version,
        config_version=config_version,
        rights_caveat=acquisition.get("rights_caveat") or "metadata-indicated-open-government-licence-v3-pending-project-review",
        privacy_caveat=acquisition.get("privacy_caveat") or "restricted-private-staging; privacy and coordinate review pending",
        coverage=acquisition.get("coverage") or "England and Wales profile; Northern Ireland remains a separate source scope",
        redirects=tuple(acquisition.get("redirects") or ()),
    )
    if alarms and mode == "handoff":
        raise RefreshError("refresh drift alarm blocks handoff: " + ", ".join(alarms))
    handoff = None
    if mode == "handoff":
        handoff = write_private_monthly_handoff(input_path, root / "handoff", artifact)
    lifecycle = run_private_lifecycle(input_path, root / "lifecycle", artifact, adapter, health_as_of_utc=retrieved_at_utc, previous_normalized_path=previous_normalized, review_blockers=REVIEW_BLOCKERS)
    report = {
        "source_url": source_url,
        "retrieved_at_utc": retrieved_at_utc,
        "effective_date": effective_date,
        "sha256": artifact.sha256,
        "byte_size": artifact.byte_size,
        "code_version": code_version,
        "config_version": config_version,
        "profile": result.profile,
        "schema_fingerprint": fingerprint,
        "column_count": columns,
        "input_rows": len(result.accepted) + len(result.quarantined),
        "normalized_rows": len(result.accepted),
        "quarantined_rows": len(result.quarantined),
        "coverage_counts": result.coverage_counts or {},
        "anomaly_counts": result.anomaly_counts or {},
        "drift_alarms": alarms,
        "disappeared_not_observed_count": disappeared,
        "disappearance_semantics": "not-observed; never inferred as closure",
        "geocoding": "disabled",
        "mode": mode,
        "release_state": "not-created",
        "publication_state": "private-candidate" if handoff else "not-staged",
        "requested_url": acquisition.get("requested_url"),
        "final_url": acquisition.get("final_url"),
        "redirects": acquisition.get("redirects", []),
        "acquisition_metadata": str(root / "acquisition-metadata.json"),
        "lifecycle_run_dir": lifecycle.get("run_dir"),
        "health_path": str(Path(lifecycle["run_dir"]) / "source-health.json"),
    }
    _write_json(root / "refresh.json", report)
    return {"report": report, "handoff": handoff}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--raw", type=Path)
    source.add_argument("--fetch", action="store_true")
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--source-url", default=CONFIG["source_url"])
    parser.add_argument("--retrieved-at-utc")
    parser.add_argument("--effective-date")
    parser.add_argument("--code-version", default=CONFIG["adapter_version"])
    parser.add_argument("--config-version", default=CONFIG["contract_version"])
    parser.add_argument("--mode", choices=("dry-run", "handoff"), default="dry-run")
    parser.add_argument("--previous-normalized", type=Path)
    parser.add_argument("--bounded-sample", action="store_true")
    parser.add_argument("--terms-review", type=Path)
    parser.add_argument("--max-bytes", type=int, default=64 * 1024 * 1024)
    args = parser.parse_args()
    result = refresh_monthly(
        run_dir=args.run_dir, raw_path=args.raw, fetch=args.fetch, source_url=args.source_url,
        retrieved_at_utc=args.retrieved_at_utc, effective_date=args.effective_date,
        code_version=args.code_version, config_version=args.config_version, mode=args.mode,
        previous_normalized=args.previous_normalized, bounded_sample=args.bounded_sample,
        terms_review_path=args.terms_review, max_bytes=args.max_bytes,
    )
    print(json.dumps(result["report"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
