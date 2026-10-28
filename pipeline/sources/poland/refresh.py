"""GIW source bridge for the existing refresh runner."""
from pathlib import Path
import os
from pipeline.common.orchestrator import run_private_lifecycle
from pipeline.contracts.adapter_contract import SourceArtifact
from pipeline.contracts.source_lifecycle import read_jsonl
from .adapter import ADAPTER_VERSION, SCHEMA_VERSION, SOURCE_ID, SOURCE_URL, COVERAGE, GiwApprovedFoodAdapter
from .acquire import fetch


class GiwApprovedFoodRefreshAdapter:
    source_id = SOURCE_ID
    adapter_version = ADAPTER_VERSION
    source_kind = "facility_master"

    def acquire(self, *, run_dir, options):
        review = options.get("terms_review_paths", {}).get(SOURCE_ID)
        if not review:
            raise ValueError("GIW source terms review is required")
        return fetch(output_root=run_dir / "acquisition", run_id=str(options.get("acquisition_run_id") or run_dir.name),
                     terms_review_path=Path(review), timeout_seconds=min(float(options.get("timeout_seconds", 30)),30),
                     resume_root=Path(os.environ["UEC_POLAND_RESUME_CAPTURE"]) if os.environ.get("UEC_POLAND_RESUME_CAPTURE") else None)

    def refresh(self, *, mode, run_dir, artifact, options):
        facts = options.get("acquisition")
        if mode == "live-acquisition" or artifact is None or not isinstance(facts, dict):
            raise ValueError("GIW refresh requires preserved source pages and acquisition provenance")
        source_artifact = SourceArtifact(SOURCE_URL, facts["retrieved_at_utc"], facts["artifact_sha256"], facts["artifact_byte_size"],
            code_version=ADAPTER_VERSION, config_version=SCHEMA_VERSION, coverage=COVERAGE,
            rights_caveat="GIW attribution, source/acquisition dates and transformation notice; private integration only",
            privacy_caveat="private business-site source evidence; separate publication and location review")
        adapter = GiwApprovedFoodAdapter()
        result = run_private_lifecycle(artifact, run_dir / "lifecycle", source_artifact, adapter,
                                       health_as_of_utc=source_artifact.retrieved_at_utc)
        manifest = result.get("manifest") or {}
        handoff = {}
        if result.get("status") == "candidate-ready":
            rows = read_jsonl(Path(result["run_dir"]) / "normalized/records.jsonl")
            handoff = adapter.write_candidate_handoff(run_dir / "candidate-handoff", source_artifact, rows)
        return {"lifecycle_status": result.get("status"), "input_rows": manifest.get("input_rows", 0),
            "normalized_rows": manifest.get("normalized_rows", 0), "quarantined_rows": manifest.get("quarantined_rows", 0),
            "quarantine_reasons": manifest.get("anomaly_counts", {}), "candidate_handoff": bool(handoff),
            "candidate_observation_rows": handoff.get("normalized_rows", 0), "candidate_handoff_sha256": handoff.get("normalized_sha256"),
            "schema_fingerprint": manifest.get("schema_fingerprint"), "source_title": "GIW approved animal-origin food establishments",
            "source_canonical_url": SOURCE_URL, "retrieved_at_utc": facts["retrieved_at_utc"],
            "geocoding": "separate-private-profile", "publication": "not-created"}
