"""Run the Belgium FASFC pair through the shared private lifecycle.

The normal assisted mode takes two operator-provided files: the FASFC operator
CSV and the official LAP/PAP codebook CSV.  ``--fetch`` is available only after
the operator records the source terms decision and uses the same bounded fetch
primitive for both files.  Neither mode creates a release.
"""
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

from .adapter import CONFIG, BelgiumOperatorsAdapter


class RefreshError(ValueError):
    """A Belgium refresh cannot safely continue."""


def _local_metadata(path: Path, *, source_id: str, source_url: str, retrieved_at: str, coverage: str) -> dict[str, Any]:
    raw = path.read_bytes()
    return {"acquisition_method": "assisted_local_capture", "source_id": source_id, "artifact": path.name, "artifact_path": str(path.resolve()), "requested_url": source_url, "final_url": source_url, "redirects": [], "response_headers": {}, "requested_at_utc": retrieved_at, "retrieved_at_utc": retrieved_at, "effective_date": "unknown", "publication_date": None, "sha256": hashlib.sha256(raw).hexdigest(), "byte_size": len(raw), "adapter_version": CONFIG["adapter_version"], "code_version": CONFIG["adapter_version"], "config_version": CONFIG["schema_version"], "coverage": coverage, "rights_caveat": CONFIG["terms"], "privacy_caveat": "private staging; address and coordinate review pending", "terms_review": "operator-assisted capture; source terms review remains a separate gate"}


def _artifact(metadata: dict[str, Any], *, default_url: str, default_coverage: str) -> SourceArtifact:
    return SourceArtifact(source_url=str(metadata.get("final_url") or metadata.get("requested_url") or default_url), retrieved_at_utc=str(metadata.get("retrieved_at_utc") or ""), sha256=str(metadata["sha256"]), byte_size=int(metadata["byte_size"]), publication_date=metadata.get("publication_date"), effective_date=metadata.get("effective_date"), code_version=str(metadata.get("code_version") or CONFIG["adapter_version"]), config_version=str(metadata.get("config_version") or CONFIG["schema_version"]), rights_caveat=metadata.get("rights_caveat") or CONFIG["terms"], privacy_caveat=metadata.get("privacy_caveat") or "private staging; privacy review pending", coverage=metadata.get("coverage") or default_coverage, redirects=tuple(metadata.get("redirects") or ()))


def refresh(*, run_dir: str | Path, operators_path: str | Path | None = None, activity_codes_path: str | Path | None = None, fetch_pair: bool = False, output_root: str | Path = "data/raw", run_id: str | None = None, terms_review_path: str | Path | None = None, retrieved_at_utc: str | None = None, timeout_seconds: float = 60, max_bytes: int = 128 * 1024 * 1024, previous_normalized: str | Path | None = None) -> dict[str, Any]:
    if fetch_pair == (operators_path is not None or activity_codes_path is not None):
        raise RefreshError("specify --fetch or both --operators and --activity-codes")
    root = Path(run_dir)
    retrieved = retrieved_at_utc or utc_now()
    if fetch_pair:
        if terms_review_path is None:
            raise RefreshError("--terms-review is required with --fetch")
        try:
            operator_meta = fetch_source(source_id=CONFIG["source_id"], url=CONFIG["operator_url"], output_root=Path(output_root), artifact_name="operators.csv", run_id=run_id, timeout_seconds=timeout_seconds, max_bytes=max_bytes, terms_review_path=terms_review_path, code_version=CONFIG["adapter_version"], config_version=CONFIG["schema_version"], coverage=CONFIG["coverage"], rights_caveat=CONFIG["terms"], privacy_caveat="private staging; privacy review pending")
            code_meta = fetch_source(source_id="be.activity-codes", url=CONFIG["activity_code_url"], output_root=Path(output_root), artifact_name="activity-codes.csv", run_id=run_id, timeout_seconds=timeout_seconds, max_bytes=max_bytes, terms_review_path=terms_review_path, code_version=CONFIG["adapter_version"], config_version=CONFIG["schema_version"], coverage="FASFC LAP/PAP codebook; not a facility list", rights_caveat=CONFIG["terms"], privacy_caveat="no facility rows expected")
        except AcquisitionError as error:
            raise RefreshError(str(error)) from error
        operator_path = Path(operator_meta["artifact_path"]); code_path = Path(code_meta["artifact_path"])
    else:
        if operators_path is None or activity_codes_path is None:
            raise RefreshError("both local artifacts are required")
        operator_path, code_path = Path(operators_path).resolve(), Path(activity_codes_path).resolve()
        if not operator_path.is_file() or not code_path.is_file():
            raise RefreshError("operator and activity-code artifacts must exist")
        operator_meta = _local_metadata(operator_path, source_id=CONFIG["source_id"], source_url=CONFIG["operator_url"], retrieved_at=retrieved, coverage=CONFIG["coverage"])
        code_meta = _local_metadata(code_path, source_id="be.activity-codes", source_url=CONFIG["activity_code_url"], retrieved_at=retrieved, coverage="FASFC LAP/PAP codebook; not a facility list")
    atomic_json(root / "acquisition-metadata.json", {"operator": operator_meta, "activity_codes": code_meta})
    operator_artifact = _artifact(operator_meta, default_url=CONFIG["operator_url"], default_coverage=CONFIG["coverage"])
    code_artifact = _artifact(code_meta, default_url=CONFIG["activity_code_url"], default_coverage="FASFC LAP/PAP codebook; not a facility list")
    adapter = BelgiumOperatorsAdapter(code_path, code_artifact)
    lifecycle = run_private_lifecycle(operator_path, root / "lifecycle", operator_artifact, adapter, health_as_of_utc=retrieved)
    manifest = lifecycle.get("manifest") or {}
    report = {"source_id": CONFIG["source_id"], "source_url": operator_artifact.source_url, "retrieved_at_utc": operator_artifact.retrieved_at_utc, "operator_sha256": operator_artifact.sha256, "activity_code_sha256": code_artifact.sha256, "input_rows": manifest.get("input_rows"), "normalized_rows": manifest.get("normalized_rows"), "quarantined_rows": manifest.get("quarantined_rows"), "operator_schema_fingerprint": manifest.get("operator_schema_fingerprint"), "activity_code_schema_fingerprint": (manifest.get("activity_codebook") or {}).get("schema_fingerprint"), "drift_alarms": [], "disappeared_not_observed_count": 0, "disappearance_semantics": "not-observed; never inferred as closure", "geocoding": "disabled", "release_state": "not-created", "publication_state": "private-candidate", "publication_eligibility": "blocked", "lifecycle_status": lifecycle.get("status"), "lifecycle_run_dir": lifecycle.get("run_dir"), "previous_normalized_supplied": previous_normalized is not None}
    atomic_json(root / "refresh.json", report)
    return {"report": report, "lifecycle": lifecycle}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--fetch", action="store_true")
    source.add_argument("--operators", type=Path)
    parser.add_argument("--activity-codes", type=Path)
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
        result = refresh(run_dir=args.run_dir, operators_path=args.operators, activity_codes_path=args.activity_codes, fetch_pair=args.fetch, output_root=args.output_root, run_id=args.run_id, terms_review_path=args.terms_review, retrieved_at_utc=args.retrieved_at_utc, timeout_seconds=args.timeout_seconds, max_bytes=args.max_bytes, previous_normalized=args.previous_normalized)
    except (OSError, RefreshError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, sort_keys=True))
        return 2
    print(json.dumps(result["report"], sort_keys=True))
    return 0 if result["report"]["lifecycle_status"] == "candidate-ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
