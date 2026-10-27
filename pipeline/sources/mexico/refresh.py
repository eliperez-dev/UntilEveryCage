"""Shared refresh-runner hook for private Mexico DENUE candidate staging."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Mapping

from pipeline.common.orchestrator import run_private_lifecycle
from pipeline.contracts.adapter_contract import SourceArtifact
from pipeline.contracts.source_lifecycle import read_jsonl

from .acquire import DEFAULT_MAX_BYTES, DEFAULT_MAX_RECORDS, DEFAULT_MAX_REQUESTS, DEFAULT_PAGE_SIZE, fetch
from .adapter import ADAPTER_VERSION, API_BASE, API_DOCS, SCHEMA_VERSION, SOURCE_ID, DenueAdapter

REVIEW_BLOCKERS = {
    "terms": ["INEGI free-use attribution and source-specific terms review must be confirmed before publication."],
    "privacy": ["Facility coordinates and addresses require location-precision/privacy review before public use."],
    "coverage": ["DENUE is a business directory, not a TIF certification registry or census of all animal facilities."],
    "classification": ["SCIAN classes 311611–311614 are mapped to slaughter/processing; verify fit and retain source activity fields."],
}


class DenueRefreshAdapter:
    """Acquisition and refresh hook; root owns shared registry/runner wiring."""

    source_id = SOURCE_ID
    adapter_version = ADAPTER_VERSION
    source_kind = "facility_master"

    def acquire(self, *, run_dir: Path, options: Mapping[str, Any]) -> Mapping[str, Any]:
        review_paths = options.get("terms_review_paths")
        review = review_paths.get(SOURCE_ID) if isinstance(review_paths, Mapping) else None
        review = review or options.get("terms_review_path")
        if not review:
            raise ValueError("source-specific terms review is required for live acquisition")
        return fetch(
            output_root=run_dir / "acquisition",
            page_size=int(options.get("page_size", DEFAULT_PAGE_SIZE)),
            max_records=int(options.get("max_records", DEFAULT_MAX_RECORDS)),
            max_requests=int(options.get("max_requests", DEFAULT_MAX_REQUESTS)),
            max_bytes=int(options.get("max_bytes", DEFAULT_MAX_BYTES)),
            timeout_seconds=float(options.get("timeout_seconds", 30)),
            max_duration_seconds=float(options.get("max_duration_seconds", 900)),
            states=tuple(options.get("states") or (f"{n:02d}" for n in range(1, 33))),
        )

    def refresh(self, *, mode: str, run_dir: Path, artifact: Path | None,
                options: Mapping[str, Any]) -> Mapping[str, Any]:
        if mode == "live-acquisition":
            raise ValueError("shared runner must preserve acquisition before source refresh")
        if artifact is None or not artifact.is_file():
            raise FileNotFoundError("preserved DENUE JSON artifact is required")
        facts = options.get("acquisition")
        if not isinstance(facts, Mapping):
            raise ValueError("acquisition provenance is required for source refresh")
        retrieved = str(facts.get("retrieved_at_utc") or "")
        checksum = str(facts.get("artifact_sha256") or facts.get("sha256") or "")
        byte_size = facts.get("artifact_byte_size", facts.get("byte_size"))
        if not retrieved or not checksum or not isinstance(byte_size, int):
            raise ValueError("acquisition provenance is incomplete")
        raw = artifact.read_bytes()
        if len(raw) != byte_size or hashlib.sha256(raw).hexdigest() != checksum:
            raise ValueError("DENUE acquisition provenance does not match preserved artifact")

        source_artifact = SourceArtifact(
            source_url=API_BASE, retrieved_at_utc=retrieved, sha256=checksum, byte_size=byte_size,
            publication_date=facts.get("publication_date"), effective_date=facts.get("effective_date"),
            code_version=ADAPTER_VERSION, config_version=SCHEMA_VERSION,
            rights_caveat="INEGI DENUE API; attribute Source: INEGI, DENUE with retrieval date, identify transformations, and do not imply endorsement.",
            privacy_caveat="Private staging only; address and source-coordinate precision require separate review.",
            coverage="INEGI DENUE selected SCIAN 2023 classes 311611–311614; bounded state-by-state API acquisition.",
        )
        adapter = DenueAdapter()
        lifecycle = run_private_lifecycle(
            artifact, run_dir / "lifecycle", source_artifact, adapter,
            health_as_of_utc=retrieved, review_blockers=REVIEW_BLOCKERS,
        )
        manifest = lifecycle.get("manifest") or {}
        handoff: dict[str, Any] = {}
        if lifecycle.get("status") == "candidate-ready":
            lifecycle_root = Path(lifecycle["run_dir"])
            rows = read_jsonl(lifecycle_root / "normalized" / "records.jsonl")
            parsed = adapter.parse_bytes(raw)
            handoff = adapter.write_candidate_handoff(
                run_dir / "candidate-handoff", source_artifact,
                {"accepted": rows, "quarantined": parsed["quarantined"]},
            )
        return {
            "lifecycle_status": lifecycle.get("status"),
            "publication_state": lifecycle.get("publication_state", "unchanged"),
            "input_rows": manifest.get("input_rows", 0),
            "normalized_rows": manifest.get("normalized_rows", 0),
            "quarantined_rows": manifest.get("quarantined_rows", 0),
            "candidate_handoff": bool(handoff),
            "candidate_observation_rows": handoff.get("normalized_rows", 0),
            "candidate_handoff_sha256": handoff.get("normalized_sha256"),
            "source_canonical_url": API_BASE,
            "source_documentation_url": API_DOCS,
            "retrieved_at_utc": retrieved,
            "source_artifact_sha256": checksum,
            "source_artifact_byte_size": byte_size,
            "preflight_rows": facts.get("preflight_rows"),
            "request_count": facts.get("request_count"),
            "response_bytes": facts.get("response_bytes"),
            "activity_counts": facts.get("activity_counts", {}),
            "quarantine_reasons": manifest.get("anomaly_counts", {}),
            "geocoding": "disabled",
            "publication": "not-created",
        }
