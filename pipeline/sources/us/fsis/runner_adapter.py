"""Bridge the existing two-file FSIS lifecycle into the private refresh runner."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from pipeline.contracts.adapter_contract import SourceArtifact
from pipeline.contracts.candidate_handoff import write_handoff

from .adapter import CONFIG, FsisMpiAdapter
from .firefox_acquisition import acquire_firefox
from .refresh import _validate_download


ROOT = Path(__file__).resolve().parents[4]
AUTHORIZATION = ROOT / "data" / "acquisition-authorizations" / "us.fsis.json"


def _artifact(metadata: Mapping[str, Any], role: str) -> SourceArtifact:
    return SourceArtifact(
        source_url=str(metadata["final_url"]),
        retrieved_at_utc=str(metadata["retrieved_at_utc"]),
        sha256=str(metadata["sha256"]),
        byte_size=int(metadata["byte_size"]),
        publication_date=metadata.get("publication_date"),
        effective_date=metadata.get("effective_date"),
        code_version=CONFIG["adapter_version"],
        config_version=CONFIG["contract_version"],
        rights_caveat="Private preview only; no public redistribution terms or legal conclusion recorded.",
        privacy_caveat="Address and source-provided coordinates remain private pending privacy review.",
        coverage="Current FSIS MPI export only; state-inspection and APHIS populations excluded.",
    )


class FsisRefreshAdapter:
    """Acquire both current official exports and run FSIS's exact-ID lifecycle."""

    source_id = CONFIG["source_id"]
    adapter_version = CONFIG["adapter_version"]
    source_kind = "facility_master"
    fixture_paths = (
        Path(__file__).parent / "fixtures" / "valid.csv",
        Path(__file__).parent / "fixtures" / "demographics.csv",
    )
    fixture_path = fixture_paths[0]
    fixture_path = fixture_paths[0]
    fixture_path = fixture_paths[0]

    def acquire(self, *, run_dir: Path, options: Mapping[str, Any]) -> Mapping[str, Any]:
        review_paths = options.get("terms_review_paths")
        review = review_paths.get(self.source_id) if isinstance(review_paths, Mapping) else None
        if not review:
            raise ValueError("FSIS private-preview terms decision is required")
        authorization = json.loads(AUTHORIZATION.read_text(encoding="utf-8"))
        run_id = str(options.get("acquisition_run_id") or run_dir.name)
        max_bytes = int(options.get("max_bytes", 128 * 1024 * 1024))
        timeout = float(options.get("timeout_seconds", 60.0))
        output_root = run_dir / "acquisition"
        results: dict[str, Any] = {}
        routes = (
            ("directory", "us.fsis.directory", CONFIG["directory_by_number_url"], "directory.csv"),
            ("demographics", "us.fsis.demographics", CONFIG["demographics_url"], "demographics.csv"),
        )
        for role, source_id, url, filename in routes:
            results[role] = acquire_firefox(
                source_id=source_id,
                page_url=CONFIG["directory_url"],
                url=url,
                output_root=output_root,
                artifact_name=filename,
                terms_review_path=Path(str(review)),
                acquisition_authorization=authorization,
                run_id=run_id,
                max_attempts=2,
                max_bytes=max_bytes,
                navigation_timeout_seconds=min(timeout, 90.0),
                download_timeout_seconds=min(timeout, 120.0),
                code_version=self.adapter_version,
                config_version=CONFIG["contract_version"],
                coverage="FSIS MPI directory and supplemental demographics; state-inspection programs excluded",
                rights_caveat="Approved for private preview only; public redistribution terms remain unreviewed.",
                privacy_caveat="Private preview only; address and coordinate review pending.",
                artifact_validator=lambda path, headers, role=role: _validate_download(path, headers, role=role),
                require_public_link=True,
            )
        return {
            "artifact_path": results["directory"]["artifact_path"],
            "companion_artifact_path": results["demographics"]["artifact_path"],
            "acquisition": results,
        }

    def refresh(self, *, mode: str, run_dir: Path, artifact: Path | None,
                options: Mapping[str, Any]) -> Mapping[str, Any]:
        acquisition = options.get("acquisition")
        facts = acquisition.get("acquisition") if isinstance(acquisition, Mapping) else None
        # The mixed D3 rehearsal's local-artifact mode supplies its checked-in
        # fixture artifact without acquisition metadata. The live refresh runner
        # also invokes adapters in local-artifact mode after acquisition, but
        # always supplies both role-specific provenance records. Distinguish the
        # two by provenance, never by the mode name alone.
        if mode == "fixture" or (mode == "local-artifact" and not isinstance(facts, Mapping)):
            directory_path = Path(__file__).parent / "fixtures" / "valid.csv"
            demographics_path = Path(__file__).parent / "fixtures" / "demographics.csv"
            retrieved_at = "2026-01-01T00:00:00Z"
            artifact_facts = {
                role: {"final_url": CONFIG[f"{role}_url"] if role == "demographics" else CONFIG["directory_by_number_url"],
                       "retrieved_at_utc": retrieved_at, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                       "byte_size": path.stat().st_size, "effective_date": "unknown"}
                for role, path in (("directory", directory_path), ("demographics", demographics_path))
            }
        else:
            if artifact is None or not isinstance(facts, Mapping) or not isinstance(facts.get("directory"), Mapping) or not isinstance(facts.get("demographics"), Mapping):
                raise ValueError("FSIS refresh requires both freshly acquired artifacts and provenance")
            directory_path = artifact
            companion = acquisition.get("companion_artifact_path")
            if not isinstance(companion, str):
                raise ValueError("FSIS demographics export is missing")
            demographics_path = Path(companion)
            artifact_facts = facts

        roles = {"directory": _artifact(artifact_facts["directory"], "directory"),
                 "demographics": _artifact(artifact_facts["demographics"], "demographics")}
        source_adapter = FsisMpiAdapter()
        lifecycle = run_dir / "lifecycle"
        manifest = source_adapter.run_sources({"directory": directory_path, "demographics": demographics_path}, lifecycle, roles)
        bundle_hash = hashlib.sha256("".join(f"{role}:{roles[role].sha256}\n" for role in sorted(roles)).encode()).hexdigest()
        bundle = SourceArtifact(
            source_url=roles["directory"].source_url,
            retrieved_at_utc=roles["directory"].retrieved_at_utc,
            sha256=bundle_hash,
            byte_size=sum(item.byte_size for item in roles.values()),
            effective_date=roles["directory"].effective_date,
            code_version=self.adapter_version,
            config_version=CONFIG["contract_version"],
            rights_caveat=roles["directory"].rights_caveat,
            privacy_caveat=roles["directory"].privacy_caveat,
            coverage=roles["directory"].coverage,
        )
        handoff = source_adapter.write_candidate_handoff(
            lifecycle,
            roles["directory"],
            output_dir=run_dir / "candidate-handoff",
            bundle_artifact=bundle,
            source_artifacts={role: {
                "source_url": item.source_url, "retrieved_at_utc": item.retrieved_at_utc,
                "sha256": item.sha256, "byte_size": item.byte_size,
                "effective_date": item.effective_date,
            } for role, item in roles.items()},
        )
        return {
            "acquisition_classification": "live" if mode != "fixture" else "assisted",
            "input_rows": manifest["input_rows"],
            "normalized_rows": manifest["normalized_rows"],
            "quarantined_rows": manifest["quarantined_rows"],
            "candidate_observation_rows": handoff["normalized_rows"],
            "candidate_handoff_sha256": handoff["normalized_sha256"],
            "schema_fingerprint": manifest["schema_fingerprint"],
            "quarantine_reasons": manifest["anomaly_counts"],
            "source_metrics": manifest["source_metrics"],
            "row_reconciliation": manifest["row_reconciliation"],
            "directory_schema_fingerprint": manifest["schema_fingerprint"],
            "demographic_schema_fingerprint": manifest["demographic_schema_fingerprint"],
            "review_required": True,
            "publication_state": "private-preview-only",
            "candidate_handoff": True,
            "public_surfaces": {"api": False, "map": False, "csv": False},
        }
