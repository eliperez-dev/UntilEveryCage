"""Shared restricted run coordination; it does not fetch or publish sources."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any, Callable

from pipeline.contracts.adapter_contract import SourceAdapter, SourceArtifact, source_artifact_from_mapping
from pipeline.contracts.private_run import write_private_run_report
from pipeline.contracts.source_health import build_health_snapshot, write_health_snapshot
from .identity import record_key
from .source_operations import classify_failure, finalize_run_operations

ORCHESTRATOR_VERSION = "v2-orchestrator-3"


def _atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
        os.replace(name, path)
    except Exception:
        try:
            os.unlink(name)
        except FileNotFoundError:
            pass
        raise


def register_input(raw: bytes, staging_dir: str | Path, config: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
    """Register caller-supplied bytes by hash. This function never downloads."""
    staging = Path(staging_dir)
    digest = hashlib.sha256(raw).hexdigest()
    artifact = staging / "raw" / f"{digest}.artifact"
    if not artifact.exists():
        _atomic(artifact, raw)
    metadata = {**config, "checksum_sha256": digest, "byte_size": len(raw),
                "orchestrator_version": ORCHESTRATOR_VERSION, "raw_artifact": str(artifact)}
    # Equal bytes can represent separate observations with different retrieval
    # metadata. Keep each observation while sharing the immutable raw bytes.
    registration = staging / "raw" / "registrations" / f"{uuid.uuid4().hex}.manifest.json"
    metadata["acquisition_manifest"] = str(registration)
    _atomic(registration, (json.dumps(metadata, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode())
    return artifact, metadata


def run_registered_input(raw_path: str | Path, runs_dir: str | Path, config: dict[str, Any],
                         adapter_runner: Callable[..., dict[str, Any]],
                         suppressed_ids: set[str | tuple[str, str, str]] | None = None,
                         prior_eligible_release: dict[str, Any] | None = None,
                         previous_normalized_path: str | Path | None = None,
                         review_blockers: dict[str, list[str]] | None = None) -> dict[str, Any]:
    """Run an adapter to a human-gated candidate, preserving prior release on failure."""
    raw = Path(raw_path)
    runs = Path(runs_dir)
    runs.mkdir(parents=True, exist_ok=True)
    run_dir = Path(tempfile.mkdtemp(prefix=f"{hashlib.sha256(raw.read_bytes()).hexdigest()[:16]}-", dir=runs))
    try:
        manifest = adapter_runner(raw, run_dir, config)
        records = [json.loads(line) for line in (run_dir / "normalized" / "records.jsonl").read_text(encoding="utf-8").splitlines() if line]
        suppressed = suppressed_ids or set()
        candidate = [r for r in records if record_key(r) not in suppressed]
        restricted = (config.get("terms_status") == "pending_confirmation"
                      or config.get("acquisition_status") == "restricted_pending_terms")
        if restricted:
            # Restricted inputs may be parsed and retained for review, but can
            # never create a publication candidate until terms are confirmed.
            status = {"status": "staged-restricted", "publication_state": "terms-gate-blocked",
                      "candidate_created": False, "release_promoted": False,
                      "public_surfaces": {"api": False, "map": False, "export": False,
                                          "cache": False, "history": False},
                      "geocoding": "disabled",
                      "suppressed_count": len(records) - len(candidate),
                      "manifest": manifest, "prior_eligible_release": prior_eligible_release}
        else:
            _atomic(run_dir / "release-candidate" / "records.jsonl",
                    b"".join((json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n").encode() for r in candidate))
            status = {"status": "candidate-ready", "publication_state": "human-gate-required",
                      "candidate_created": True, "release_promoted": False,
                      "suppressed_count": len(records) - len(candidate),
                      "manifest": manifest, "prior_eligible_release": prior_eligible_release}
    except Exception as exc:
        failure = classify_failure(exc)
        status = {"status": "failed", "publication_state": "unchanged", "release_promoted": False,
                  "error_type": type(exc).__name__, "error": str(exc),
                  "failure_class": failure["failure_class"], "attempts": getattr(exc, "attempts", []),
                  "prior_eligible_release": prior_eligible_release}
    status["run_dir"] = str(run_dir)
    # Health is emitted after run-status exists because it must prove that no
    # release was promoted.  Legacy adapters get the QA report too; health is
    # attempted only for the typed private publication state understood by
    # source_health.
    _atomic(run_dir / "run-status.json", (json.dumps(status, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode())
    if "manifest" in status and isinstance(status["manifest"], dict) and status["manifest"].get("source_id"):
        manifest = status["manifest"]
        try:
            write_private_run_report(
                run_dir,
                manifest,
                normalized_path=run_dir / "normalized" / "records.jsonl",
                previous_normalized_path=previous_normalized_path,
            )
            if manifest.get("publication_state") == "private-candidate":
                as_of = config.get("health_as_of_utc") or config.get("retrieved_at_utc")
                if as_of:
                    snapshot = build_health_snapshot(run_dir, as_of_utc=as_of)
                    write_health_snapshot(run_dir / "source-health.json", snapshot)
        except Exception as exc:
            # A candidate with invalid evidence is not ready for any later
            # gate.  Keep the files for diagnosis, but fail the run closed.
            failure = classify_failure(exc)
            status = {"status": "failed", "publication_state": "unchanged",
                      "release_promoted": False, "error_type": type(exc).__name__,
                      "error": f"private evidence: {exc}", "failure_class": failure["failure_class"],
                      "attempts": getattr(exc, "attempts", []),
                      "prior_eligible_release": prior_eligible_release,
                      "run_dir": str(run_dir)}
    status["run_dir"] = str(run_dir)
    status["run_id"] = config.get("run_id") or run_dir.name
    # The operations ledger is derived from the private run and is append-only.
    # It records review/diff artifacts without changing the adapter contract or
    # creating a release.  A ledger failure closes this run rather than leaving
    # an apparently complete run with missing operational evidence.
    try:
        status = finalize_run_operations(
            runs.parent, run_dir, manifest=status.get("manifest"), status=status,
            config={**config, "review_blockers": review_blockers or {}},
            previous_normalized_path=previous_normalized_path,
            prior_eligible_release=prior_eligible_release,
        )
    except Exception as exc:
        failure = classify_failure(exc)
        status = {
            "status": "failed", "publication_state": "unchanged", "release_promoted": False,
            "release_preserved": True, "error_type": type(exc).__name__,
            "error": f"source operations: {exc}", "failure_class": failure["failure_class"],
            "prior_eligible_release": prior_eligible_release, "run_dir": str(run_dir),
            "run_id": config.get("run_id") or run_dir.name,
        }
    _atomic(run_dir / "run-status.json", (json.dumps(status, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode())
    return status


def run_registered_typed_input(raw_path: str | Path, runs_dir: str | Path,
                               config: dict[str, Any], adapter: SourceAdapter,
                               suppressed_ids: set[str | tuple[str, str, str]] | None = None,
                               prior_eligible_release: dict[str, Any] | None = None,
                               previous_normalized_path: str | Path | None = None,
                               review_blockers: dict[str, list[str]] | None = None) -> dict[str, Any]:
    """Run a typed adapter from registered acquisition metadata.

    This is the compatibility seam for adapters whose ``run`` method accepts
    ``SourceArtifact`` rather than the legacy config mapping. The mapping is
    converted once at the shared boundary; the adapter still validates the
    raw bytes and writes its own private manifest.
    """
    artifact = source_artifact_from_mapping(config)

    def invoke(raw: str | Path, run_dir: str | Path, _config: dict[str, Any]) -> dict[str, Any]:
        return adapter.run(raw, run_dir, artifact)

    return run_registered_input(raw_path, runs_dir, config, invoke,
                                suppressed_ids=suppressed_ids,
                                prior_eligible_release=prior_eligible_release,
                                previous_normalized_path=previous_normalized_path,
                                review_blockers=review_blockers)


def run_private_lifecycle(raw_path: str | Path, runs_dir: str | Path,
                          artifact: SourceArtifact, adapter: SourceAdapter,
                          *, suppressed_ids: set[str | tuple[str, str, str]] | None = None,
                          prior_eligible_release: dict[str, Any] | None = None,
                          health_as_of_utc: str | None = None,
                          previous_normalized_path: str | Path | None = None,
                          review_blockers: dict[str, list[str]] | None = None) -> dict[str, Any]:
    """Run the canonical typed lifecycle from a preserved ``SourceArtifact``.

    This is the source-local integration seam for new countries.  Acquisition
    is deliberately absent: callers must provide an already preserved file and
    its recorded facts.  The adapter writes parsed/normalized/quarantined
    evidence, this runner writes QA/run status/health, and no release or API
    publication is possible here.
    """
    config = {
        "source_id": adapter.source_id,
        "source_url": artifact.source_url,
        "retrieved_at_utc": artifact.retrieved_at_utc,
        "checksum_sha256": artifact.sha256,
        "byte_size": artifact.byte_size,
        "publication_date": artifact.publication_date,
        "effective_date": artifact.effective_date,
        "code_version": artifact.code_version,
        "config_version": artifact.config_version,
        "rights_caveat": artifact.rights_caveat,
        "privacy_caveat": artifact.privacy_caveat,
        "coverage": artifact.coverage,
        "health_as_of_utc": health_as_of_utc or artifact.retrieved_at_utc,
    }
    return run_registered_typed_input(
        raw_path, runs_dir, config, adapter,
        suppressed_ids=suppressed_ids,
        prior_eligible_release=prior_eligible_release,
        previous_normalized_path=previous_normalized_path,
        review_blockers=review_blockers,
    )
