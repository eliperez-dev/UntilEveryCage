"""Fresh/private refresh and candidate handoff for Scottish aquaculture sites."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from pipeline.common.orchestrator import run_private_lifecycle
from pipeline.contracts.adapter_contract import SourceArtifact
from pipeline.contracts.candidate_handoff import write_handoff
from pipeline.contracts.source_lifecycle import read_jsonl

from .acquire import DEFAULT_MAX_BYTES, fetch
from .adapter import ADAPTER_VERSION, ATTRIBUTION, CATALOG_URL, COVERAGE, LICENSE, LICENSE_URL, SCHEMA_VERSION, SOURCE_ID, ScotlandAquacultureAdapter, parse_geojson

REVIEW_BLOCKERS = {
    "terms": ["OGL v3 attribution is identified in the publisher catalog; exact source-specific operator approval is required before every live acquisition."],
    "privacy": ["Source points and site names require location-precision/privacy review before any public map or export."],
    "coverage": ["The catalog layer includes recreational fishery sites; these are quarantined. This snapshot is not a census of all Scottish animal facilities."],
    "classification": ["Only source site types Fish and Shellfish are normalized; statuses and source facility/species/stage codes are preserved."],
}


class ScotlandAquacultureRefreshAdapter:
    """Shared runner hook; acquisition and row semantics remain source-owned."""

    source_id = SOURCE_ID
    adapter_version = ADAPTER_VERSION
    source_kind = "facility_master"

    def acquire(self, *, run_dir: Path, options: Mapping[str, Any]) -> Mapping[str, Any]:
        review_paths = options.get("terms_review_paths")
        review = review_paths.get(SOURCE_ID) if isinstance(review_paths, Mapping) else None
        review = review or options.get("terms_review_path")
        if not review:
            raise ValueError("source-specific terms review is required for live acquisition")
        return fetch(output_root=run_dir / "acquisition",
                     run_id=str(options.get("acquisition_run_id") or run_dir.name),
                     terms_review_path=Path(str(review)),
                     timeout_seconds=float(options.get("timeout_seconds", 60)),
                     max_bytes=int(options.get("max_bytes", DEFAULT_MAX_BYTES)))

    def refresh(self, *, mode: str, run_dir: Path, artifact: Path | None,
                options: Mapping[str, Any]) -> Mapping[str, Any]:
        if mode == "live-acquisition":
            raise ValueError("shared runner must preserve acquisition before source refresh")
        if artifact is None or not artifact.exists():
            raise FileNotFoundError("preserved aquaculture GeoJSON artifact is required")
        facts = options.get("acquisition")
        if not isinstance(facts, Mapping):
            raise ValueError("acquisition provenance is required for source refresh")
        retrieved = str(facts.get("retrieved_at_utc") or "")
        checksum = str(facts.get("artifact_sha256") or facts.get("sha256") or "")
        byte_size = facts.get("artifact_byte_size", facts.get("byte_size"))
        if not retrieved or not checksum or not isinstance(byte_size, int):
            raise ValueError("acquisition provenance is incomplete")
        source_artifact = SourceArtifact(
            source_url=CATALOG_URL, retrieved_at_utc=retrieved, sha256=checksum, byte_size=byte_size,
            publication_date=facts.get("publication_date"), effective_date=facts.get("effective_date"),
            code_version=ADAPTER_VERSION, config_version=SCHEMA_VERSION,
            rights_caveat=f"{LICENSE}; {LICENSE_URL}; {ATTRIBUTION}",
            privacy_caveat="private staging; source location precision and publication eligibility require separate review",
            coverage=COVERAGE,
        )
        lifecycle = _run_lifecycle(artifact, run_dir, source_artifact)
        manifest = lifecycle.get("manifest") or {}
        handoff: dict[str, Any] = {}
        if lifecycle.get("status") == "candidate-ready":
            lifecycle_root = Path(lifecycle["run_dir"])
            rows = read_jsonl(lifecycle_root / "normalized" / "records.jsonl")
            handoff = write_handoff(run_dir / "candidate-handoff", rows, source_artifact,
                                    source_id=SOURCE_ID, emit_graph_candidates=True)
        return {
            "lifecycle_status": lifecycle.get("status"),
            "publication_state": lifecycle.get("publication_state", "unchanged"),
            "input_rows": manifest.get("input_rows", 0),
            "normalized_rows": manifest.get("normalized_rows", 0),
            "quarantined_rows": manifest.get("quarantined_rows", 0),
            "candidate_handoff": bool(handoff),
            "candidate_observation_rows": handoff.get("normalized_rows", 0),
            "candidate_handoff_sha256": handoff.get("normalized_sha256"),
            "source_title": "Scottish Government finfish and shellfish aquaculture sites",
            "retrieved_at_utc": retrieved, "source_license": LICENSE,
            "source_attribution": ATTRIBUTION, "source_canonical_url": CATALOG_URL,
            "schema_fingerprint": manifest.get("schema_fingerprint"),
            "quarantine_reasons": manifest.get("anomaly_counts", {}),
            "geocoding": "disabled", "publication": "not-created",
        }


def _run_lifecycle(artifact: Path, run_dir: Path, source_artifact: SourceArtifact) -> dict[str, Any]:
    return run_private_lifecycle(artifact, run_dir / "lifecycle", source_artifact,
                                 ScotlandAquacultureAdapter(),
                                 health_as_of_utc=source_artifact.retrieved_at_utc,
                                 review_blockers=REVIEW_BLOCKERS)


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def refresh(*, run_dir: str | Path, raw_path: str | Path | None = None, fetch_live: bool = False,
            terms_review_path: str | Path | None = None, output_root: str | Path | None = None,
            run_id: str | None = None, timeout_seconds: float = 60.0,
            max_bytes: int = DEFAULT_MAX_BYTES, mode: str = "handoff") -> dict[str, Any]:
    if fetch_live == (raw_path is not None):
        raise ValueError("specify exactly one of fetch_live or raw_path")
    if mode not in {"dry-run", "handoff"}:
        raise ValueError("mode must be dry-run or handoff")
    root = Path(run_dir)
    if fetch_live:
        if terms_review_path is None:
            raise ValueError("--terms-review is required for live acquisition")
        acquisition = fetch(output_root=Path(output_root or root / "acquisition"),
                            run_id=run_id or root.name, terms_review_path=Path(terms_review_path),
                            timeout_seconds=timeout_seconds, max_bytes=max_bytes)
        input_path = Path(acquisition["artifact_path"])
    else:
        input_path = Path(raw_path)  # type: ignore[arg-type]
        raw = input_path.read_bytes()
        source_timestamp = parse_geojson(raw)["timeStamp"]
        acquisition = {"acquisition_method": "preserved_local_artifact", "source_id": SOURCE_ID,
                       "source_url": CATALOG_URL, "requested_url": CATALOG_URL, "final_url": CATALOG_URL,
                       "retrieved_at_utc": _now(), "effective_date": source_timestamp,
                       "source_timestamp_utc": source_timestamp, "publication_date": None,
                       "sha256": hashlib.sha256(raw).hexdigest(), "byte_size": len(raw),
                       "coverage": COVERAGE, "rights_caveat": f"{LICENSE}; attribution required",
                       "privacy_caveat": "private staging; source location precision and publication eligibility require separate review"}
    raw = input_path.read_bytes()
    acquired_at = str(acquisition.get("retrieved_at_utc") or _now())
    artifact = SourceArtifact(
        source_url=CATALOG_URL, retrieved_at_utc=acquired_at,
        sha256=str(acquisition["sha256"]), byte_size=int(acquisition["byte_size"]),
        publication_date=acquisition.get("publication_date"), effective_date=acquisition.get("effective_date"),
        code_version=ADAPTER_VERSION, config_version=SCHEMA_VERSION,
        rights_caveat=f"{LICENSE}; {LICENSE_URL}; attribution required",
        privacy_caveat="private staging; source location precision and publication eligibility require separate review",
        coverage=COVERAGE)
    _write_json(root / "acquisition-summary.json", {
        "source_id": SOURCE_ID, "catalog_url": CATALOG_URL,
        "retrieved_at_utc": acquired_at, "effective_date": acquisition.get("effective_date", "unknown"),
        "sha256": artifact.sha256, "byte_size": artifact.byte_size,
        "acquisition_method": acquisition.get("acquisition_method", "preserved_local_artifact"),
        "content_type": acquisition.get("response_headers", {}).get("Content-Type"),
    })
    adapter = ScotlandAquacultureAdapter()
    parsed = adapter.parse_bytes(raw)
    lifecycle = run_private_lifecycle(input_path, root / "lifecycle", artifact, adapter,
                                      health_as_of_utc=acquired_at, review_blockers=REVIEW_BLOCKERS)
    lifecycle_root = Path(lifecycle["run_dir"])
    handoff = None
    if mode == "handoff":
        rows = read_jsonl(lifecycle_root / "normalized" / "records.jsonl")
        handoff = adapter.write_candidate_handoff(lifecycle_root / "candidate-handoff", artifact, rows)
    report = {
        "source_id": SOURCE_ID, "catalog_url": CATALOG_URL,
        "retrieved_at_utc": acquired_at, "sha256": artifact.sha256, "byte_size": artifact.byte_size,
        "effective_date": acquisition.get("effective_date", "unknown"),
        "input_sites": parsed["input_rows"], "normalized_sites": parsed["normalized_rows"],
        "quarantined_sites": parsed["quarantined_rows"],
        "source_feature_rows": parsed["source_feature_rows"],
        "source_feature_type_counts": parsed["source_feature_type_counts"],
        "site_type_counts": parsed["site_type_counts"], "anomaly_counts": parsed["anomaly_counts"],
        "schema_fingerprint": parsed["schema_fingerprint"], "geocoding": "disabled",
        "publication_state": "private-candidate", "release_state": "not-created", "mode": mode,
        "lifecycle_run_dir": str(lifecycle["run_dir"]),
        "health_path": str(lifecycle_root / "source-health.json"), "handoff": handoff,
    }
    _write_json(root / "refresh-summary.json", report)
    return {"report": report, "lifecycle": lifecycle, "handoff": handoff}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--raw", type=Path)
    source.add_argument("--fetch", action="store_true")
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--terms-review", type=Path)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--run-id")
    parser.add_argument("--timeout-seconds", type=float, default=60)
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    parser.add_argument("--mode", choices=("dry-run", "handoff"), default="handoff")
    args = parser.parse_args()
    result = refresh(run_dir=args.run_dir, raw_path=args.raw, fetch_live=args.fetch,
                     terms_review_path=args.terms_review, output_root=args.output_root,
                     run_id=args.run_id, timeout_seconds=args.timeout_seconds,
                     max_bytes=args.max_bytes, mode=args.mode)
    print(json.dumps(result["report"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
