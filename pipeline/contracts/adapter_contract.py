from __future__ import annotations
import hashlib
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Protocol
from .source_lifecycle import read_jsonl


@dataclass(frozen=True)
class SourceArtifact:
    """Immutable acquisition facts supplied to a source adapter."""
    source_url: str
    retrieved_at_utc: str
    sha256: str
    byte_size: int
    publication_date: str | None = None
    effective_date: str | None = None
    code_version: str = "unknown"
    config_version: str = "unknown"
    rights_caveat: str | None = None
    privacy_caveat: str | None = None
    coverage: str | None = None
    redirects: tuple[dict[str, Any], ...] = ()


def source_artifact_from_mapping(values: dict[str, Any]) -> SourceArtifact:
    """Convert legacy config dictionaries at a source-local boundary only."""
    required = ("source_url", "retrieved_at_utc", "byte_size")
    missing = [key for key in required if not values.get(key)]
    if not values.get("checksum_sha256") and not values.get("sha256"):
        missing.append("checksum_sha256")
    if missing:
        raise ValueError("missing acquisition provenance: " + ", ".join(missing))
    return SourceArtifact(
        source_url=str(values["source_url"]), retrieved_at_utc=str(values["retrieved_at_utc"]),
        sha256=str(values.get("checksum_sha256") or values["sha256"]), byte_size=int(values["byte_size"]),
        publication_date=values.get("publication_date"), effective_date=values.get("effective_date"),
        code_version=str(values.get("code_version", "unknown")), config_version=str(values.get("config_version", "unknown")),
        rights_caveat=values.get("rights_caveat"), privacy_caveat=values.get("privacy_caveat"), coverage=values.get("coverage"),
        redirects=tuple(values.get("redirects") or ()))


def source_artifact_from_acquisition(
    metadata: dict[str, Any], *, adapter_version: str, config_version: str,
    source_url: str | None = None, coverage: str | None = None,
    rights_caveat: str | None = None, privacy_caveat: str | None = None,
) -> SourceArtifact:
    """Build the typed adapter boundary from either fetch or local metadata.

    Acquisition metadata uses ``sha256``; older callers use
    ``checksum_sha256``.  Keeping this compatibility here prevents every
    source adapter from reimplementing provenance normalization.
    """
    values = dict(metadata)
    values.setdefault("source_url", values.get("final_url") or source_url)
    values.setdefault("retrieved_at_utc", values.get("requested_at_utc"))
    values.setdefault("checksum_sha256", values.get("sha256"))
    values.setdefault("coverage", coverage)
    values.setdefault("rights_caveat", rights_caveat)
    values.setdefault("privacy_caveat", privacy_caveat)
    values["code_version"] = adapter_version
    values["config_version"] = config_version
    return source_artifact_from_mapping(values)


class SourceAdapter(Protocol):
    """Minimal boundary between acquisition evidence and private staging."""
    source_id: str
    adapter_version: str

    def run(self, raw_path: str | Path, run_dir: str | Path, artifact: SourceArtifact) -> dict[str, Any]: ...


def assert_manifest(manifest: dict, raw: bytes, schema_version: str) -> None:
    """Assert safety invariants shared by adapter tests; not a release gate."""
    assert manifest["checksum_sha256"] == hashlib.sha256(raw).hexdigest()
    assert manifest["byte_size"] == len(raw)
    assert manifest["schema_version"] == schema_version
    assert manifest["input_rows"] == manifest["normalized_rows"] + manifest["quarantined_rows"]
    assert manifest["release_state"] == "not-created"
