"""Bounded private acquisition and shared-lifecycle refresh for FSS Scotland."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pipeline.common.acquisition import AcquisitionError, fetch_source, utc_now
from pipeline.common.orchestrator import run_private_lifecycle
from pipeline.contracts.adapter_contract import SourceArtifact

from .adapter import CONFIG, FssApprovedEstablishmentsAdapter
from .handoff import write_private_handoff


REVIEW_BLOCKERS = {
    "terms": ["FSS indicates OGL v3; exact CSV terms, attribution, and project redistribution review remain human gates."],
    "privacy": ["Address fields and remarks require privacy/safety review; no coordinates are published or geocoded by this adapter."],
    "completeness": ["This lane is Scotland only; FSA England/Wales/Northern Ireland are separate feeds, and a missing source row is not closure."],
    "classification": ["Live activity columns are preserved and classified conservatively; remarks, duplicate approval IDs, unknown activity/status, and privacy-risk addresses quarantine."],
    "coverage": ["The retained live header contract is inspected but current source effective-date and full category coverage remain subject to each bounded refresh."],
}


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, default=list) + "\n", encoding="utf-8")


def _local_metadata(raw_path: Path, *, source_url: str, retrieved_at_utc: str, effective_date: str | None) -> dict[str, Any]:
    raw = raw_path.read_bytes()
    existing = raw_path.parent / "acquisition-metadata.json"
    if existing.exists():
        retained = json.loads(existing.read_text(encoding="utf-8"))
        if retained.get("sha256") == hashlib.sha256(raw).hexdigest() and int(retained.get("byte_size", -1)) == len(raw):
            return retained
    return {
        "acquisition_method": "preserved_local_artifact",
        "source_id": CONFIG["source_id"],
        "artifact": raw_path.name,
        "artifact_path": str(raw_path),
        "requested_url": source_url,
        "final_url": source_url,
        "redirects": [],
        "response_headers": {},
        "requested_at_utc": retrieved_at_utc,
        "retrieved_at_utc": retrieved_at_utc,
        "effective_date": effective_date or "unknown",
        "publication_date": None,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "byte_size": len(raw),
        "adapter_version": CONFIG["adapter_version"],
        "code_version": CONFIG["adapter_version"],
        "config_version": CONFIG["contract_version"],
        "coverage": "Scotland only; FSA England/Wales and Northern Ireland remain separate source scopes",
        "rights_caveat": "OGL v3 indicated by source metadata; project terms/attribution review remains recorded separately",
        "privacy_caveat": "restricted private staging; personal-data and precise-location screening pending",
        "terms_review": "not_required_for_already-preserved-local-artifact",
    }


def _read_previous_ids(path: Path | None) -> set[str]:
    if path is None or not path.exists():
        return set()
    values: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if line:
            normalized = json.loads(line).get("normalized", {})
            value = normalized.get("establishment_id") or normalized.get("approval_number")
            nation = normalized.get("nation") or "Scotland"
            if isinstance(value, str) and value:
                values.add(f"{nation}|{value}")
    return values


def refresh_scotland(
    *,
    run_dir: str | Path,
    raw_path: str | Path | None = None,
    fetch: bool = False,
    source_url: str = CONFIG["source_url"],
    terms_review_path: str | Path | None = None,
    retrieved_at_utc: str | None = None,
    effective_date: str | None = None,
    publication_date: str | None = None,
    mode: str = "dry-run",
    previous_normalized: str | Path | None = None,
    max_bytes: int = 64 * 1024 * 1024,
) -> dict[str, Any]:
    if mode not in {"dry-run", "handoff"}:
        raise AcquisitionError("mode must be dry-run or handoff")
    if fetch == (raw_path is not None):
        raise AcquisitionError("specify exactly one of raw_path or fetch")
    root = Path(run_dir)
    if fetch:
        if terms_review_path is None:
            raise AcquisitionError("terms_review_path is required for network acquisition")
        acquisition = fetch_source(
            source_id=CONFIG["source_id"], url=source_url, output_root=root / "acquisition",
            artifact_name="source.csv", terms_review_path=terms_review_path, max_bytes=max_bytes,
            code_version=CONFIG["adapter_version"], config_version=CONFIG["contract_version"],
            coverage="Scotland only; England/Wales/Northern Ireland remain separate source scopes",
            rights_caveat="OGL v3 indicated; project attribution/terms review is retained with this run",
            privacy_caveat="restricted private staging; personal-data and precise-location screening pending",
            effective_date=effective_date, publication_date=publication_date,
        )
        input_path = Path(acquisition["artifact_path"])
    else:
        input_path = Path(raw_path)  # type: ignore[arg-type]
        if not input_path.is_file():
            raise AcquisitionError(f"raw artifact does not exist: {input_path}")
        retrieved_at_utc = retrieved_at_utc or utc_now()
        acquisition = _local_metadata(input_path, source_url=source_url, retrieved_at_utc=retrieved_at_utc, effective_date=effective_date)
    raw = input_path.read_bytes()
    _write_json(root / "acquisition-metadata.json", acquisition)
    retrieved_at_utc = acquisition["retrieved_at_utc"]
    artifact = SourceArtifact(
        source_url=source_url, retrieved_at_utc=retrieved_at_utc,
        sha256=acquisition["sha256"], byte_size=acquisition["byte_size"],
        publication_date=publication_date or acquisition.get("publication_date"),
        effective_date=effective_date or acquisition.get("effective_date"),
        code_version=CONFIG["adapter_version"], config_version=CONFIG["contract_version"],
        rights_caveat=acquisition.get("rights_caveat"), privacy_caveat=acquisition.get("privacy_caveat"),
        coverage=acquisition.get("coverage"), redirects=tuple(acquisition.get("redirects") or ()),
    )
    adapter = FssApprovedEstablishmentsAdapter()
    result = adapter.parse_bytes(raw)
    current_ids = {
        f"Scotland|{record['normalized'].get('approval_number')}"
        for record in result.accepted
        if record["normalized"].get("approval_number")
    } | {
        f"Scotland|{item['record']['normalized'].get('approval_number')}"
        for item in result.quarantined
        if item["record"]["normalized"].get("approval_number")
    }
    current_ids.discard(None)
    previous_ids = _read_previous_ids(Path(previous_normalized) if previous_normalized else None)
    disappeared = len(previous_ids - current_ids) if previous_ids else 0
    lifecycle = run_private_lifecycle(input_path, root / "lifecycle", artifact, adapter, health_as_of_utc=retrieved_at_utc, previous_normalized_path=previous_normalized, review_blockers=REVIEW_BLOCKERS)
    handoff = None
    if mode == "handoff":
        handoff = write_private_handoff(input_path, root / "handoff", artifact)
    report = {
        "source_id": CONFIG["source_id"], "source_url": source_url,
        "requested_url": acquisition.get("requested_url"), "final_url": acquisition.get("final_url"),
        "redirects": acquisition.get("redirects", []), "retrieved_at_utc": retrieved_at_utc,
        "effective_date": effective_date or acquisition.get("effective_date"),
        "publication_date": publication_date or acquisition.get("publication_date"),
        "sha256": artifact.sha256, "byte_size": artifact.byte_size,
        "code_version": artifact.code_version, "config_version": artifact.config_version,
        "input_rows": len(result.accepted) + len(result.quarantined),
        "normalized_rows": len(result.accepted), "quarantined_rows": len(result.quarantined),
        "coverage_counts": result.coverage_counts or {}, "anomaly_counts": result.anomaly_counts or {},
        "disappeared_not_observed_count": disappeared,
        "disappearance_semantics": "not-observed; never inferred as closure",
        "geocoding": "disabled", "release_state": "not-created",
        "publication_state": "private-candidate", "mode": mode,
        "acquisition_metadata": str(root / "acquisition-metadata.json"),
        "lifecycle_run_dir": str(lifecycle["run_dir"]),
        "health_path": str(Path(lifecycle["run_dir"]) / "source-health.json"),
        "handoff": handoff,
    }
    _write_json(root / "refresh.json", report)
    return {"report": report, "lifecycle": lifecycle, "handoff": handoff}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--raw", type=Path)
    source.add_argument("--fetch", action="store_true")
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--source-url", default=CONFIG["source_url"])
    parser.add_argument("--terms-review", type=Path)
    parser.add_argument("--retrieved-at-utc")
    parser.add_argument("--effective-date")
    parser.add_argument("--publication-date")
    parser.add_argument("--mode", choices=("dry-run", "handoff"), default="dry-run")
    parser.add_argument("--previous-normalized", type=Path)
    parser.add_argument("--max-bytes", type=int, default=64 * 1024 * 1024)
    args = parser.parse_args()
    result = refresh_scotland(
        run_dir=args.run_dir, raw_path=args.raw, fetch=args.fetch, source_url=args.source_url,
        terms_review_path=args.terms_review, retrieved_at_utc=args.retrieved_at_utc,
        effective_date=args.effective_date, publication_date=args.publication_date, mode=args.mode,
        previous_normalized=args.previous_normalized, max_bytes=args.max_bytes,
    )
    print(json.dumps(result["report"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
