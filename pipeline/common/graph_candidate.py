"""Shared private graph-candidate generation for source adapters.

The builder only uses identifiers and claims already present in one source
record.  It never performs fuzzy matching, proximity joins, or universal-ID
assignment.  Output is private review evidence and cannot authorize import or
publication.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from pipeline.contracts.graph_candidate_handoff import validate_graph_candidate
from pipeline.common.graph_source_mapping import (
    additional_source_identifiers,
    location_role as mapped_location_role,
    name_assertions,
    operator_asserted,
    organization_identifiers,
    source_identifier,
)


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
    source_id = str(record.get("source_id") or "unknown")
    identifier = source_identifier(source_id, normalized if isinstance(normalized, dict) else {})
    if identifier:
        return f"{source_id}|{identifier['identifier_type']}|{identifier['value']}"
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
    typed_identifier = source_identifier(source_id, normalized)
    if not typed_identifier:
        raise ValueError("graph candidate requires a source-native establishment identifier")
    source_values = record.get("source_values") if isinstance(record.get("source_values"), dict) else {}
    facility_aliases = additional_source_identifiers(source_id, normalized, source_values)
    observed = _text(observed_at) or _text(normalized.get("observed_at")) or "unknown-observation-date"
    facility_ref = _local_ref("facility", source_id, source_key)
    facilities = [{
        "local_ref": facility_ref,
        "source_identifier": {
            **typed_identifier,
        },
        **({"additional_source_identifiers": facility_aliases} if facility_aliases else {}),
    }]

    mapped_organizations = organization_identifiers(source_id, normalized, source_values)
    organizations: list[dict[str, Any]] = []
    organization_refs: list[str] = []
    if mapped_organizations:
        primary, *aliases = mapped_organizations
        organization_ref = _local_ref(
            "organization", source_id,
            f"{source_key}|{primary['identifier_type']}|{primary['value']}",
        )
        organization_refs.append(organization_ref)
        organization_entity: dict[str, Any] = {
            "local_ref": organization_ref,
            "source_identifier": {key: primary[key] for key in (
                "identifier_type", "value", "id_namespace", "identity_scope")},
        }
        if aliases:
            organization_entity["additional_source_identifiers"] = aliases
        organizations.append(organization_entity)

    support: list[dict[str, str]] = [{"source_record_key": source_key}]
    if artifact_sha256:
        support.append({"artifact_sha256": artifact_sha256})
    relationships: list[dict[str, Any]] = []
    if operator_asserted(source_id, source_values):
        for organization_ref in organization_refs:
            relationships.append({
                "relationship_type": "operator", "from_organization_ref": organization_ref,
                "target_facility_ref": facility_ref, "assertion_status": "asserted",
                "observed_at": observed, "valid_from": None, "valid_to": None,
                "confidence": None, "confidence_basis": "source_asserted_identifier_cooccurrence",
                "connection_type": "exact",
                "signal_bundle": [{"kind": "source_identifier_cooccurrence",
                                   "identifier_types": [item["identifier_type"] for item in mapped_organizations],
                                   "connection_type": "exact"}],
                "review_state": "review_required", "support": support,
                "evidence_method": "explicit source-native identifiers in one source observation",
            })
    claims: list[dict[str, Any]] = [{
        "claim_domain": "identity",
        "claim_kind": "source_establishment",
        "facility_ref": facility_ref,
        "value_state": "known",
        "value": typed_identifier["value"],
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
    assertions = name_assertions(
        source_id, normalized,
        record.get("source_values") if isinstance(record.get("source_values"), dict) else None,
    )
    for assertion in assertions:
        claims.append({
            "claim_domain": "identity",
            "claim_kind": f"source_{assertion['role']}_name",
            "facility_ref": facility_ref,
            "value_state": "known",
            "value": assertion["value"],
            "observed_at": observed,
            "confidence": None,
            "review_state": "review_required",
            "support": support,
        })

    business_name_aliases = _fsis_business_name_aliases(record) if source_id == "us.fsis" else []
    candidate = {
        "contract_version": "graph-candidate-handoff-v1",
        "source_id": source_id,
        "source_record_key": source_key,
        "source_row": record.get("source_row"),
        "source_values": record.get("source_values", {}),
        # Exact private normalized context is retained for the shared matcher
        # and replay tooling. Eligibility comes only from typed fields below.
        "normalized_values": normalized,
        "name_assertions": assertions,
        "location_role": mapped_location_role(
            source_id, normalized,
            record.get("source_values") if isinstance(record.get("source_values"), dict) else None,
        ),
        # Only this source-native, explicitly named alias field is eligible
        # for the private shared-business-name matcher.  It is not an owner
        # or operator assertion and is never emitted as public edge text.
        **({"shared_business_name_aliases": business_name_aliases} if business_name_aliases else {}),
        "facilities": facilities,
        "organizations": organizations,
        "relationships": relationships,
        "claims": claims,
        "crosswalks": [],
        "contradiction_state": "none-observed",
        "review_state": "review_required",
        "publication": PUBLICATION,
    }
    validate_graph_candidate(candidate)
    return candidate


def _fsis_business_name_aliases(record: dict[str, Any]) -> list[str]:
    """Return only retained FSIS DBA/alternate-name evidence for private matching."""
    normalized = record.get("normalized")
    if not isinstance(normalized, dict):
        return []
    aliases: list[str] = []
    for field in ("alternate_names", "dba_names"):
        value = normalized.get(field)
        values = value if isinstance(value, (list, tuple)) else [value]
        for item in values:
            if isinstance(item, str) and item.strip():
                aliases.append(item.strip())
    return list(dict.fromkeys(aliases))


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
        "source_ids": sorted({candidate["source_id"] for candidate in candidates}),
        "candidate_rows": len(candidates),
        "facility_identifier_candidates": sum(bool(candidate.get("facilities")) for candidate in candidates),
        "organization_identifier_candidates": sum(bool(candidate.get("organizations")) for candidate in candidates),
        "name_assertion_candidates": sum(len(candidate.get("name_assertions", [])) for candidate in candidates),
        "location_role_counts": dict(sorted(Counter(candidate.get("location_role", "unknown") for candidate in candidates).items())),
        "business_contact_candidates": sum(len(candidate.get("business_contacts", [])) for candidate in candidates),
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
