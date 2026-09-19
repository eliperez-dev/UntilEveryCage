"""Shared private graph-candidate generation for source adapters.

The builder only uses identifiers and claims already present in one source
record.  It never performs fuzzy matching, proximity joins, or universal-ID
assignment.  Output is private review evidence and cannot authorize import or
publication.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from pipeline.contracts.graph_candidate_handoff import validate_graph_candidate


PUBLICATION = {
    "storage_state": "private",
    "privacy_status": "pending",
    "review_state": "review_required",
    "publication_status": "not_eligible",
    "release_id": None,
}


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _source_key(record: dict[str, Any]) -> str:
    for key in ("source_record_key", "source_row_id"):
        value = _text(record.get(key))
        if value:
            return value
    normalized = record.get("normalized") or {}
    identifier = _text(normalized.get("establishment_id")) or _text(normalized.get("approval_number"))
    if identifier:
        return f"{record.get('source_id')}|{identifier}"
    return f"{record.get('source_id')}|row-{record.get('source_row')}"


def _local_ref(prefix: str, source_id: str, source_key: str) -> str:
    digest = hashlib.sha256(f"{source_id}|{source_key}".encode("utf-8")).hexdigest()[:20]
    return f"{prefix}:{source_id}:{digest}"


def build_graph_candidate(
    record: dict[str, Any],
    *,
    artifact_sha256: str | None = None,
    observed_at: str | None = None,
) -> dict[str, Any]:
    """Build one source-local, review-required graph candidate."""
    source_id = _text(record.get("source_id"))
    source_key = _source_key(record)
    if not source_id:
        raise ValueError("graph candidate requires source_id")
    normalized = record.get("normalized")
    if not isinstance(normalized, dict):
        raise ValueError("graph candidate requires normalized source evidence")
    identifier = _text(normalized.get("establishment_id")) or _text(normalized.get("approval_number"))
    if not identifier:
        raise ValueError("graph candidate requires a source-native establishment identifier")
    observed = _text(observed_at) or _text(normalized.get("observed_at")) or "unknown-observation-date"
    facility_ref = _local_ref("facility", source_id, source_key)
    facilities = [{
        "local_ref": facility_ref,
        "source_identifier": {
            "identifier_type": "source_establishment_id",
            "value": identifier,
            "identity_scope": "source_scoped",
        },
    }]

    support: list[dict[str, str]] = [{"source_record_key": source_key}]
    if artifact_sha256:
        support.append({"artifact_sha256": artifact_sha256})
    claims: list[dict[str, Any]] = [{
        "claim_domain": "identity",
        "claim_kind": "source_establishment",
        "facility_ref": facility_ref,
        "value_state": "known",
        "value": identifier,
        "observed_at": observed,
        "confidence": None,
        "review_state": "review_required",
        "support": support,
    }]
    categories = normalized.get("activity_categories") or ()
    if categories:
        claims.append({
            "claim_domain": "operation",
            "claim_kind": "source_activity_categories",
            "facility_ref": facility_ref,
            "value_state": "known",
            "value": list(categories),
            "observed_at": observed,
            "confidence": None,
            "review_state": "review_required",
            "support": support,
        })
    source_label = _text(normalized.get("name")) or _text(normalized.get("trading_name"))
    if source_label:
        claims.append({
            "claim_domain": "identity",
            "claim_kind": "source_label",
            "facility_ref": facility_ref,
            "value_state": "known",
            "value": source_label,
            "observed_at": observed,
            "confidence": None,
            "review_state": "review_required",
            "support": support,
        })

    candidate = {
        "contract_version": "graph-candidate-handoff-v1",
        "source_id": source_id,
        "source_record_key": source_key,
        "source_row": record.get("source_row"),
        "source_values": record.get("source_values", {}),
        "facilities": facilities,
        "organizations": [],
        "relationships": [],
        "claims": claims,
        "crosswalks": [],
        "contradiction_state": "none-observed",
        "review_state": "review_required",
        "publication": PUBLICATION,
    }
    validate_graph_candidate(candidate)
    return candidate


def write_graph_candidates(
    run_dir: str | Path,
    records: Iterable[dict[str, Any]],
    *,
    artifact_sha256: str | None = None,
    observed_at: str | None = None,
    quarantined_rows: int = 0,
) -> dict[str, Any]:
    """Write deterministic private graph candidates and a row-free manifest."""
    root = Path(run_dir)
    root.mkdir(parents=True, exist_ok=True)
    candidates = [build_graph_candidate(record, artifact_sha256=artifact_sha256, observed_at=observed_at) for record in records]
    candidates.sort(key=lambda candidate: (candidate["source_id"], candidate["source_record_key"], candidate["source_row"]))
    payload = b"".join((json.dumps(candidate, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8") for candidate in candidates)
    records_path = root / "records.jsonl"
    records_path.write_bytes(payload)
    manifest = {
        "schema_version": "private-graph-candidate-set-v1",
        "contract_version": "graph-candidate-handoff-v1",
        "candidate_rows": len(candidates),
        "quarantined_source_rows": quarantined_rows,
        "records_sha256": hashlib.sha256(payload).hexdigest(),
        "storage_state": "private",
        "privacy_status": "pending",
        "review_state": "review_required",
        "publication_status": "not_eligible",
        "release_id": None,
        "auto_merge": False,
        "contradictions": "source-local contradiction/review states preserved; no cross-source merge performed",
    }
    (root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return manifest
