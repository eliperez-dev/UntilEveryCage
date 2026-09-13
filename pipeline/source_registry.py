"""Load and validate the repository-backed legacy source registry.

This module is deliberately offline: validation never fetches URLs or opens
legacy data files. The registry records what the repository demonstrates, not
what a live source currently publishes.
"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse


REGISTRY_PATH = Path(__file__).with_name("source_registry.json")
REQUIRED_FIELDS = {
    "source_id", "jurisdiction_scope", "legacy_paths", "url", "access_method",
    "cadence", "attribution_licensing_notes", "adapter_status",
    "expected_artifact_schema", "blockers",
}
VALID_ADAPTER_STATUSES = {"not_started", "reference_only", "implemented_partial", "implemented"}


class SourceRegistryError(ValueError):
    """Raised when the registry is malformed or contradicts repository state."""


def load_registry(path: Path = REGISTRY_PATH, *, repository_root: Path | None = None) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise SourceRegistryError(f"registry is not valid JSON: {error.msg}") from error
    validate_registry(payload, repository_root=repository_root or path.parents[1])
    return payload


def validate_registry(payload: object, *, repository_root: Path | None = None) -> None:
    if not isinstance(payload, dict):
        raise SourceRegistryError("registry must be an object")
    if payload.get("registry_version") != "1.0":
        raise SourceRegistryError("registry_version 1.0 is required")
    if not isinstance(payload.get("evidence_basis"), str) or not payload["evidence_basis"]:
        raise SourceRegistryError("evidence_basis must be a non-empty string")
    if payload.get("unknown_value") != "unknown":
        raise SourceRegistryError("unknown_value must be the explicit string 'unknown'")
    sources = payload.get("sources")
    if not isinstance(sources, list) or not sources:
        raise SourceRegistryError("sources must be a non-empty list")
    seen: set[str] = set()
    root = repository_root
    for index, source in enumerate(sources):
        prefix = f"sources[{index}]"
        if not isinstance(source, dict):
            raise SourceRegistryError(f"{prefix} must be an object")
        missing = REQUIRED_FIELDS - source.keys()
        if missing:
            raise SourceRegistryError(f"{prefix} missing fields: {sorted(missing)}")
        for field in {
            "source_id", "jurisdiction_scope", "url", "access_method", "cadence",
            "attribution_licensing_notes", "adapter_status", "expected_artifact_schema",
        }:
            if not isinstance(source[field], str) or not source[field]:
                raise SourceRegistryError(f"{prefix}.{field} must be a non-empty string")
        source_id = source["source_id"]
        if source_id in seen:
            raise SourceRegistryError(f"{prefix}.source_id must be unique and non-empty")
        seen.add(source_id)
        if source["url"] != "unknown":
            parsed = urlparse(source["url"])
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise SourceRegistryError(f"{prefix}.url must be an http(s) URL or 'unknown'")
        if source["adapter_status"] not in VALID_ADAPTER_STATUSES:
            raise SourceRegistryError(f"{prefix}.adapter_status is not recognized")
        if not isinstance(source["legacy_paths"], list) or not source["legacy_paths"]:
            raise SourceRegistryError(f"{prefix}.legacy_paths must be non-empty")
        if not all(isinstance(item, str) and item for item in source["legacy_paths"]):
            raise SourceRegistryError(f"{prefix}.legacy_paths must contain non-empty strings")
        if not isinstance(source["blockers"], list) or not all(isinstance(item, str) and item for item in source["blockers"]):
            raise SourceRegistryError(f"{prefix}.blockers must be a list of non-empty strings")
        if root is not None:
            for relative_path in source["legacy_paths"]:
                try:
                    resolved_root = root.resolve()
                    candidate = (root / relative_path).resolve()
                    candidate.relative_to(resolved_root)
                except (OSError, ValueError) as error:
                    raise SourceRegistryError(f"{prefix} legacy path escapes repository: {relative_path}") from error
                if not candidate.exists():
                    raise SourceRegistryError(f"{prefix} legacy path does not exist: {relative_path}")


def source_ids(path: Path = REGISTRY_PATH) -> tuple[str, ...]:
    """Return stable IDs in registry order after offline validation."""
    return tuple(item["source_id"] for item in load_registry(path)["sources"])
