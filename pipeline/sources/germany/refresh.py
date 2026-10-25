"""Private live acquisition or preserved-artifact refresh for BVL BLtU."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from pipeline.common.acquisition import utc_now
from pipeline.common.orchestrator import run_private_lifecycle
from pipeline.common.review import write_operator_review_packet
from pipeline.contracts.adapter_contract import SourceArtifact
from pipeline.contracts.candidate_handoff import write_handoff
from pipeline.contracts.source_lifecycle import atomic_json

from .adapter import CONFIG, BltuAdapter
from .acquire import BvlAcquisitionError, fetch as fetch_bltu


class RefreshError(ValueError):
    pass


class GermanyRefreshAdapter:
    """Source-owned bridge for the shared private refresh runner."""
    source_id = CONFIG["source_id"]
    adapter_version = CONFIG["adapter_version"]
    source_kind = "facility_master"

    def refresh(self, *, mode: str, run_dir: Path, artifact: Path | None,
                options: dict[str, Any]) -> dict[str, Any]:
        if mode == "fixture":
            raw = Path(__file__).parent.parent.parent / "germany" / "fixtures" / "synthetic_bltu.csv"
            result = refresh(run_dir=run_dir, raw_path=raw,
                             retrieved_at_utc="2026-09-14T00:00:00Z")
        elif mode == "local-artifact":
            if artifact is None:
                raise RefreshError("local artifact mode requires a preserved BVL export")
            result = refresh(run_dir=run_dir, raw_path=artifact,
                             acquisition_metadata_path=options.get("acquisition_metadata"))
        elif mode == "live-acquisition":
            result = refresh(run_dir=run_dir, fetch=True,
                             output_root=run_dir / "acquisition",
                             run_id=str(options.get("acquisition_run_id") or run_dir.name),
                             timeout_seconds=float(options.get("timeout_seconds", 30)),
                             max_bytes=int(options.get("max_bytes", 16 * 1024 * 1024)))
        else:
            raise RefreshError(f"unsupported Germany refresh mode: {mode}")
        return dict(result["report"])


REVIEW_BLOCKERS = {
    "terms": ["BVL documents public access/export but dataset-specific reuse and redistribution terms remain pending named human confirmation."],
    "privacy": ["Facility addresses may overlap residences or identify people; address and coordinate publication review is pending and geocoding remains disabled."],
    "completeness": ["BLtU is the continuously updated 853/2004 approved-establishment list, not a census of all animal-agriculture facilities; export effective date is unknown until captured."],
    "classification": ["Only the pinned SH/CP activity mapping is accepted; unmapped activity flags quarantine and species/activity interpretation remains source-scoped."],
    "coverage": ["The portal export URL is session/request-specific; a selected current general-list export and its schema must be evidenced per run."],
}


def _local_metadata(path: Path, retrieved: str, metadata_path: str | Path | None = None) -> dict[str, Any]:
    raw = path.read_bytes()
    if metadata_path is not None:
        metadata = json.loads(Path(metadata_path).read_text(encoding="utf-8"))
        if not isinstance(metadata, dict):
            raise RefreshError("acquisition metadata must be an object")
        if str(metadata.get("sha256") or "").lower() != hashlib.sha256(raw).hexdigest() or int(metadata.get("byte_size") or -1) != len(raw):
            raise RefreshError("acquisition metadata does not match the BLtU artifact")
        metadata.setdefault("artifact_path", str(path.resolve()))
        metadata.setdefault("retrieved_at_utc", retrieved)
        metadata.setdefault("requested_at_utc", retrieved)
        metadata.setdefault("effective_date", "unknown")
        metadata.setdefault("publication_date", None)
        metadata.setdefault("redirects", [])
        metadata.setdefault("response_headers", {})
        metadata.setdefault("adapter_version", CONFIG["adapter_version"])
        metadata.setdefault("code_version", CONFIG["adapter_version"])
        metadata.setdefault("config_version", CONFIG["schema_version"])
        metadata.setdefault("coverage", CONFIG["coverage"])
        metadata.setdefault("rights_caveat", CONFIG["terms"])
        metadata.setdefault("privacy_caveat", "private staging; address and coordinate review pending")
        return metadata
    return {"acquisition_method": "assisted_bvl_portal_export", "source_id": CONFIG["source_id"], "artifact": path.name, "artifact_path": str(path.resolve()), "requested_url": CONFIG["source_url"], "final_url": CONFIG["source_url"], "redirects": [], "response_headers": {}, "requested_at_utc": retrieved, "retrieved_at_utc": retrieved, "effective_date": "unknown", "publication_date": None, "sha256": hashlib.sha256(raw).hexdigest(), "byte_size": len(raw), "adapter_version": CONFIG["adapter_version"], "code_version": CONFIG["adapter_version"], "config_version": CONFIG["schema_version"], "coverage": CONFIG["coverage"], "rights_caveat": CONFIG["terms"], "privacy_caveat": "private staging; address and coordinate review pending", "terms_review": "assisted capture; recurring acquisition and redistribution remain human-gated"}


def refresh(*, run_dir: str | Path, raw_path: str | Path | None = None, fetch: bool = False, export_url: str | None = None, terms_review_path: str | Path | None = None, output_root: str | Path = "data/raw", run_id: str | None = None, retrieved_at_utc: str | None = None, timeout_seconds: float = 60, max_bytes: int = 128 * 1024 * 1024, previous_normalized: str | Path | None = None, acquisition_metadata_path: str | Path | None = None) -> dict[str, Any]:
    if fetch == (raw_path is not None):
        raise RefreshError("specify exactly one of --raw or --fetch")
    retrieved = retrieved_at_utc or utc_now()
    if fetch:
        try:
            if export_url:
                raise RefreshError("--export-url is no longer used; acquisition follows the configured public BLtU session")
            metadata = fetch_bltu(output_root=output_root, run_id=run_id or retrieved.replace(":", "").replace("-", ""), timeout_seconds=timeout_seconds, max_bytes=min(max_bytes, 64 * 1024 * 1024))
        except BvlAcquisitionError as error:
            raise RefreshError(str(error)) from error
        input_path = Path(metadata["artifact_path"])
    else:
        input_path = Path(raw_path).resolve()  # type: ignore[arg-type]
        if not input_path.is_file():
            raise RefreshError("BLtU raw artifact does not exist")
        metadata = _local_metadata(input_path, retrieved, acquisition_metadata_path)
    atomic_json(Path(run_dir) / "acquisition-metadata.json", metadata)
    adapter = BltuAdapter()
    raw = input_path.read_bytes()
    artifact = SourceArtifact(source_url=str(metadata.get("final_url") or CONFIG["source_url"]), retrieved_at_utc=str(metadata["retrieved_at_utc"]), sha256=hashlib.sha256(raw).hexdigest(), byte_size=len(raw), publication_date=metadata.get("publication_date"), effective_date=metadata.get("effective_date"), code_version=adapter.adapter_version, config_version=adapter.schema_version, rights_caveat=CONFIG["terms"], privacy_caveat=metadata.get("privacy_caveat"), coverage=CONFIG["coverage"], redirects=tuple(metadata.get("redirects") or ()))
    lifecycle = run_private_lifecycle(input_path, Path(run_dir) / "lifecycle", artifact, adapter, health_as_of_utc=str(metadata["retrieved_at_utc"]), previous_normalized_path=previous_normalized, review_blockers=REVIEW_BLOCKERS)
    if lifecycle.get("status") == "candidate-ready":
        run_root = Path(lifecycle["run_dir"])
        rows = [json.loads(line) for line in (run_root / "normalized" / "records.jsonl").read_text(encoding="utf-8").splitlines() if line]
        write_handoff(run_root / "candidate-handoff", rows, artifact, source_id=adapter.source_id)
        write_operator_review_packet(
            run_root,
            lifecycle["manifest"],
            source_scope=lifecycle["manifest"]["coverage"],
            checks=("review candidate-handoff/normalized/records.jsonl in restricted staging", "confirm the BVL export request/session evidence", "confirm no public release or API promotion"),
            blockers=("candidate is private and human-gated", "dataset-specific reuse and address/coordinate review pending"),
        )
    manifest = lifecycle.get("manifest") or {}
    report = {"source_id": CONFIG["source_id"], "source_url": artifact.source_url, "portal_url": CONFIG["portal_url"], "retrieved_at_utc": artifact.retrieved_at_utc, "sha256": artifact.sha256, "byte_size": artifact.byte_size, "input_rows": manifest.get("input_rows"), "normalized_rows": manifest.get("normalized_rows"), "quarantined_rows": manifest.get("quarantined_rows"), "schema_status": manifest.get("schema_status"), "schema_fingerprint": manifest.get("schema_fingerprint"), "drift_alarms": [], "disappearance_semantics": "not-observed; never inferred as closure", "geocoding": "disabled", "release_state": "not-created", "publication_state": "private-candidate", "publication_eligibility": "blocked", "lifecycle_status": lifecycle.get("status"), "lifecycle_run_dir": lifecycle.get("run_dir")}
    atomic_json(Path(run_dir) / "refresh.json", report)
    return {"report": report, "lifecycle": lifecycle}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--raw", type=Path)
    source.add_argument("--fetch", action="store_true")
    parser.add_argument("--export-url", help=argparse.SUPPRESS)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=Path("data/raw"))
    parser.add_argument("--run-id")
    parser.add_argument("--retrieved-at-utc")
    parser.add_argument("--timeout-seconds", type=float, default=30)
    parser.add_argument("--max-bytes", type=int, default=16 * 1024 * 1024)
    parser.add_argument("--previous-normalized", type=Path)
    parser.add_argument("--acquisition-metadata", type=Path, help="row-free JSON sidecar for a browser-assisted export")
    args = parser.parse_args()
    try:
        result = refresh(run_dir=args.run_dir, raw_path=args.raw, fetch=args.fetch, export_url=args.export_url, output_root=args.output_root, run_id=args.run_id, retrieved_at_utc=args.retrieved_at_utc, timeout_seconds=args.timeout_seconds, max_bytes=args.max_bytes, previous_normalized=args.previous_normalized, acquisition_metadata_path=args.acquisition_metadata)
    except (OSError, RefreshError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, sort_keys=True))
        return 2
    print(json.dumps(result["report"], sort_keys=True))
    return 0 if result["report"]["lifecycle_status"] == "candidate-ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
