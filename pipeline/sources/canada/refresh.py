"""Run Ontario or CFIA through private acquisition or assisted capture."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from pipeline.common.acquisition import utc_now
from pipeline.common.orchestrator import run_private_lifecycle
from pipeline.common.review import write_operator_review_packet
from pipeline.contracts.adapter_contract import source_artifact_from_acquisition
from pipeline.contracts.candidate_handoff import write_handoff
from pipeline.contracts.source_lifecycle import atomic_json

from .acquire import ADAPTERS, fetch_source_artifact


def _local_metadata(path: Path, adapter: Any, retrieved: str) -> dict[str, Any]:
    """Reuse a verified acquisition sidecar when staging a fetched artifact."""
    sidecar = path.parent / "acquisition-metadata.json"
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if sidecar.is_file():
        retained = json.loads(sidecar.read_text(encoding="utf-8"))
        if retained.get("sha256") == digest and int(retained.get("byte_size", -1)) == len(raw):
            return retained
    return {"acquisition_method": "assisted_local_capture", "source_id": adapter.source_id, "artifact_path": str(path), "sha256": digest, "byte_size": len(raw), "retrieved_at_utc": retrieved, "requested_url": adapter.source_url, "final_url": adapter.source_url}


def refresh(*, source: str, run_dir: str | Path, raw_path: str | Path | None = None, fetch: bool = False, terms_review_path: str | Path | None = None, output_root: str | Path = "data/raw", run_id: str | None = None, retrieved_at_utc: str | None = None, timeout_seconds: float = 60.0, max_bytes: int = 64 * 1024 * 1024) -> dict[str, Any]:
    if fetch == (raw_path is not None): raise ValueError("specify exactly one of --fetch or --raw")
    adapter = ADAPTERS[source](); retrieved = retrieved_at_utc or utc_now()
    if fetch:
        if terms_review_path is None: raise ValueError("--terms-review is required with --fetch")
        metadata = fetch_source_artifact(source=source, output_root=output_root, terms_review_path=terms_review_path, run_id=run_id, timeout_seconds=timeout_seconds, max_bytes=max_bytes); raw = Path(metadata["artifact_path"])
        artifact = source_artifact_from_acquisition(metadata, adapter_version=adapter.adapter_version, config_version=adapter.schema_version)
    else:
        raw = Path(raw_path).resolve()
        if not raw.is_file(): raise ValueError("--raw artifact must exist")
        metadata = _local_metadata(raw, adapter, retrieved)
        data = raw.read_bytes(); artifact = source_artifact_from_acquisition(metadata, adapter_version=adapter.adapter_version, config_version=adapter.schema_version, source_url=adapter.source_url, coverage=adapter.coverage, rights_caveat="assisted capture; current terms remain pending", privacy_caveat="private staging; privacy review pending")
    root = Path(run_dir); atomic_json(root / "acquisition-metadata.json", metadata); lifecycle = run_private_lifecycle(raw, root / "lifecycle", artifact, adapter, health_as_of_utc=retrieved)
    if lifecycle.get("status") == "candidate-ready":
        run_root = Path(lifecycle["run_dir"]); rows = [json.loads(line) for line in (run_root / "normalized" / "records.jsonl").read_text(encoding="utf-8").splitlines() if line]; write_handoff(run_root / "candidate-handoff", rows, artifact, source_id=adapter.source_id)
        write_operator_review_packet(run_root, lifecycle["manifest"], source_scope=lifecycle["manifest"]["coverage"], checks=("review candidate-handoff/records.jsonl in restricted staging", "keep Ontario and CFIA candidates separate", "confirm no public promotion"), blockers=("candidate is private and human-gated", "privacy and attribution review pending"))
    report = {"source_id": adapter.source_id, "jurisdiction": adapter.jurisdiction, "source_url": artifact.source_url, "retrieved_at_utc": artifact.retrieved_at_utc, "checksum_sha256": artifact.sha256, "byte_size": artifact.byte_size, "lifecycle_status": lifecycle.get("status"), "run_dir": lifecycle.get("run_dir"), "publication_state": lifecycle.get("publication_state", "unchanged"), "release_state": "not-created", "geocoding": "disabled"}; atomic_json(root / "refresh.json", report); return {"report": report, "lifecycle": lifecycle}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--source", choices=sorted(ADAPTERS), required=True); group = parser.add_mutually_exclusive_group(required=True); group.add_argument("--fetch", action="store_true"); group.add_argument("--raw", type=Path); parser.add_argument("--run-dir", type=Path, required=True); parser.add_argument("--terms-review", type=Path); parser.add_argument("--output-root", type=Path, default=Path("data/raw")); parser.add_argument("--run-id"); parser.add_argument("--retrieved-at-utc"); parser.add_argument("--timeout-seconds", type=float, default=60.0); parser.add_argument("--max-bytes", type=int, default=64 * 1024 * 1024); args = parser.parse_args()
    try: result = refresh(source=args.source, run_dir=args.run_dir, raw_path=args.raw, fetch=args.fetch, terms_review_path=args.terms_review, output_root=args.output_root, run_id=args.run_id, retrieved_at_utc=args.retrieved_at_utc, timeout_seconds=args.timeout_seconds, max_bytes=args.max_bytes)
    except (OSError, ValueError) as error: print(json.dumps({"status": "failed", "error": str(error)}, sort_keys=True)); return 2
    print(json.dumps(result["report"], sort_keys=True)); return 0 if result["report"]["lifecycle_status"] == "candidate-ready" else 1


if __name__ == "__main__": raise SystemExit(main())
