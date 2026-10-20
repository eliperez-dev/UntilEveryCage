"""EPA ECHO animal-production private refresh bridge."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from pipeline.common.orchestrator import run_private_lifecycle
from pipeline.common.refresh_runner import RefreshCatalog, RefreshRunner
from pipeline.contracts.adapter_contract import SourceArtifact
from pipeline.contracts.candidate_handoff import write_handoff
from pipeline.contracts.refresh import RefreshRequest
from pipeline.contracts.source_lifecycle import read_jsonl

from . import SOURCE_ID
from .acquire import DEFAULT_MAX_BYTES, PAGE_SIZE, SERVICE_URL, fetch
from .adapter import ADAPTER_VERSION, SCHEMA_VERSION, EpaEchoAnimalAdapter
from .fixtures import write_synthetic_archive

COVERAGE = "EPA ECHO CWA/NPDES-associated facility records filtered by native livestock/poultry industry classifications; not a confirmed CAFO list or complete inventory"
RIGHTS_CAVEAT = "EPA default public-domain notice applies to EPA-produced data; ECHO can include state-reported inputs, so redistribution/provenance review remains separate"
PRIVACY_CAVEAT = "facility names, addresses, and coordinates remain in restricted private staging pending privacy and location-precision review"
REVIEW_BLOCKERS = {
    "terms": ["Confirm source-specific reuse and attribution treatment for EPA records and upstream state-submitted fields before any publication."],
    "privacy": ["Facility names, addresses, and location points remain private pending privacy and coordinate-precision review."],
    "classification": ["Industry codes plus CWA/NPDES association do not establish CAFO status, current operation, or animal counts."],
    "coverage": ["This bounded query covers only ECHO records matching selected livestock/poultry NAICS/SIC codes and is not a complete facility inventory."],
}


class EpaEchoAnimalRefreshAdapter:
    """Shared refresh hook; parsing and source semantics remain source-owned."""

    source_id = SOURCE_ID
    adapter_version = ADAPTER_VERSION
    source_kind = "facility_master"

    def acquire(self, *, run_dir: Path, options: Mapping[str, Any]) -> Mapping[str, Any]:
        reviews = options.get("terms_review_paths")
        review_path = reviews.get(SOURCE_ID) if isinstance(reviews, Mapping) else None
        review_path = review_path or options.get("terms_review_path")
        if not review_path:
            raise ValueError("source-specific terms review is required for live acquisition")
        return fetch(
            output_root=run_dir / "acquisition",
            run_id=str(options.get("acquisition_run_id") or run_dir.name),
            terms_review_path=Path(str(review_path)),
            timeout_seconds=float(options.get("timeout_seconds", 60)),
            max_bytes=int(options.get("max_bytes", DEFAULT_MAX_BYTES)),
            page_size=int(options.get("page_size", PAGE_SIZE)),
        )

    def refresh(self, *, mode: str, run_dir: Path, artifact: Path | None,
                options: Mapping[str, Any]) -> Mapping[str, Any]:
        if mode == "live-acquisition":
            raise ValueError("shared runner must preserve acquisition before source refresh")
        if mode == "fixture" and artifact is None:
            artifact = write_synthetic_archive(run_dir / "fixture" / "synthetic-responses.zip")
        if artifact is None or not artifact.is_file():
            raise FileNotFoundError("preserved EPA ECHO artifact is required")
        facts = options.get("acquisition")
        if not isinstance(facts, Mapping) and mode == "fixture" and artifact is not None:
            raw = artifact.read_bytes()
            facts = {
                "source_url": "https://example.invalid/epa-echo-animal-production-fixture",
                "retrieved_at_utc": "2026-01-01T00:00:00Z",
                "sha256": hashlib.sha256(raw).hexdigest(), "byte_size": len(raw),
            }
        if not isinstance(facts, Mapping):
            sidecar = artifact.parent / "acquisition-metadata.json"
            facts = json.loads(sidecar.read_text(encoding="utf-8")) if sidecar.is_file() else None
        if not isinstance(facts, Mapping) or artifact is None or not artifact.is_file():
            raise ValueError("EPA acquisition provenance is required")
        retrieved = facts.get("retrieved_at_utc")
        sha256 = facts.get("sha256")
        byte_size = facts.get("byte_size")
        if not retrieved or not sha256 or not isinstance(byte_size, int):
            raise ValueError("EPA acquisition provenance is incomplete")
        source_artifact = SourceArtifact(
            source_url=str(facts.get("final_url") or facts.get("source_url") or SERVICE_URL),
            retrieved_at_utc=str(retrieved), sha256=str(sha256), byte_size=byte_size,
            publication_date=facts.get("publication_date"), effective_date="unknown",
            code_version=ADAPTER_VERSION, config_version=SCHEMA_VERSION,
            rights_caveat=("synthetic fixture only; no source rights claim" if mode == "fixture" else RIGHTS_CAVEAT),
            privacy_caveat=("synthetic fixture only; no source privacy claim" if mode == "fixture" else PRIVACY_CAVEAT),
            coverage=("one synthetic EPA-shaped fixture row only" if mode == "fixture" else COVERAGE),
        )
        lifecycle = run_private_lifecycle(
            artifact, run_dir / "lifecycle", source_artifact, EpaEchoAnimalAdapter(),
            health_as_of_utc=source_artifact.retrieved_at_utc,
            review_blockers=REVIEW_BLOCKERS,
        )
        manifest = lifecycle.get("manifest") or {}
        handoff_written = False
        if lifecycle.get("status") == "candidate-ready":
            lifecycle_root = Path(lifecycle["run_dir"])
            rows = read_jsonl(lifecycle_root / "normalized" / "records.jsonl")
            safe_rows = [{**row, "source_values": {}} for row in rows]
            write_handoff(run_dir / "candidate-handoff", safe_rows, source_artifact,
                          source_id=SOURCE_ID, emit_graph_candidates=False)
            handoff_written = True
        return {
            "lifecycle_status": lifecycle.get("status"),
            "publication_state": "blocked",
            "input_rows": manifest.get("input_rows", 0),
            "normalized_rows": manifest.get("normalized_rows", 0),
            "quarantined_rows": manifest.get("quarantined_rows", 0),
            "candidate_handoff": handoff_written,
            "candidate_observation_rows": manifest.get("normalized_rows", 0) if handoff_written else 0,
            "quarantine_reasons": manifest.get("anomaly_counts", {}),
            "schema_fingerprint": manifest.get("schema_fingerprint"),
            "coverage": COVERAGE,
            "geocoding": "disabled",
            "publication": "not-created",
        }


def run_live(*, terms_review_path: Path, output_root: Path,
             timeout_seconds: float = 60.0, max_bytes: int = DEFAULT_MAX_BYTES,
             page_size: int = PAGE_SIZE) -> dict[str, Any]:
    """Execute one source-scoped authorized run through the shared runner."""
    request = RefreshRequest(
        source_ids=(SOURCE_ID,), mode="live-acquisition", output_root=output_root,
        options={
            "authorized_live_sources": [SOURCE_ID],
            "terms_review_paths": {SOURCE_ID: str(terms_review_path)},
            "timeout_seconds": timeout_seconds, "max_bytes": max_bytes, "page_size": page_size,
        },
    )
    return RefreshRunner(RefreshCatalog()).run(request)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch", action="store_true", required=True)
    parser.add_argument("--terms-review", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=Path("data/staging/source-expansion-20261020/us-epa-echo-animal-production"))
    parser.add_argument("--timeout-seconds", type=float, default=60)
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    parser.add_argument("--page-size", type=int, default=PAGE_SIZE)
    args = parser.parse_args()
    try:
        result = run_live(terms_review_path=args.terms_review, output_root=args.output_root,
                          timeout_seconds=args.timeout_seconds, max_bytes=args.max_bytes,
                          page_size=args.page_size)
    except (OSError, ValueError) as error:
        print(json.dumps({"status": "failed", "error_type": type(error).__name__}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("exit_status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
