"""Run an accepted Géorisques ICPE snapshot through the private lifecycle."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from pipeline.common.acquisition import require_terms_review
from pipeline.common.orchestrator import run_private_lifecycle
from pipeline.common.review import write_operator_review_packet
from pipeline.contracts.adapter_contract import SourceArtifact
from pipeline.contracts.candidate_handoff import write_handoff
from pipeline.contracts.source_lifecycle import atomic_json, read_jsonl

from .acquire import acquire_snapshot
from .adapter import GeorisquesIcpeAnimalAdapter
from .config import CONFIG


def _artifact_from_snapshot(path: Path, terms: dict[str, str]) -> tuple[Path, SourceArtifact]:
    if path.is_file():
        path = path.parent
    manifest_path = path.parent / "snapshot-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("source_id") != CONFIG["source_id"]:
        raise ValueError("snapshot source_id does not match this adapter")
    adapter = GeorisquesIcpeAnimalAdapter()
    parsed = adapter.parse_pages(path)
    if parsed["sha256"] != manifest.get("sha256") or parsed["byte_size"] != manifest.get("byte_size"):
        raise ValueError("snapshot bytes do not match snapshot-manifest provenance")
    if parsed["results"] != manifest.get("results") or parsed["total_pages"] != manifest.get("total_pages"):
        raise ValueError("snapshot manifest counts do not reconcile")
    artifact = SourceArtifact(
        source_url=CONFIG["source_url"],
        retrieved_at_utc=str(manifest["retrieved_at_utc"]),
        sha256=parsed["sha256"], byte_size=parsed["byte_size"],
        effective_date="unknown", code_version=CONFIG["adapter_version"],
        config_version=CONFIG["config_version"],
        rights_caveat="Géorisques CGU acceptance recorded in terms review; Licence Ouverte 2.0 attribution/update-date review still required.",
        privacy_caveat="Restricted private evidence; names/identifiers retained for review; no personal-contact expansion or geocoding.",
        coverage=CONFIG["coverage"],
    )
    # Do not embed reviewer notes or identity in row-level evidence.
    atomic_json(path.parent / "terms-review-reference.json", {
        "decision": terms["decision"], "reference": terms["reference"],
        "reviewed_at": terms["reviewed_at"],
    })
    return path, artifact


def refresh(*, run_dir: str | Path, terms_review_path: str | Path,
            raw_path: str | Path | None = None, fetch: bool = False,
            output_root: str | Path = "data/raw", run_id: str | None = None,
            timeout_seconds: float = 30.0, page_size: int | None = None,
            max_pages: int | None = None, max_records: int | None = None) -> dict[str, Any]:
    if fetch == (raw_path is not None):
        raise ValueError("specify exactly one of --fetch or --raw-pages")
    terms = require_terms_review(Path(terms_review_path))
    if fetch:
        snapshot = acquire_snapshot(output_root=output_root, terms_review_path=terms_review_path,
                                    run_id=run_id, timeout_seconds=timeout_seconds,
                                    page_size=page_size, max_pages=max_pages, max_records=max_records)
        source, artifact = _artifact_from_snapshot(Path(snapshot["artifact_path"]), terms)
    else:
        source, artifact = _artifact_from_snapshot(Path(raw_path), terms)
    root = Path(run_dir)
    atomic_json(root / "acquisition-metadata.json", {
        "source_id": CONFIG["source_id"], "source_url": CONFIG["source_url"],
        "retrieved_at_utc": artifact.retrieved_at_utc, "checksum_sha256": artifact.sha256,
        "byte_size": artifact.byte_size, "terms_decision": terms["decision"],
        "terms_reference": terms["reference"], "private_raw_pages": str(source),
    })
    adapter = GeorisquesIcpeAnimalAdapter()
    lifecycle = run_private_lifecycle(
        source, root / "lifecycle", artifact, adapter,
        health_as_of_utc=artifact.retrieved_at_utc,
        review_blockers={
            "terms": ["Géorisques CGU acceptance must be recorded; Licence Ouverte 2.0 attribution/update-date review remains separate."],
            "privacy": ["Native names, addresses, business identifiers and coordinates require private review; no contact expansion."],
            "classification": ["ICPE rubrics are regulatory observations; current animal use and source status are not independently verified."],
            "coverage": ["Only allowlisted animal/agriculture/animal-food rubrics; filtered API results are not a complete facility count."],
        },
    )
    if lifecycle.get("status") == "candidate-ready":
        lifecycle_root = Path(lifecycle["run_dir"])
        rows = read_jsonl(lifecycle_root / "normalized" / "records.jsonl")
        write_handoff(lifecycle_root / "candidate-handoff", rows, artifact, source_id=adapter.source_id)
        write_operator_review_packet(
            lifecycle_root, lifecycle["manifest"], source_scope=CONFIG["coverage"],
            checks=("review candidate-handoff/records.jsonl in restricted staging", "confirm API terms and attribution/update date", "review geography and activity semantics"),
            blockers=("private candidate only; release not created", "current animal use and status are not independently verified", "publication requires separate approval"),
        )
    report = {
        "source_id": adapter.source_id, "source_url": artifact.source_url,
        "retrieved_at_utc": artifact.retrieved_at_utc, "checksum_sha256": artifact.sha256,
        "byte_size": artifact.byte_size, "lifecycle_status": lifecycle.get("status"),
        "run_dir": lifecycle.get("run_dir"), "release_state": "not-created",
        "publication_state": lifecycle.get("publication_state", "unchanged"),
        "terms_status": "accepted-for-private-processing; attribution/release review pending",
        "geocoding": "disabled",
    }
    atomic_json(root / "refresh.json", report)
    return {"report": report, "lifecycle": lifecycle}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--fetch", action="store_true")
    source.add_argument("--raw-pages", type=Path)
    parser.add_argument("--terms-review", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=Path("data/raw"))
    parser.add_argument("--run-id")
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument("--page-size", type=int)
    parser.add_argument("--max-pages", type=int)
    parser.add_argument("--max-records", type=int)
    args = parser.parse_args()
    try:
        result = refresh(run_dir=args.run_dir, terms_review_path=args.terms_review,
                         raw_path=args.raw_pages, fetch=args.fetch, output_root=args.output_root,
                         run_id=args.run_id, timeout_seconds=args.timeout_seconds,
                         page_size=args.page_size, max_pages=args.max_pages,
                         max_records=args.max_records)
    except (OSError, ValueError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, sort_keys=True))
        return 2
    print(json.dumps(result["report"], sort_keys=True))
    return 0 if result["report"]["lifecycle_status"] == "candidate-ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
