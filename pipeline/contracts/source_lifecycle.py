"""Small, source-agnostic primitives for private source lifecycles.

The lifecycle is intentionally a file contract rather than a framework:
``acquire -> preserve -> parse -> normalize -> validate -> health ->
candidate import -> guarded test-only API``.  Only the first six stages are
owned by this package.  Import and publication remain explicit gates in the
maintenance/API layers.

All writers below use a same-directory temporary file and ``os.replace``.
That matters for reruns: a failed stage must not leave a plausible partial
JSON or JSONL artifact that a later stage could mistake for a complete run.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


LIFECYCLE_CONTRACT_VERSION = "source-lifecycle-v1"
PRIVATE_PUBLICATION_STATES = {"private-candidate", "not-staged", "human-gate-required"}


@dataclass(frozen=True)
class SourceConfig:
    """The minimal checked-in identity/configuration shared by source packages."""

    source_id: str
    source_url: str
    adapter_version: str
    schema_version: str
    config_version: str = "unknown"
    coverage: str | None = None
    geocoding: str = "disabled"
    terms_status: str = "pending_confirmation"

    def __post_init__(self) -> None:
        for name in ("source_id", "source_url", "adapter_version", "schema_version", "config_version"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise ValueError(f"{name} must be a non-empty string")

    def as_mapping(self) -> dict[str, Any]:
        """Return a JSON-compatible mapping for legacy runner boundaries."""
        return {
            "source_id": self.source_id,
            "source_url": self.source_url,
            "adapter_version": self.adapter_version,
            "schema_version": self.schema_version,
            "config_version": self.config_version,
            "coverage": self.coverage,
            "geocoding": self.geocoding,
            "terms_status": self.terms_status,
        }


def atomic_bytes(path: str | Path, payload: bytes) -> Path:
    """Atomically write bytes and return ``path``.

    The target directory is created, but existing files are never removed
    before the replacement is ready.  This is safe for repeated local runs
    and leaves the previous complete artifact available after write errors.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
        os.replace(temporary_name, target)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise
    return target


def atomic_json(path: str | Path, value: dict[str, Any]) -> Path:
    """Atomically write canonical, UTF-8 JSON with a trailing newline."""
    payload = (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, default=list) + "\n").encode("utf-8")
    return atomic_bytes(path, payload)


def atomic_jsonl(path: str | Path, rows: Iterable[dict[str, Any]]) -> tuple[Path, str, int]:
    """Atomically write sorted-key JSONL and return path, hash, and row count."""
    payload = b"".join(
        (json.dumps(row, ensure_ascii=False, sort_keys=True, default=list) + "\n").encode("utf-8")
        for row in rows
    )
    return atomic_bytes(path, payload), hashlib.sha256(payload).hexdigest(), payload.count(b"\n")


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    """Read a deterministic JSONL artifact, rejecting malformed lines."""
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def validate_private_manifest(manifest: dict[str, Any]) -> None:
    """Validate the shared count and publication invariants."""
    required = {"source_id", "input_rows", "normalized_rows", "quarantined_rows", "release_state"}
    missing = sorted(required - manifest.keys())
    if missing:
        raise ValueError("manifest missing required keys: " + ", ".join(missing))
    counts = tuple(manifest[key] for key in ("input_rows", "normalized_rows", "quarantined_rows"))
    if any(not isinstance(value, int) or value < 0 for value in counts):
        raise ValueError("manifest row counts must be non-negative integers")
    if counts[0] != counts[1] + counts[2]:
        raise ValueError("manifest row counts do not reconcile")
    if manifest["release_state"] != "not-created":
        raise ValueError("private run cannot have a release")
    if manifest.get("publication_state") not in PRIVATE_PUBLICATION_STATES | {None}:
        raise ValueError("private run publication state is not restricted")


def private_manifest(
    *,
    source_id: str,
    adapter_version: str,
    schema_version: str,
    artifact: Any,
    input_rows: int,
    normalized_rows: int,
    quarantined_rows: int,
    normalized_sha256: str,
    parsed_sha256: str | None = None,
    anomaly_counts: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Create the common manifest envelope while retaining source details.

    Source adapters still own their field mappings and anomaly vocabulary;
    this helper owns only the stable provenance, count, and publication fields.
    """
    manifest: dict[str, Any] = {
        "contract_version": LIFECYCLE_CONTRACT_VERSION,
        "source_id": source_id,
        "adapter_version": adapter_version,
        "schema_version": schema_version,
        "source_url": artifact.source_url,
        "retrieved_at_utc": artifact.retrieved_at_utc,
        "publication_date": artifact.publication_date,
        "effective_date": artifact.effective_date,
        "sha256": artifact.sha256,
        "checksum_sha256": artifact.sha256,
        "byte_size": artifact.byte_size,
        "code_version": artifact.code_version,
        "config_version": artifact.config_version,
        "input_rows": input_rows,
        "normalized_rows": normalized_rows,
        "quarantined_rows": quarantined_rows,
        "normalized_sha256": normalized_sha256,
        "release_state": "not-created",
        "publication_state": "private-candidate",
        "review_state": "review_required",
        "privacy_gate": "pending",
        "coordinate_gate": "review_required",
        "anomaly_counts": anomaly_counts or {},
        "acquisition": artifact.__dict__,
    }
    if parsed_sha256 is not None:
        manifest["parsed_sha256"] = parsed_sha256
    validate_private_manifest(manifest)
    return manifest
