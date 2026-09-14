"""Shared restricted run coordination; it does not fetch or publish sources."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Callable

ORCHESTRATOR_VERSION = "v2-orchestrator-1"


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
    _atomic(staging / "raw" / f"{digest}.manifest.json",
            (json.dumps(metadata, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode())
    return artifact, metadata


def run_registered_input(raw_path: str | Path, runs_dir: str | Path, config: dict[str, Any],
                         adapter_runner: Callable[..., dict[str, Any]],
                         suppressed_ids: set[str] | None = None,
                         prior_eligible_release: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run an adapter to a human-gated candidate, preserving prior release on failure."""
    raw = Path(raw_path)
    run_dir = Path(runs_dir) / hashlib.sha256(raw.read_bytes()).hexdigest()[:16]
    try:
        manifest = adapter_runner(raw, run_dir, config)
        records = [json.loads(line) for line in (run_dir / "normalized" / "records.jsonl").read_text(encoding="utf-8").splitlines() if line]
        suppressed = suppressed_ids or set()
        candidate = [r for r in records if r.get("source_id") not in suppressed]
        restricted = config.get("acquisition_status") == "restricted_pending_terms"
        if restricted:
            # Restricted inputs may be parsed and retained for review, but can
            # never create a publication candidate until terms are confirmed.
            status = {"status": "staged-restricted", "publication_state": "restricted",
                      "candidate_created": False, "release_promoted": False,
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
        status = {"status": "failed", "publication_state": "unchanged", "release_promoted": False,
                  "error_type": type(exc).__name__, "error": str(exc),
                  "prior_eligible_release": prior_eligible_release}
    _atomic(run_dir / "run-status.json", (json.dumps(status, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode())
    return status
