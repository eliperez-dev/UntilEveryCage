"""Shared private graph-candidate generation from explicit source identifiers."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Iterable

from pipeline.contracts.graph_candidate_handoff import (
    CONTRACT_VERSION,
    canonical_json_bytes,
)
from pipeline.contracts.source_lifecycle import atomic_bytes, atomic_json


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _stable_ref(prefix: str, value: str) -> str:
    digest = hashlib.sha256(f"{prefix}|{value}".encode()).hexdigest()[:16]
    return f"{prefix}:{digest}"


def build_identifier_graph_candidate(
    *,
    source_id: str,
    source_record_key: str,
    source_values: dict[str, Any],
    facility_identifier: tuple[str, str] | None,
    organization_identifier: tuple[str, str] | None,
    organization_identifiers: Iterable[tuple[str, str]] | None = None,
    observed_at: str,
    source_row: int = 1,
    artifact_sha256: str | None = None,
    signal_bundle: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a private candidate without fuzzy matching or canonical IDs."""
    if not _text(source_record_key):
        raise ValueError("source_record_key is required for graph candidate")
    organization_pairs = list(organization_identifiers or ())
    if organization_identifier:
        organization_pairs.insert(0, organization_identifier)
    # Keep a stable, source-local organization list when a row carries more
    # than one authoritative identifier (for example an Italian VAT and
    # fiscal-code value).  Duplicate pairs are harmless input noise and must
    # not create duplicate nodes or edges.
    organization_pairs = list(dict.fromkeys(
        (identifier_type, value)
        for identifier_type, value in organization_pairs
        if _text(identifier_type) and _text(value)
    ))
    if not facility_identifier and not organization_pairs:
        raise ValueError("an explicit facility or organization identifier is required")
    facilities: list[dict[str, Any]] = []
    organizations: list[dict[str, Any]] = []
    facility_ref = None
    organization_refs: list[str] = []
    if facility_identifier:
        identifier_type, value = facility_identifier
        facility_ref = _stable_ref("facility", f"{source_id}|{identifier_type}|{value}")
        facilities.append({"local_ref": facility_ref, "source_identifier": {"identifier_type": identifier_type, "value": value, "identity_scope": "source_scoped"}})
    for identifier_type, value in organization_pairs:
        organization_ref = _stable_ref("organization", f"{source_id}|{identifier_type}|{value}")
        organization_refs.append(organization_ref)
        organizations.append({"local_ref": organization_ref, "source_identifier": {"identifier_type": identifier_type, "value": value, "identity_scope": "source_scoped"}})
    relationships = []
    support = [{"source_record_key": source_record_key}]
    if artifact_sha256:
        support.append({"artifact_sha256": artifact_sha256})
    for organization_ref in organization_refs:
        if facility_ref:
            relationships.append({
                "relationship_type": "operator",
                "from_organization_ref": organization_ref,
                "target_facility_ref": facility_ref,
                "assertion_status": "asserted",
                "observed_at": observed_at,
                "valid_from": None,
                "valid_to": None,
                # The adapter emits evidence, not a calibrated probability.
                # D6 scoring owns confidence assignment downstream.
                "confidence": None,
                "confidence_basis": "source_asserted_identifier_cooccurrence",
                "connection_type": "exact",
                "signal_bundle": signal_bundle or [{"kind": "source_identifier_cooccurrence"}],
                "review_state": "review_required",
                "support": support,
                "evidence_method": "explicit source-native identifiers in one source observation",
            })
    return {
        "contract_version": CONTRACT_VERSION,
        "source_id": source_id,
        "source_record_key": source_record_key,
        "source_row": source_row if isinstance(source_row, int) and source_row > 0 else 1,
        "source_values": source_values,
        "facilities": facilities,
        "organizations": organizations,
        "relationships": relationships,
        "signal_bundle": signal_bundle or [{"kind": "source_identifier_cooccurrence"}],
        "claims": [],
        "crosswalks": [],
        "publication": {
            "storage_state": "private",
            "privacy_status": "pending",
            "review_state": "review_required",
            "publication_status": "not_eligible",
            "release_id": None,
        },
    }


def write_graph_candidates(run_dir: str | Path, candidates: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Write deterministic private JSONL graph candidates and row-free manifest."""
    ordered = sorted((candidate for candidate in candidates), key=lambda value: (value["source_id"], value["source_record_key"]))
    payload = b"".join(canonical_json_bytes(candidate) for candidate in ordered)
    root = Path(run_dir)
    target = root / "graph-candidates.jsonl"
    atomic_bytes(target, payload)
    relationship_count = sum(len(candidate.get("relationships", [])) for candidate in ordered)
    manifest = {
        "schema_version": "private-graph-candidate-batch-v1",
        "contract_version": CONTRACT_VERSION,
        "candidate_count": len(ordered),
        "facility_identifier_candidates": sum(bool(candidate.get("facilities")) for candidate in ordered),
        "organization_identifier_candidates": sum(bool(candidate.get("organizations")) for candidate in ordered),
        "operator_relationship_candidates": relationship_count,
        "review_required_count": len(ordered),
        "publication_status": "not_eligible",
        "storage_state": "private",
        "sha256": hashlib.sha256(payload).hexdigest(),
        "byte_size": len(payload),
        "row_payloads_included": True,
    }
    atomic_json(root / "graph-candidates-manifest.json", manifest)
    return manifest
