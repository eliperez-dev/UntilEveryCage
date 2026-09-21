"""Contracts for the source-neutral private refresh runner.

The runner deliberately accepts summaries, not rows.  Adapters remain the
owners of source parsing and normalization; this module defines the stable
control-plane vocabulary used to select, retry, resume, and report runs.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

REFRESH_CONTRACT_VERSION = "private-refresh-v1"
MODES = frozenset({"fixture", "local-artifact", "live-acquisition"})
SOURCE_KINDS = frozenset({"facility_master", "evidence_event"})


class RefreshAdapter(Protocol):
    source_id: str
    adapter_version: str
    source_kind: str

    def refresh(self, *, mode: str, run_dir: Path, artifact: Path | None,
                options: Mapping[str, Any]) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class AdapterCapabilities:
    source_id: str
    adapter_version: str
    schema_version: str
    acquisition: str
    geocoding: str
    publication: str
    adapter_path: str | None = None
    country_code: str | None = None
    source_kind: str = "facility_master"

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "AdapterCapabilities":
        required = ("source_id", "adapter_version", "schema_version", "acquisition", "geocoding", "publication")
        missing = [key for key in required if not value.get(key)]
        if missing:
            raise ValueError("adapter capability missing: " + ", ".join(missing))
        source_kind = value.get("source_kind", "facility_master")
        if source_kind not in SOURCE_KINDS:
            raise ValueError(f"source_kind must be one of {sorted(SOURCE_KINDS)}")
        return cls(**{key: value.get(key) for key in (
            "source_id", "adapter_version", "schema_version", "acquisition", "geocoding", "publication", "adapter_path", "country_code")}, source_kind=source_kind)


@dataclass(frozen=True)
class RefreshRequest:
    source_ids: tuple[str, ...] = ()
    all_eligible: bool = False
    mode: str = "fixture"
    artifact_paths: Mapping[str, str] = field(default_factory=dict)
    output_root: Path = Path("data/staging/private-refresh")
    retries: int = 0
    resume: bool = False
    import_candidates: bool = False
    database_url: str | None = None
    options: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.mode not in MODES:
            raise ValueError(f"mode must be one of {sorted(MODES)}")
        if self.all_eligible and self.source_ids:
            raise ValueError("choose explicit source_ids or all_eligible, not both")
        if not self.all_eligible and not self.source_ids:
            raise ValueError("at least one source or --all-eligible is required")
        if self.retries < 0 or self.retries > 5:
            raise ValueError("retries must be between 0 and 5")
        if self.import_candidates and not self.database_url:
            raise ValueError("database_url is required when candidate import is enabled")


def canonical_plan(request: RefreshRequest, selected: tuple[str, ...], capabilities: Mapping[str, AdapterCapabilities]) -> dict[str, Any]:
    """Return the row-free deterministic plan used for run identity."""
    artifacts = {source: request.artifact_paths.get(source) for source in selected}
    versions = {source: capabilities[source].adapter_version for source in selected if source in capabilities}
    payload = {
        "contract_version": REFRESH_CONTRACT_VERSION,
        "sources": list(selected), "mode": request.mode,
        "artifacts": artifacts, "adapter_versions": versions,
        "source_kinds": {source: capabilities[source].source_kind for source in selected if source in capabilities},
        "retries": request.retries, "import_candidates": request.import_candidates,
        "options": row_free_summary(request.options),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    payload["plan_hash"] = hashlib.sha256(encoded).hexdigest()
    payload["run_id"] = "refresh-" + payload["plan_hash"][:16]
    return payload


def row_free_summary(summary: Mapping[str, Any]) -> dict[str, Any]:
    """Copy an adapter summary while rejecting accidental row-bearing output."""
    forbidden = {"row", "rows", "records", "normalized", "source_values", "payload", "raw"}
    def clean(value: Any, key: str | None = None) -> Any:
        if key in forbidden:
            raise ValueError(f"adapter summary contains row-bearing key: {key}")
        if isinstance(value, Mapping):
            return {str(k): clean(v, str(k)) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [clean(v) for v in value]
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        return str(value)
    return clean(dict(summary))


@dataclass(frozen=True)
class RegisteredAdapter:
    capabilities: AdapterCapabilities
    adapter: RefreshAdapter
