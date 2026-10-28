"""EEA bridge for the existing shared private refresh runner."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from pipeline.common.orchestrator import run_private_lifecycle
from pipeline.contracts.adapter_contract import SourceArtifact
from pipeline.contracts.source_lifecycle import read_jsonl
from .acquire import fetch
from .adapter import ADAPTER_VERSION, COVERAGE, SCHEMA_VERSION, SOURCE_ID, SOURCE_URL, EeaLivestockAdapter


class EeaLivestockRefreshAdapter:
    source_id = SOURCE_ID
    adapter_version = ADAPTER_VERSION
    source_kind = "facility_master"

    def acquire(self, *, run_dir: Path, options: Mapping[str, Any]) -> Mapping[str, Any]:
        reviews = options.get("terms_review_paths", {})
        review = reviews.get(SOURCE_ID) if isinstance(reviews, Mapping) else None
        if not review:
            raise ValueError("EEA source-specific terms review is required")
        return fetch(output_root=run_dir / "acquisition", run_id=str(options.get("acquisition_run_id") or run_dir.name),
                     terms_review_path=Path(review), timeout_seconds=float(options.get("timeout_seconds", 60)),
                     max_bytes=min(int(options.get("max_bytes", 64 * 1024 * 1024)), 64 * 1024 * 1024))

    def refresh(self, *, mode: str, run_dir: Path, artifact: Path | None, options: Mapping[str, Any]) -> Mapping[str, Any]:
        facts = options.get("acquisition")
        if mode == "live-acquisition" or artifact is None or not isinstance(facts, Mapping):
            raise ValueError("EEA refresh requires a preserved acquisition")
        source_artifact = SourceArtifact(source_url=SOURCE_URL, retrieved_at_utc=facts["retrieved_at_utc"],
                                         sha256=facts["artifact_sha256"], byte_size=facts["artifact_byte_size"],
                                         code_version=ADAPTER_VERSION, config_version=SCHEMA_VERSION, coverage=COVERAGE,
                                         rights_caveat="CC BY 4.0; attribute European Environment Agency",
                                         privacy_caveat="private source-site evidence; publication review separate")
        adapter = EeaLivestockAdapter()
        result = run_private_lifecycle(artifact, run_dir / "lifecycle", source_artifact, adapter,
                                       health_as_of_utc=source_artifact.retrieved_at_utc)
        manifest = result.get("manifest") or {}
        handoff = {}
        if result.get("status") == "candidate-ready":
            rows = read_jsonl(Path(result["run_dir"]) / "normalized/records.jsonl")
            handoff = adapter.write_candidate_handoff(run_dir / "candidate-handoff", source_artifact, rows)
        return {"lifecycle_status": result.get("status"), "input_rows": manifest.get("input_rows", 0),
                "normalized_rows": manifest.get("normalized_rows", 0), "quarantined_rows": manifest.get("quarantined_rows", 0),
                "quarantine_reasons": manifest.get("anomaly_counts", {}), "country_counts": manifest.get("country_counts", {}),
                "candidate_handoff": bool(handoff), "candidate_observation_rows": handoff.get("normalized_rows", 0),
                "candidate_handoff_sha256": handoff.get("normalized_sha256"), "schema_fingerprint": manifest.get("schema_fingerprint"),
                "source_title": "European Environment Agency — Intensive livestock sites",
                "source_canonical_url": SOURCE_URL, "source_attribution": "European Environment Agency",
                "retrieved_at_utc": facts["retrieved_at_utc"], "geocoding": "disabled", "publication": "not-created"}
