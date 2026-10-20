"""Run Norway aquaculture through the shared private refresh bridge."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from pipeline.common.refresh_runner import RefreshCatalog, RefreshRunner
from pipeline.contracts.adapter_contract import SourceArtifact
from pipeline.contracts.refresh import AdapterCapabilities, RefreshRequest
from pipeline.contracts.source_lifecycle import read_jsonl
from pipeline.sources.norway.acquire import fetch
from pipeline.sources.norway.aquaculture import (
    ADAPTER_VERSION, COVERAGE, LICENSE, LICENSE_URL, LICENSE_VERSION,
    SCHEMA_VERSION, SOURCE_ID, SOURCE_URL, NorwayAquacultureAdapter,
)
from pipeline.contracts.candidate_handoff import write_handoff


class NorwayAquacultureRefreshAdapter:
    """D2 runner hook; all row processing stays source-owned."""

    source_id = SOURCE_ID
    adapter_version = ADAPTER_VERSION
    source_kind = "facility_master"

    def acquire(self, *, run_dir: Path, options: Mapping[str, Any]) -> Mapping[str, Any]:
        review_paths = options.get("terms_review_paths")
        review = review_paths.get(SOURCE_ID) if isinstance(review_paths, Mapping) else None
        review = review or options.get("terms_review_path")
        if not review:
            raise ValueError("source-specific terms review is required for live acquisition")
        return fetch(output_root=run_dir / "acquisition", run_id=str(options.get("acquisition_run_id") or run_dir.name),
                     terms_review_path=Path(str(review)), timeout_seconds=float(options.get("timeout_seconds", 60)),
                     max_bytes=int(options.get("max_bytes", 24 * 1024 * 1024)),
                     page_size=int(options.get("page_size", 500)))

    def refresh(self, *, mode: str, run_dir: Path, artifact: Path | None,
                options: Mapping[str, Any]) -> Mapping[str, Any]:
        if mode == "live-acquisition":
            raise ValueError("shared runner must preserve acquisition before source refresh")
        if artifact is None or not artifact.exists():
            raise FileNotFoundError("preserved aquaculture source artifact is required")
        facts = options.get("acquisition")
        if not isinstance(facts, Mapping):
            raise ValueError("acquisition provenance is required for source refresh")
        artifact_source_url = str(facts.get("canonical_url") or facts.get("source_url") or SOURCE_URL)
        retrieved = str(facts.get("retrieved_at_utc") or "")
        checksum = str(facts.get("artifact_sha256") or facts.get("sha256") or "")
        byte_size = facts.get("artifact_byte_size", facts.get("byte_size"))
        if not retrieved or not checksum or not isinstance(byte_size, int):
            raise ValueError("acquisition provenance is incomplete")
        source_artifact = SourceArtifact(
            source_url=artifact_source_url, retrieved_at_utc=retrieved,
            sha256=checksum, byte_size=byte_size,
            publication_date=facts.get("publication_date"), effective_date=facts.get("effective_date"),
            code_version=ADAPTER_VERSION, config_version=SCHEMA_VERSION,
            rights_caveat=f"{LICENSE} {LICENSE_VERSION}; attribute Fiskeridirektoratet and do not imply endorsement; private preview only",
            privacy_caveat="locality-point precision and facility privacy review remain pending; no holder mailing address is used",
            coverage=COVERAGE,
        )
        lifecycle = RefreshRunnerAdapter.run_lifecycle(artifact, run_dir, source_artifact)
        manifest = lifecycle.get("manifest") or {}
        candidate = False
        if lifecycle.get("status") == "candidate-ready":
            lifecycle_root = Path(lifecycle["run_dir"])
            rows = read_jsonl(lifecycle_root / "normalized" / "records.jsonl")
            safe_rows = [{**row, "source_values": {}} for row in rows]
            handoff = write_handoff(run_dir / "candidate-handoff", safe_rows, source_artifact,
                                    source_id=SOURCE_ID, emit_graph_candidates=False)
            candidate = True
        else:
            handoff = {}
        return {
            "lifecycle_status": lifecycle.get("status"),
            "publication_state": lifecycle.get("publication_state", "unchanged"),
            "input_rows": manifest.get("input_rows", 0),
            "normalized_rows": manifest.get("normalized_rows", 0),
            "quarantined_rows": manifest.get("quarantined_rows", 0),
            "candidate_handoff": candidate,
            "candidate_observation_rows": manifest.get("normalized_rows", 0) if candidate else 0,
            "candidate_handoff_sha256": handoff.get("normalized_sha256"),
            "source_title": "Fiskeridirektoratet Aquaculture Register localities",
            "retrieved_at_utc": retrieved,
            "source_feature_count": facts.get("feature_count", 0),
            "source_object_id_count": facts.get("object_id_count", 0),
            "source_coordinate_count_checked": facts.get("coordinates_checked", 0),
            "source_page_count": facts.get("page_count", 0),
            "source_license": f"{LICENSE} {LICENSE_VERSION}",
            "source_canonical_url": artifact_source_url,
            "schema_fingerprint": manifest.get("schema_fingerprint"),
            "quarantine_reasons": manifest.get("anomaly_counts", {}),
            "source_attribution": "Fiskeridirektoratet",
            "geocoding": "disabled", "publication": "not-created",
        }


class RefreshRunnerAdapter:
    @staticmethod
    def run_lifecycle(artifact: Path, run_dir: Path, source_artifact: SourceArtifact) -> dict[str, Any]:
        from pipeline.common.orchestrator import run_private_lifecycle
        return run_private_lifecycle(artifact, run_dir / "lifecycle", source_artifact,
                                     NorwayAquacultureAdapter(), health_as_of_utc=source_artifact.retrieved_at_utc)


def run_live(*, terms_review_path: Path, output_root: Path,
             timeout_seconds: float = 60.0, max_bytes: int = 24 * 1024 * 1024,
             page_size: int = 500) -> dict[str, Any]:
    """Use the shared runner with a source-local capability registration.

    The project registry already identifies this source; the capability entry
    is supplied here until the owning integration lane adds it centrally.
    """
    catalog = RefreshCatalog()
    capabilities = AdapterCapabilities(
        source_id=SOURCE_ID, adapter_version=ADAPTER_VERSION, schema_version=SCHEMA_VERSION,
        acquisition="bounded_private_fetch", geocoding="disabled", publication="human_gate_required",
        adapter_path="pipeline.sources.norway.refresh.NorwayAquacultureRefreshAdapter",
        country_code="NO", source_kind="facility_master", operational_classification="live",
        live_callable=True,
    )
    catalog.register(NorwayAquacultureRefreshAdapter(), capabilities)
    request = RefreshRequest(
        source_ids=(SOURCE_ID,), mode="live-acquisition", output_root=output_root,
        options={"authorized_live_sources": [SOURCE_ID],
                 "terms_review_paths": {SOURCE_ID: str(terms_review_path)},
                 "timeout_seconds": timeout_seconds, "max_bytes": max_bytes,
                 "page_size": page_size},
    )
    return RefreshRunner(catalog).run(request)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch", action="store_true", required=True)
    parser.add_argument("--terms-review", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=Path("data/staging/source-expansion-20261020/norway"))
    parser.add_argument("--timeout-seconds", type=float, default=60)
    parser.add_argument("--max-bytes", type=int, default=24 * 1024 * 1024)
    parser.add_argument("--page-size", type=int, default=500)
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
