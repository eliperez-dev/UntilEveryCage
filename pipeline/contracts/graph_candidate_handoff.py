"""Small, deterministic candidate shape for future country adapters.

This is a private handoff contract only. It carries source-native identifiers
and local references; it intentionally has no universal or canonical identity
field and cannot authorize import, review, or publication.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any


CONTRACT_VERSION = "graph-candidate-handoff-v1"
GRAPH_DOMAINS = {
    "identity", "location", "operation", "ownership", "inspection", "violation",
    "commitment", "investigation", "public_funding", "animal_count", "other",
}
RELATIONSHIP_TYPES = {"operator", "regulator", "owner", "parent", "brand", "supplier", "customer"}
REVIEW_STATES = {"unreviewed", "review_required", "reviewed", "accepted", "rejected"}


def _required_text(value: Any, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")


def _optional_confidence(value: Any, field: str) -> None:
    if value is not None and (not isinstance(value, (int, float)) or not 0 <= value <= 1):
        raise ValueError(f"{field} must be null or between 0 and 1")


def _assert_date_like(value: Any, field: str) -> None:
    if value is not None and (not isinstance(value, str) or len(value) < 10):
        raise ValueError(f"{field} must be null or an ISO date/time string")


def _refs(items: Any, field: str) -> set[str]:
    if not isinstance(items, list):
        raise ValueError(f"{field} must be a list")
    refs: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            raise ValueError(f"{field} entries must be objects")
        _required_text(item.get("local_ref"), f"{field}.local_ref")
        ref = item["local_ref"]
        if ref in refs:
            raise ValueError(f"duplicate local_ref: {ref}")
        refs.add(ref)
        identifier = item.get("source_identifier")
        if not isinstance(identifier, dict):
            raise ValueError(f"{field}.source_identifier is required")
        _required_text(identifier.get("identifier_type"), f"{field}.source_identifier.identifier_type")
        _required_text(identifier.get("value"), f"{field}.source_identifier.value")
        if identifier.get("identity_scope", "source_scoped") != "source_scoped":
            raise ValueError("source identifiers must use source_scoped identity_scope")
    return refs


def validate_graph_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    """Validate and return a candidate without inferring identities."""
    if not isinstance(candidate, dict):
        raise ValueError("candidate must be an object")
    if candidate.get("contract_version") != CONTRACT_VERSION:
        raise ValueError(f"contract_version must be {CONTRACT_VERSION}")
    for field in ("source_id", "source_record_key"):
        _required_text(candidate.get(field), field)
    if not isinstance(candidate.get("source_row"), int) or candidate["source_row"] < 1:
        raise ValueError("source_row must be a positive integer")
    if not isinstance(candidate.get("source_values"), dict):
        raise ValueError("source_values must be an object")

    publication = candidate.get("publication")
    expected_publication = {
        "storage_state": "private",
        "privacy_status": "pending",
        "review_state": "review_required",
        "publication_status": "not_eligible",
        "release_id": None,
    }
    if publication != expected_publication:
        raise ValueError("candidate handoffs must remain private and not eligible for publication")

    forbidden = {"canonical_id", "global_id", "universal_id", "universal_identity"}
    if forbidden.intersection(candidate):
        raise ValueError("candidate must not assert a universal identity")

    facilities = _refs(candidate.get("facilities"), "facilities")
    organizations = _refs(candidate.get("organizations"), "organizations")
    all_refs = facilities | organizations
    if not facilities and not organizations:
        raise ValueError("candidate must contain at least one source-native entity")

    relationships = candidate.get("relationships", [])
    if not isinstance(relationships, list):
        raise ValueError("relationships must be a list")
    for relationship in relationships:
        if not isinstance(relationship, dict):
            raise ValueError("relationship entries must be objects")
        status = relationship.get("assertion_status", "asserted")
        if status not in {"asserted", "unknown", "disputed", "rejected"}:
            raise ValueError("relationship assertion_status is invalid")
        relationship_type = relationship.get("relationship_type")
        if status == "unknown":
            if relationship_type is not None or relationship.get("from_organization_ref") is not None:
                raise ValueError("unknown relationships cannot name a type or organization")
            _required_text(relationship.get("unknown_reason"), "relationship.unknown_reason")
        else:
            if relationship_type not in RELATIONSHIP_TYPES:
                raise ValueError("relationship_type is invalid")
            if relationship.get("from_organization_ref") not in organizations:
                raise ValueError("relationship.from_organization_ref must reference an organization")
            if relationship.get("unknown_reason") is not None:
                raise ValueError("known relationships cannot include unknown_reason")
        targets = [relationship.get("target_facility_ref"), relationship.get("target_organization_ref")]
        if sum(target is not None for target in targets) != 1 or (targets[0] is not None and targets[0] not in facilities) or (targets[1] is not None and targets[1] not in organizations):
            raise ValueError("relationship must reference exactly one valid target")
        _assert_date_like(relationship.get("valid_from"), "relationship.valid_from")
        _assert_date_like(relationship.get("valid_to"), "relationship.valid_to")
        _required_text(relationship.get("observed_at"), "relationship.observed_at")
        _optional_confidence(relationship.get("confidence"), "relationship.confidence")
        if relationship.get("review_state", "review_required") not in REVIEW_STATES:
            raise ValueError("relationship.review_state is invalid")

    claims = candidate.get("claims", [])
    if not isinstance(claims, list):
        raise ValueError("claims must be a list")
    for claim in claims:
        if not isinstance(claim, dict):
            raise ValueError("claim entries must be objects")
        if claim.get("claim_domain") not in GRAPH_DOMAINS:
            raise ValueError("claim.claim_domain is invalid")
        _required_text(claim.get("claim_kind"), "claim.claim_kind")
        targets = [claim.get("facility_ref"), claim.get("organization_ref")]
        if sum(target is not None for target in targets) != 1 or (targets[0] is not None and targets[0] not in facilities) or (targets[1] is not None and targets[1] not in organizations):
            raise ValueError("claim must reference exactly one valid subject")
        value_state = claim.get("value_state", "known")
        if value_state not in {"known", "unknown", "not_applicable", "withheld"}:
            raise ValueError("claim.value_state is invalid")
        if value_state == "unknown":
            _required_text(claim.get("unknown_reason"), "claim.unknown_reason")
        elif claim.get("unknown_reason") is not None:
            raise ValueError("known claims cannot include unknown_reason")
        _required_text(claim.get("observed_at"), "claim.observed_at")
        _optional_confidence(claim.get("confidence"), "claim.confidence")
        if not isinstance(claim.get("support"), list) or not claim["support"]:
            raise ValueError("claim.support must contain at least one artifact or source-record reference")
        for support in claim["support"]:
            if not isinstance(support, dict) or not (support.get("source_record_key") or support.get("artifact_sha256")):
                raise ValueError("claim.support entries need source_record_key or artifact_sha256")

    for crosswalk in candidate.get("crosswalks", []):
        if not isinstance(crosswalk, dict):
            raise ValueError("crosswalk entries must be objects")
        if crosswalk.get("left_ref") not in all_refs or crosswalk.get("right_ref") not in all_refs:
            raise ValueError("crosswalk refs must reference candidate entities")
        if crosswalk["left_ref"] == crosswalk["right_ref"]:
            raise ValueError("crosswalk cannot link an entity to itself")
        if crosswalk.get("identity_scope", "source_scoped") != "source_scoped":
            raise ValueError("crosswalks must remain source-scoped")
        _required_text(crosswalk.get("match_method"), "crosswalk.match_method")
        _optional_confidence(crosswalk.get("confidence"), "crosswalk.confidence")

    return candidate


def canonical_json_bytes(candidate: dict[str, Any]) -> bytes:
    validate_graph_candidate(candidate)
    return (json.dumps(candidate, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def write_graph_candidate(run_dir: str | Path, candidate: dict[str, Any]) -> dict[str, Any]:
    """Write one private candidate and a checksum manifest for handoff."""
    payload = canonical_json_bytes(candidate)
    root = Path(run_dir)
    root.mkdir(parents=True, exist_ok=True)
    target = root / "graph-candidate.json"
    temporary = target.with_name(target.name + ".tmp")
    temporary.write_bytes(payload)
    os.replace(temporary, target)
    return {
        "contract_version": CONTRACT_VERSION,
        "source_id": candidate["source_id"],
        "source_record_key": candidate["source_record_key"],
        "sha256": hashlib.sha256(payload).hexdigest(),
        "byte_size": len(payload),
        "publication_state": "private-candidate",
    }
