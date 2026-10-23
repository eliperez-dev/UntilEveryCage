"""Row-free coverage accounting for the finite retained graph corpus."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable


RELEASE_MANIFEST = Path(r"D:\UntilEveryCage-Operations\deployment\serving-20261018\release-2026-10-18-manifest.json")


def _read_object(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _candidate_manifests(roots: Iterable[str | Path]) -> dict[str, list[tuple[str, dict[str, Any]]]]:
    found: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    visited: set[Path] = set()
    for root_value in roots:
        root = Path(root_value)
        if not root.exists():
            continue
        for path in root.rglob("*.json"):
            if path.name not in {"manifest.json", "graph-candidates-manifest.json"} or path in visited:
                continue
            visited.add(path)
            manifest = _read_object(path)
            if not manifest:
                continue
            source_ids = manifest.get("source_ids")
            if not isinstance(source_ids, list):
                parent_manifest = _read_object(path.parent.parent / "manifest.json")
                source_id = manifest.get("source_id") or (parent_manifest or {}).get("source_id")
                source_ids = [source_id] if isinstance(source_id, str) else []
            for source_id in source_ids:
                if isinstance(source_id, str) and source_id.strip():
                    found.setdefault(source_id, []).append((hashlib.sha256(path.read_bytes()).hexdigest(), manifest))
    return found


def build_source_graph_coverage(
    roots: Iterable[str | Path],
    *,
    release_manifest_path: str | Path = RELEASE_MANIFEST,
    retained_private_source_ids: Iterable[str] = (),
) -> dict[str, Any]:
    """Build release plus retained-private source coverage without reading rows.

    Missing candidate runs are explicitly ``not-run``.  Candidate counts are
    chosen from the most informative single run per source rather than summed
    across retries, so the report cannot inflate coverage by duplicate runs.
    """
    release = _read_object(Path(release_manifest_path))
    if release is None:
        raise ValueError("release manifest is unavailable or malformed")
    coverage = release.get("source_coverage")
    if not isinstance(coverage, list):
        raise ValueError("release manifest has no source_coverage metadata")
    released: dict[str, int | None] = {}
    for item in coverage:
        if isinstance(item, dict) and isinstance(item.get("source_id"), str):
            rows = item.get("row_count")
            released[item["source_id"]] = rows if isinstance(rows, int) and rows >= 0 else None
    if isinstance(release.get("source_ids"), list):
        released = {str(source_id): released.get(str(source_id)) for source_id in release["source_ids"]}
    private_ids = {item.strip() for item in retained_private_source_ids if isinstance(item, str) and item.strip()}
    by_source = _candidate_manifests(roots)
    source_ids = sorted(set(released) | private_ids | set(by_source))
    sources: list[dict[str, Any]] = []
    for source_id in source_ids:
        runs = by_source.get(source_id, [])
        chosen = max(runs, key=lambda pair: (
            pair[1].get("candidate_rows", pair[1].get("candidate_count", 0)) or 0,
            pair[1].get("facility_identifier_candidates", 0) or 0,
            pair[1].get("name_assertion_candidates", 0) or 0,
            pair[0],
        )) if runs else None
        manifest = chosen[1] if chosen else {}
        status = "not-run" if chosen is None else "participating"
        sources.append({
            "source_id": source_id,
            "scope": "released" if source_id in released else "retained-private",
            "released_records": released.get(source_id),
            "graph_status": status,
            "run_manifests_seen": len(runs),
            "selected_manifest_sha256": chosen[0] if chosen else None,
            "candidate_rows": manifest.get("candidate_rows", manifest.get("candidate_count", 0)) if chosen else 0,
            "facility_identifier_candidates": manifest.get("facility_identifier_candidates", 0) if chosen else 0,
            "organization_identifier_candidates": manifest.get("organization_identifier_candidates", 0) if chosen else 0,
            "name_assertion_candidates": manifest.get("name_assertion_candidates", 0) if chosen else 0,
            "location_role_counts": manifest.get("location_role_counts", {}) if chosen else {},
            "business_contact_candidates": manifest.get("business_contact_candidates", 0) if chosen else 0,
            "evidence_event_candidates": manifest.get("event_count", manifest.get("evidence_event_candidates", 0)) if chosen else 0,
        })
    return {
        "schema_version": "private-graph-source-coverage-v1",
        "release_id": release.get("release_id"),
        "release_records": sum(value or 0 for value in released.values()),
        "released_source_count": len(released),
        "retained_private_source_count": len(private_ids),
        "sources": sources,
        "totals": {
            key: sum(item.get(key) or 0 for item in sources)
            for key in ("released_records", "candidate_rows", "facility_identifier_candidates",
                        "organization_identifier_candidates", "name_assertion_candidates",
                        "business_contact_candidates", "evidence_event_candidates")
        },
        "privacy": {"rows_emitted": False, "private_handoff_values_emitted": False, "publication_authorized": False},
    }


__all__ = ["RELEASE_MANIFEST", "build_source_graph_coverage"]
