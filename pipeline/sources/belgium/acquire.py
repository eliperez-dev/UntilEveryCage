"""Bounded FASFC pair acquisition; bytes are written only to ignored storage."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from pipeline.common.acquisition import AcquisitionError, fetch_source
from pipeline.contracts.source_lifecycle import atomic_json

from .adapter import CONFIG


def fetch_pair(*, output_root: str | Path, terms_review_path: str | Path, run_id: str | None = None, timeout_seconds: float = 180, max_bytes: int = 128 * 1024 * 1024, max_attempts: int = 3) -> dict:
    """Fetch operator and companion codebook with independent provenance."""
    root = Path(output_root)
    common = {"timeout_seconds": timeout_seconds, "max_bytes": max_bytes, "max_attempts": max_attempts, "retry_delay_seconds": 2, "max_retry_delay_seconds": 8}
    operator = fetch_source(source_id=CONFIG["source_id"], url=CONFIG["operator_url"], output_root=root, artifact_name="operators.csv", run_id=run_id, terms_review_path=terms_review_path, code_version=CONFIG["adapter_version"], config_version=CONFIG["schema_version"], coverage=CONFIG["coverage"], rights_caveat=CONFIG["terms"], privacy_caveat="restricted private staging; no address/name/identifier fields are copied to the candidate handoff", **common)
    codebook = fetch_source(source_id="be.activity-codes", url=CONFIG["activity_code_url"], output_root=root, artifact_name="activity-codes.csv", run_id=run_id, terms_review_path=terms_review_path, code_version=CONFIG["adapter_version"], config_version=CONFIG["schema_version"], coverage="FASFC LAP/PAP activity codebook; not a facility list", rights_caveat=CONFIG["terms"], privacy_caveat="no facility rows expected", **common)
    pair = {"operator": operator, "activity_codes": codebook, "source_id": CONFIG["source_id"], "catalog_url": CONFIG["catalog_url"]}
    atomic_json(root / CONFIG["source_id"] / str(run_id or operator["run_id"]) / "pair-metadata.json", pair)
    return pair


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=Path("data/raw"))
    parser.add_argument("--terms-review", type=Path, required=True)
    parser.add_argument("--run-id")
    parser.add_argument("--timeout-seconds", type=float, default=60)
    parser.add_argument("--max-bytes", type=int, default=128 * 1024 * 1024)
    args = parser.parse_args()
    try:
        pair = fetch_pair(output_root=args.output_root, terms_review_path=args.terms_review, run_id=args.run_id, timeout_seconds=args.timeout_seconds, max_bytes=args.max_bytes)
    except (OSError, AcquisitionError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, sort_keys=True))
        return 2
    print(json.dumps({"status": "archived", "operator": pair["operator"], "activity_codes": pair["activity_codes"]}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
