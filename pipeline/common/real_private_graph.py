"""Discover and rehearse retained real-data graph handoffs.

The operator deliberately works from private manifests and handoff contracts.
It never copies rows into the repository and only returns aggregate data.  A
manifest is evidence of a private processing run, not evidence that a row is
approved, current, or safe to publish.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from pipeline.common.graph_persistence import ConnectionEdgeBuilder, import_evidence_events, import_graph_candidates


REPORT_VERSION = "d5-real-private-graph-v1"
EVIDENCE_CONTRACTS = {"us-aphis-observation-handoff-v1"}


@dataclass(frozen=True)
class ManifestRecord:
    path: Path
    source_id: str
    normalized_rows: int | None
    quarantined_rows: int | None
    candidate_rows: int | None
    graph_edges: int | None
    facility_candidates: int | None
    organization_candidates: int | None
    coordinate_states: dict[str, int]
    identity_counts: dict[str, int]
    digest: str
    integrity_status: str


def _integer(value: Any) -> int | None:
    return value if isinstance(value, int) and value >= 0 else None


def _source_id(payload: dict[str, Any]) -> str | None:
    if isinstance(payload.get("source_id"), str) and payload["source_id"].strip():
        return payload["source_id"].strip()
    source = payload.get("source")
    if isinstance(source, dict) and isinstance(source.get("source_id"), str):
        return source["source_id"].strip() or None
    return None


def _nested_int(payload: dict[str, Any], *paths: tuple[str, ...]) -> int | None:
    for path in paths:
        current: Any = payload
        for key in path:
            if not isinstance(current, dict):
                current = None
                break
            current = current.get(key)
        value = _integer(current)
        if value is not None:
            return value
    return None


def _counter(payload: dict[str, Any], *paths: tuple[str, ...]) -> dict[str, int]:
    for path in paths:
        current: Any = payload
        for key in path:
            if not isinstance(current, dict):
                current = None
                break
            current = current.get(key)
        if isinstance(current, dict):
            return {str(key): value for key, value in current.items() if isinstance(value, int) and value >= 0}
    return {}


def _manifest_record(path: Path, payload: dict[str, Any]) -> ManifestRecord | None:
    source_id = _source_id(payload)
    if not source_id:
        return None
    graph = payload.get("graph") if isinstance(payload.get("graph"), dict) else {}
    summary = payload.get("graph_candidate_summary") if isinstance(payload.get("graph_candidate_summary"), dict) else {}
    expected_normalized = payload.get("normalized_sha256")
    normalized_candidates = (
        path.parent / "normalized" / "records.jsonl",
        path.parent / "candidate-handoff" / "normalized" / "records.jsonl",
        path.parent / "records.jsonl",
    )
    normalized_path = next((candidate for candidate in normalized_candidates if candidate.is_file()), None)
    if isinstance(expected_normalized, str) and normalized_path is not None:
        try:
            actual = hashlib.sha256(normalized_path.read_bytes()).hexdigest()
            integrity_status = "verified-normalized" if actual == expected_normalized else "hash-mismatch"
        except OSError:
            integrity_status = "unavailable"
    else:
        source_meta = payload.get("source") if isinstance(payload.get("source"), dict) else {}
        source_url = payload.get("source_url") or payload.get("stable_url") or source_meta.get("source_url")
        retrieved = payload.get("retrieved_at_utc") or source_meta.get("retrieved_at_utc")
        declared_hash = (
            payload.get("sha256") or payload.get("checksum_sha256") or payload.get("source_artifact_sha256")
            or payload.get("operator_sha256") or payload.get("bytes_sha256") or source_meta.get("sha256")
        )
        if source_url and retrieved and declared_hash:
            integrity_status = "declared-artifact"
        else:
            integrity_status = "missing-provenance"
    return ManifestRecord(
        path=path,
        source_id=source_id,
        normalized_rows=_nested_int(payload, ("normalized_rows",), ("source", "private_rehearsal_normalized_rows")),
        quarantined_rows=_nested_int(payload, ("quarantined_rows",), ("source", "private_rehearsal_validation_findings")),
        candidate_rows=_nested_int(payload, ("candidate_rows",), ("candidate_handoff", "normalized_rows"), ("graph_candidate_summary", "candidate_count")),
        graph_edges=_nested_int(payload, ("graph_edges",), ("graph", "accepted_relationships"), ("graph_candidate_summary", "operator_relationship_candidates"), ("graph_candidates", "count")),
        facility_candidates=_nested_int(payload, ("graph_candidate_summary", "facility_identifier_candidates"), ("review_metrics", "facility_observation", "accepted_distinct_provisional_facility_keys")),
        organization_candidates=_nested_int(payload, ("graph_candidate_summary", "organization_identifier_candidates")),
        coordinate_states=_counter(payload, ("review_metrics", "geospatial", "coordinate_state_counts"), ("coordinate_state_counts",)),
        identity_counts=_counter(payload, ("review_metrics", "facility_observation", "identity_state_counts"), ("identity_state_counts",)),
        digest=hashlib.sha256(path.read_bytes()).hexdigest(),
        integrity_status=integrity_status,
    )


def _json_paths(root: Path) -> Iterable[Path]:
    if root.is_file() and root.suffix.lower() == ".json":
        yield root
    elif root.is_dir():
        for path in sorted(root.rglob("*.json")):
            # Avoid opening row-level JSON payloads while walking a large
            # private archive.  Operators can pass a specific JSON file when
            # a nonstandard aggregate manifest is required.
            name = path.name.casefold()
            parent = path.parent.name.casefold()
            if name == "manifest.json" or "manifest" in name or parent == "manifests" or any(
                token in name for token in ("report", "rehearsal", "release", "proof", "candidate", "evaluation", "status")
            ):
                yield path


def discover_manifests(roots: Iterable[str | Path]) -> list[ManifestRecord]:
    """Read only JSON metadata and return source aggregates, deduplicated."""
    records: list[ManifestRecord] = []
    seen: set[tuple[str, str]] = set()
    for value in roots:
        root = Path(value)
        for path in _json_paths(root):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError):
                continue
            if not isinstance(payload, dict):
                continue
            record = _manifest_record(path, payload)
            if record is None:
                # Some aggregate manifests contain a source list.  Expand
                # only the source summaries; no row-level content is read.
                for source in payload.get("sources", []):
                    if isinstance(source, dict):
                        child = dict(source)
                        child.setdefault("source_id", source.get("source_id"))
                        child.setdefault("normalized_rows", source.get("normalized_rows"))
                        child.setdefault("quarantined_rows", source.get("quarantined_rows"))
                        child_record = _manifest_record(path, child)
                        if child_record is not None:
                            key = (child_record.source_id, child_record.digest)
                            if key not in seen:
                                seen.add(key)
                                records.append(child_record)
                continue
            key = (record.source_id, record.digest)
            if key not in seen:
                seen.add(key)
                records.append(record)
    return sorted(records, key=lambda item: (item.source_id, str(item.path)))


def _private_state(payload: dict[str, Any]) -> bool:
    return (
        payload.get("release_state") in {None, "not-created", "candidate"}
        and payload.get("publication_state") in {None, "private-candidate"}
        and payload.get("publication_eligibility") in {None, "blocked"}
        and payload.get("public_release_created") is not True
        and payload.get("release_promoted") is not True
    )


def _handoffs(roots: Iterable[str | Path], source_ids: set[str]) -> list[tuple[str, str, Path]]:
    """Find explicit graph/evidence handoff roots without reading rows."""
    found: dict[tuple[str, str], tuple[str, str, Path]] = {}
    for value in roots:
        root = Path(value)
        if not root.exists():
            continue
        for manifest_path in root.rglob("manifest.json"):
            try:
                payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError):
                continue
            if not isinstance(payload, dict) or not _private_state(payload):
                continue
            source_id = _source_id(payload)
            if source_id not in source_ids:
                continue
            handoff_root = manifest_path.parent
            has_records = (handoff_root / "records.jsonl").is_file()
            has_graph_records = (handoff_root / "graph-candidates" / "records.jsonl").is_file()
            if not (has_records or has_graph_records):
                continue
            kind = "evidence" if payload.get("entity_scope") == "evidence_event" or payload.get("contract_version") in EVIDENCE_CONTRACTS else "facility"
            key = (source_id, kind)
            # Prefer the most recently declared artifact without exposing its
            # path in reports.  Stable lexical ordering breaks ties.
            existing = found.get(key)
            candidate = (source_id, kind, handoff_root)
            if existing is None or str(handoff_root) > str(existing[2]):
                found[key] = candidate
    return sorted(found.values(), key=lambda item: (item[0], item[1], str(item[2])))


def build_report(roots: Iterable[str | Path], *, selected_sources: Iterable[str] | None = None) -> dict[str, Any]:
    records = discover_manifests(roots)
    selected = {item.strip() for item in selected_sources or () if item.strip()}
    if selected:
        records = [item for item in records if item.source_id in selected]
    by_source: dict[str, list[ManifestRecord]] = {}
    for record in records:
        by_source.setdefault(record.source_id, []).append(record)
    sources = []
    for source_id in sorted(by_source):
        entries = by_source[source_id]
        # Acquisition retries and private QA copies commonly leave several
        # manifests for one source.  Select the most informative run rather
        # than summing retries, which would over-count real observations.
        def score(item: ManifestRecord) -> tuple[int, int, int, int, int, int, str]:
            return (
                item.normalized_rows or 0,
                item.quarantined_rows or 0,
                item.candidate_rows or 0,
                item.graph_edges or 0,
                item.facility_candidates or 0,
                item.organization_candidates or 0,
                item.digest,
            )
        chosen = max(entries, key=score)
        sources.append({
            "source_id": source_id,
            "manifest_count_seen": len(entries),
            "selected_manifest_digest": chosen.digest,
            "normalized_rows": chosen.normalized_rows,
            "quarantined_rows": chosen.quarantined_rows,
            "candidate_rows": chosen.candidate_rows,
            "graph_edge_candidates": chosen.graph_edges,
            "facility_identifier_candidates": chosen.facility_candidates,
            "organization_identifier_candidates": chosen.organization_candidates,
            "coordinate_state_counts": dict(sorted(chosen.coordinate_states.items())),
            "identity_state_counts": dict(sorted(chosen.identity_counts.items())),
            "integrity_status": chosen.integrity_status,
        })
    return {
        "schema_version": REPORT_VERSION,
        "scope": "private retained manifests only; raw rows and private filesystem paths excluded",
        "publication": {"release_created": False, "promoted": False, "public_rows": 0, "approval_inferred": False},
        "source_count": len(sources),
        "sources": sources,
        "totals": {
            key: sum(item[key] or 0 for item in sources)
            for key in ("normalized_rows", "quarantined_rows", "candidate_rows", "graph_edge_candidates", "facility_identifier_candidates", "organization_identifier_candidates")
        },
        "limitations": [
            "Manifest counts are not a completeness or accuracy claim.",
            "All rows remain private and review-required; no approval is inferred.",
            "A candidate edge is not a canonical identity or published relationship.",
            "Real precision and recall remain unmeasured without human-adjudicated labels.",
        ],
    }


def run_rehearsal(
    roots: Iterable[str | Path],
    *,
    selected_sources: Iterable[str] | None = None,
    database_url: str = "",
    disposable_db: bool = False,
    edge_builder: ConnectionEdgeBuilder | None = None,
) -> dict[str, Any]:
    report = build_report(roots, selected_sources=selected_sources)
    source_ids = {item["source_id"] for item in report["sources"]}
    handoffs = _handoffs(roots, source_ids)
    report["handoffs"] = {
        "discovered": len(handoffs),
        "facility": sum(kind == "facility" for _, kind, _ in handoffs),
        "evidence": sum(kind == "evidence" for _, kind, _ in handoffs),
        "source_ids": sorted({source_id for source_id, _, _ in handoffs}),
    }
    report["database"] = {"attempted": bool(database_url), "imports": [], "public_rows": 0}
    if database_url:
        if not disposable_db:
            raise ValueError("database rehearsal requires disposable_db=True")
        for source_id, kind, handoff_root in handoffs:
            importer = import_evidence_events if kind == "evidence" else import_graph_candidates
            try:
                import_kwargs = {"disposable_db": True}
                if kind == "facility" and edge_builder is not None:
                    # Keep the matcher lane injected: this rehearsal owns
                    # source discovery and persistence, not matching rules.
                    import_kwargs["edge_builder"] = edge_builder
                result = importer(database_url, handoff_root, **import_kwargs)
                report["database"]["imports"].append({"source_id": source_id, "kind": kind, "status": "completed", "result": {key: value for key, value in result.items() if isinstance(value, (int, float, bool, str))}})
            except Exception as exc:  # operator report records aggregate blocker, never payload
                report["database"]["imports"].append({"source_id": source_id, "kind": kind, "status": "blocked", "error_type": type(exc).__name__})
    report["database"]["completed"] = sum(item["status"] == "completed" for item in report["database"]["imports"])
    report["database"]["blocked"] = sum(item["status"] == "blocked" for item in report["database"]["imports"])
    return report


def write_report(report: dict[str, Any], output: str | Path) -> str:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()
