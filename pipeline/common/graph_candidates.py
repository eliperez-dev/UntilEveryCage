"""Shared private graph-candidate generation from explicit source identifiers."""
from __future__ import annotations

import hashlib
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from pipeline.contracts.graph_candidate_handoff import (
    CONTRACT_VERSION,
    canonical_json_bytes,
)
from pipeline.contracts.source_lifecycle import atomic_bytes, atomic_json
from pipeline.common.graph_source_mapping import (
    additional_source_identifiers,
    location_role as mapped_location_role,
    name_assertions as mapped_name_assertions,
    operator_asserted as mapped_operator_asserted,
    organization_identifiers as mapped_organization_identifiers,
)


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _stable_ref(prefix: str, value: str) -> str:
    digest = hashlib.sha256(f"{prefix}|{value}".encode()).hexdigest()[:16]
    return f"{prefix}:{digest}"


def _identifier_namespace(source_id: str, identifier_type: str) -> str:
    # Italian VAT is issued under the same national authority namespace in
    # both retained ministry registers; other native IDs remain source-local.
    if source_id in {"it.1069-2009", "it.853-2004"} and identifier_type == "italian_vat":
        return "it.tax-authority.vat"
    if identifier_type == "australian_business_number":
        return "au.abr.abn"
    if identifier_type == "australian_company_number":
        return "au.asic.acn"
    if identifier_type == "brazil_cnpj":
        return "br.receita.cnpj"
    if identifier_type == "cvr":
        return "dk.virk.cvr"
    return source_id


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
    normalized_values: dict[str, Any] | None = None,
    name_assertions: list[dict[str, str]] | None = None,
    location_role: str | None = None,
    business_contacts: list[dict[str, str]] | None = None,
    operator_asserted: bool | None = None,
) -> dict[str, Any]:
    """Build a private candidate without fuzzy matching or canonical IDs."""
    if not _text(source_record_key):
        raise ValueError("source_record_key is required for graph candidate")
    organization_pairs = list(organization_identifiers or ())
    normalized_context = normalized_values if isinstance(normalized_values, dict) else {}
    mapped_ids = mapped_organization_identifiers(source_id, normalized_context, source_values)
    organization_pairs.extend((item["identifier_type"], item["value"]) for item in mapped_ids)
    if organization_identifier:
        organization_pairs.insert(0, organization_identifier)
    # A source row can carry multiple authoritative IDs for one registered
    # business. Preserve the first as primary and attach the others as typed
    # aliases on that same entity; never mint extra entities from co-location.
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
        facility_entity = {"local_ref": facility_ref, "source_identifier": {"identifier_type": identifier_type, "id_namespace": _identifier_namespace(source_id, identifier_type), "value": value, "identity_scope": "source_scoped"}}
        aliases = additional_source_identifiers(source_id, normalized_context, source_values)
        if aliases:
            facility_entity["additional_source_identifiers"] = aliases
        facilities.append(facility_entity)
    if organization_pairs:
        identifier_type, value = organization_pairs[0]
        organization_ref = _stable_ref("organization", f"{source_id}|{identifier_type}|{value}")
        organization_refs.append(organization_ref)
        namespace = next((item["id_namespace"] for item in mapped_ids
                          if item["identifier_type"] == identifier_type and item["value"] == value),
                         _identifier_namespace(source_id, identifier_type))
        organization = {"local_ref": organization_ref, "source_identifier": {
            "identifier_type": identifier_type, "id_namespace": namespace,
            "value": value, "identity_scope": "source_scoped"}}
        aliases = []
        for alias_type, alias_value in organization_pairs[1:]:
            alias_namespace = next((item["id_namespace"] for item in mapped_ids
                                    if item["identifier_type"] == alias_type and item["value"] == alias_value),
                                   _identifier_namespace(source_id, alias_type))
            if alias_type != identifier_type or alias_value != value:
                aliases.append({"identifier_type": alias_type, "value": alias_value,
                                "id_namespace": alias_namespace, "identity_scope": "source_scoped"})
        if aliases:
            organization["additional_source_identifiers"] = aliases
        organizations.append(organization)
    if operator_asserted is None:
        operator_asserted = mapped_operator_asserted(source_id, source_values)
    if name_assertions is None:
        name_assertions = mapped_name_assertions(source_id, normalized_context, source_values)
    if location_role is None:
        location_role = mapped_location_role(source_id, normalized_context, source_values)
    relationships = []
    support = [{"source_record_key": source_record_key}]
    if artifact_sha256:
        support.append({"artifact_sha256": artifact_sha256})
    for organization_ref in organization_refs:
        if facility_ref and operator_asserted:
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
        **({"normalized_values": normalized_values} if normalized_values is not None else {}),
        **({"name_assertions": name_assertions} if name_assertions else {}),
        "location_role": location_role,
        **({"business_contacts": business_contacts} if business_contacts else {}),
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
        "source_ids": sorted({candidate["source_id"] for candidate in ordered}),
        "candidate_count": len(ordered),
        "facility_identifier_candidates": sum(bool(candidate.get("facilities")) for candidate in ordered),
        "organization_identifier_candidates": sum(bool(candidate.get("organizations")) for candidate in ordered),
        "operator_relationship_candidates": relationship_count,
        "name_assertion_candidates": sum(len(candidate.get("name_assertions", [])) for candidate in ordered),
        "location_role_counts": dict(sorted(Counter(candidate.get("location_role", "unknown") for candidate in ordered).items())),
        "business_contact_candidates": sum(len(candidate.get("business_contacts", [])) for candidate in ordered),
        "review_required_count": len(ordered),
        "publication_status": "not_eligible",
        "storage_state": "private",
        "sha256": hashlib.sha256(payload).hexdigest(),
        "byte_size": len(payload),
        "row_payloads_included": True,
    }
    atomic_json(root / "graph-candidates-manifest.json", manifest)
    return manifest
