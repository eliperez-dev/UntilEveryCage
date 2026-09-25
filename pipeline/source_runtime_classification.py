"""Runtime discovery classes joined from the source and preview registries.

The preview policy is the explicit private E2E allowlist.  The source registry
and source-status baseline provide the universe and the non-preview fallback;
this module does not grant publication eligibility.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pipeline.source_registry import load_registry


ROOT = Path(__file__).resolve().parents[1]
PREVIEW_POLICY = ROOT / "pipeline" / "preview-enabled-sources.json"
STATUS_PATH = ROOT / "docs" / "source-status.json"
CLASSES = {"production-e2e", "research-blocked", "fixture-only"}


class RuntimeClassificationError(ValueError):
    """Raised when runtime discovery inputs disagree or are incomplete."""


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeClassificationError(f"invalid classification input: {path}") from error
    if not isinstance(value, dict):
        raise RuntimeClassificationError(f"classification input must be an object: {path}")
    return value


def build_runtime_classification_index() -> dict[str, Any]:
    """Join source modules with the strict preview allowlist and status data."""
    registered = {item["source_id"] for item in load_registry()["sources"]}
    status_payload = _read_json(STATUS_PATH)
    status_items = status_payload.get("sources")
    if not isinstance(status_items, list):
        raise RuntimeClassificationError("source status must contain a sources list")
    statuses = {item.get("source_id"): item for item in status_items if isinstance(item, dict)}
    if set(statuses) != registered:
        raise RuntimeClassificationError("source and source-status IDs do not match")

    policy = _read_json(PREVIEW_POLICY)
    preview_sources = policy.get("sources")
    if not isinstance(preview_sources, dict) or not set(preview_sources).issubset(registered):
        raise RuntimeClassificationError("preview policy contains unknown sources")

    rows: dict[str, dict[str, Any]] = {}
    for source_id in sorted(registered):
        status = statuses[source_id]
        preview = preview_sources.get(source_id)
        if isinstance(preview, dict) and preview.get("enabled") is True:
            classification = preview.get("runtime_classification")
            if classification != "production-e2e" or preview.get("public_release") is not False:
                raise RuntimeClassificationError(
                    f"enabled private-preview source lacks a production-e2e/public-release boundary: {source_id}"
                )
        elif status.get("acquisition") == "blocked":
            classification = "research-blocked"
        else:
            classification = "fixture-only"
        if classification not in CLASSES:
            raise RuntimeClassificationError(f"unsupported runtime classification for {source_id}")
        rows[source_id] = {
            "classification": classification,
            "private_preview_enabled": classification == "production-e2e",
            "public_release": False,
        }
    return {
        "schema_version": "source-runtime-classification-v1",
        "source_count": len(rows),
        "sources": rows,
        "authority": "pipeline/preview-enabled-sources.json plus pipeline/source_registry.json and docs/source-status.json",
    }


def require_production_preview_source(source_id: str) -> dict[str, Any]:
    """Fail closed unless the source is explicitly allowed in private E2E."""
    index = build_runtime_classification_index()["sources"]
    source = index.get(source_id)
    if not source or source["classification"] != "production-e2e" or not source["private_preview_enabled"]:
        raise RuntimeClassificationError(f"source is not production-e2e enabled: {source_id}")
    return source
