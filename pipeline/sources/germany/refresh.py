"""Assisted/private refresh for a BVL BLtU CSV export."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from pipeline.common.acquisition import AcquisitionError, fetch_source, utc_now
from pipeline.common.orchestrator import run_private_lifecycle
from pipeline.contracts.adapter_contract import SourceArtifact
from pipeline.contracts.source_lifecycle import atomic_json

from .adapter import CONFIG, BltuAdapter


class RefreshError(ValueError):
    pass


REVIEW_BLOCKERS = {
    "terms": ["BVL documents public access/export but dataset-specific reuse and redistribution terms remain pending named human confirmation."],
    "privacy": ["Facility addresses may overlap residences or identify people; address and coordinate publication review is pending and geocoding remains disabled."],
    "completeness": ["BLtU is the continuously updated 853/2004 approved-establishment list, not a census of all animal-agriculture facilities; export effective date is unknown until captured."],
    "classification": ["Only the pinned SH/CP activity mapping is accepted; unmapped activity flags quarantine and species/activity interpretation remains source-scoped."],
    "coverage": ["The portal export URL is session/request-specific; a selected current general-list export and its schema must be evidenced per run."],
}


def _local_metadata(path: Path, retrieved: str) -> dict[str, Any]:
    raw = path.read_bytes()
    return {"acquisition_method": "assisted_bvl_portal_export", "source_id": CONFIG["source_id"], "artifact": path.name, "artifact_path": str(path.resolve()), "requested_url": CONFIG["source_url"], "final_url": CONFIG["source_url"], "redirects": [], "response_headers": {}, "requested_at_utc": retrieved, "retrieved_at_utc": retrieved, "effective_date": "unknown", "publication_date": None, "sha256": hashlib.sha256(raw).hexdigest(), "byte_size": len(raw), "adapter_version": CONFIG["adapter_version"], "code_version": CONFIG["adapter_version"], "config_version": CONFIG["schema_version"], "coverage": CONFIG["coverage"], "rights_caveat": CONFIG["terms"], "privacy_caveat": "private staging; address and coordinate review pending", "terms_review": "assisted capture; recurring acquisition and redistribution remain human-gated"}


def refresh(*, run_dir: str | Path, raw_path: str | Path | None = None, fetch: bool = False, export_url: str | None = None, terms_review_path: str | Path | None = None, output_root: str | Path = "data/raw", run_id: str | None = None, retrieved_at_utc: str | None = None, timeout_seconds: float = 60, max_bytes: int = 128 * 1024 * 1024, previous_normalized: str | Path | None = None) -> dict[str, Any]:
    if fetch == (raw_path is not None):
        raise RefreshError("specify exactly one of --raw or --fetch")
    retrieved = retrieved_at_utc or utc_now()
    if fetch:
        if not export_url:
            raise RefreshError("--export-url is required: select the current CSV/XLS export in the BVL portal")
        if not export_url.startswith(("https://www.bvl.bund.de/", "https://gis.bvl.bund.de/")):
            raise RefreshError("BLtU export URL must be an HTTPS BVL host")
        if terms_review_path is None:
            raise RefreshError("--terms-review is required with --fetch")
        try:
            metadata = fetch_source(source_id=CONFIG["source_id"], url=export_url, output_root=Path(output_root), artifact_name="bltu-export.csv", run_id=run_id, timeout_seconds=timeout_seconds, max_bytes=max_bytes, terms_review_path=terms_review_path, code_version=CONFIG["adapter_version"], config_version=CONFIG["schema_version"], coverage=CONFIG["coverage"], rights_caveat=CONFIG["terms"], privacy_caveat="private staging; address and coordinate review pending", allowed_content_types=("text/csv", "application/csv", "application/vnd.ms-excel", "application/octet-stream"))
        except AcquisitionError as error:
            raise RefreshError(str(error)) from error
        input_path = Path(metadata["artifact_path"])
    else:
        input_path = Path(raw_path).resolve()  # type: ignore[arg-type]
        if not input_path.is_file():
            raise RefreshError("BLtU raw artifact does not exist")
        metadata = _local_metadata(input_path, retrieved)
    atomic_json(Path(run_dir) / "acquisition-metadata.json", metadata)
    adapter = BltuAdapter()
    raw = input_path.read_bytes()
    artifact = SourceArtifact(source_url=str(metadata.get("final_url") or CONFIG["source_url"]), retrieved_at_utc=str(metadata["retrieved_at_utc"]), sha256=hashlib.sha256(raw).hexdigest(), byte_size=len(raw), publication_date=metadata.get("publication_date"), effective_date=metadata.get("effective_date"), code_version=adapter.adapter_version, config_version=adapter.schema_version, rights_caveat=CONFIG["terms"], privacy_caveat=metadata.get("privacy_caveat"), coverage=CONFIG["coverage"], redirects=tuple(metadata.get("redirects") or ()))
    lifecycle = run_private_lifecycle(input_path, Path(run_dir) / "lifecycle", artifact, adapter, health_as_of_utc=str(metadata["retrieved_at_utc"]), previous_normalized_path=previous_normalized, review_blockers=REVIEW_BLOCKERS)
    manifest = lifecycle.get("manifest") or {}
    report = {"source_id": CONFIG["source_id"], "source_url": artifact.source_url, "portal_url": CONFIG["portal_url"], "retrieved_at_utc": artifact.retrieved_at_utc, "sha256": artifact.sha256, "byte_size": artifact.byte_size, "input_rows": manifest.get("input_rows"), "normalized_rows": manifest.get("normalized_rows"), "quarantined_rows": manifest.get("quarantined_rows"), "schema_status": manifest.get("schema_status"), "schema_fingerprint": manifest.get("schema_fingerprint"), "drift_alarms": [], "disappearance_semantics": "not-observed; never inferred as closure", "geocoding": "disabled", "release_state": "not-created", "publication_state": "private-candidate", "publication_eligibility": "blocked", "lifecycle_status": lifecycle.get("status"), "lifecycle_run_dir": lifecycle.get("run_dir")}
    atomic_json(Path(run_dir) / "refresh.json", report)
    return {"report": report, "lifecycle": lifecycle}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--raw", type=Path)
    source.add_argument("--fetch", action="store_true")
    parser.add_argument("--export-url")
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=Path("data/raw"))
    parser.add_argument("--run-id")
    parser.add_argument("--terms-review", type=Path)
    parser.add_argument("--retrieved-at-utc")
    parser.add_argument("--timeout-seconds", type=float, default=60)
    parser.add_argument("--max-bytes", type=int, default=128 * 1024 * 1024)
    parser.add_argument("--previous-normalized", type=Path)
    args = parser.parse_args()
    try:
        result = refresh(run_dir=args.run_dir, raw_path=args.raw, fetch=args.fetch, export_url=args.export_url, terms_review_path=args.terms_review, output_root=args.output_root, run_id=args.run_id, retrieved_at_utc=args.retrieved_at_utc, timeout_seconds=args.timeout_seconds, max_bytes=args.max_bytes, previous_normalized=args.previous_normalized)
    except (OSError, RefreshError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, sort_keys=True))
        return 2
    print(json.dumps(result["report"], sort_keys=True))
    return 0 if result["report"]["lifecycle_status"] == "candidate-ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
