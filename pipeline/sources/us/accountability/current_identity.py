"""Private current-US identity integration for APHIS and FSIS observations.

This module consumes accepted records from the source-local adapters.  It
creates source-scoped crosswalk candidates only; it never creates a canonical
identity, writes a graph database, or authorizes publication.

The two supported link families are deliberately narrow:

* APHIS registrations -> annual reports and inspections, using APHIS
  certificate/customer identifiers.
* FSIS establishments -> FSIS observations, using establishment/approval
  identifiers carried by both records.

Names and addresses are a bounded review queue only.  They are never a
fallback identity decision and are not used across APHIS and FSIS source
families.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

from pipeline.contracts.source_lifecycle import atomic_json, atomic_jsonl


CONTRACT_VERSION = "us-current-identity-graph-v1"
PUBLICATION = {
    "storage_state": "private",
    "privacy_status": "pending",
    "review_state": "review_required",
    "publication_status": "not_eligible",
    "release_id": None,
}
APHIS_PROFILES = frozenset({"registrations", "annual_reports", "amendments", "inspections"})
ALTERNATE_PAIRS = {
    ("registrations", "annual_reports"),
    ("registrations", "amendments"),
    ("registrations", "inspections"),
    ("fsis_establishments", "fsis_observations"),
}
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class CurrentIdentityContractError(ValueError):
    """Input records or provenance cannot satisfy the private contract."""


def _text(value: Any) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _profile(record: Mapping[str, Any], fallback: str | None = None) -> str:
    normalized = record.get("normalized")
    if isinstance(normalized, Mapping):
        value = _text(normalized.get("evidence_type"))
        if value:
            return value
    return _text(record.get("profile")) or fallback or "unknown"


def _source_key(record: Mapping[str, Any]) -> str:
    value = _text(record.get("source_record_key"))
    if not value:
        raise CurrentIdentityContractError("record lacks source_record_key")
    return value


def _normalized(record: Mapping[str, Any]) -> Mapping[str, Any]:
    value = record.get("normalized")
    if not isinstance(value, Mapping):
        raise CurrentIdentityContractError("record lacks normalized evidence")
    return value


def _identifiers(record: Mapping[str, Any], profile: str) -> dict[str, str]:
    """Return source-qualified official identifiers without inventing one."""
    normalized = _normalized(record)
    source_id = _text(record.get("source_id")) or ""
    if source_id == "us.aphis" or profile in APHIS_PROFILES:
        fields = (
            ("aphis_certificate_number", "certificate_number"),
            ("aphis_customer_number", "customer_number"),
        )
    elif source_id == "us.fsis" or profile == "fsis_establishments":
        fields = (
            ("fsis_establishment_id", "establishment_id"),
            ("fsis_establishment_number", "establishment_number"),
        )
    else:
        fields = (
            ("fsis_establishment_id", "establishment_id"),
            ("fsis_establishment_number", "establishment_number"),
            ("observation_id", "observation_id"),
        )
    return {identifier_type: value for identifier_type, field in fields if (value := _text(normalized.get(field)))}


def _observation_date(record: Mapping[str, Any]) -> str | None:
    normalized = _normalized(record)
    for field in ("observed_at", "status_date", "grant_date"):
        value = _text(normalized.get(field))
        if value:
            return value
    year = _text(normalized.get("report_year"))
    if year and year.isdigit() and len(year) == 4:
        return f"{year}-12-31"
    value = _text(record.get("observed_at"))
    return value


def _valid_datetime(value: str | None) -> bool:
    if not value:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _provenance(
    provenance: Mapping[Any, Mapping[str, Any]],
    *,
    source_id: str,
    profile: str,
) -> dict[str, str] | None:
    """Resolve per-profile provenance, falling back to source-wide metadata."""
    profile_keys = [profile]
    # Amendments are versioned rows in the annual-report capture unless a
    # separate amendment artifact was explicitly supplied.
    if profile == "amendments":
        profile_keys.append("annual_reports")
    values = None
    for profile_key in profile_keys:
        values = (
            provenance.get((source_id, profile_key))
            or provenance.get(f"{source_id}:{profile_key}")
        )
        if values:
            break
    values = values or provenance.get(source_id)
    if not isinstance(values, Mapping):
        return None
    digest = _text(values.get("artifact_sha256") or values.get("sha256"))
    url = _text(values.get("source_url") or values.get("final_url"))
    retrieved = _text(values.get("retrieved_at_utc"))
    if not digest or not _HEX64.fullmatch(digest.lower()) or not url or not _valid_datetime(retrieved):
        return None
    return {
        "artifact_sha256": digest.lower(),
        "source_url": url,
        "retrieved_at_utc": retrieved,
    }


def _suppressed(record: Mapping[str, Any]) -> bool:
    normalized = record.get("normalized")
    values = [record.get("suppression_state"), record.get("privacy_status")]
    if isinstance(normalized, Mapping):
        values.extend((normalized.get("privacy_gate"), normalized.get("privacy_status")))
    return any(_text(value) in {"suppressed", "restricted", "failed", "suppressed_or_restricted"} for value in values)


def _stable_id(prefix: str, *parts: str) -> str:
    material = "\0".join((prefix, *parts))
    return f"{prefix}-{hashlib.sha256(material.encode('utf-8')).hexdigest()[:24]}"


def _node(record: Mapping[str, Any], profile: str, provenance: Mapping[str, str] | None) -> dict[str, Any]:
    source_id = _text(record.get("source_id")) or "unknown"
    source_key = _source_key(record)
    return {
        "entity_id": _stable_id("us-identity-entity", source_id, source_key),
        "entity_type": profile,
        "source_id": source_id,
        "source_record_key": source_key,
        "official_identifiers": _identifiers(record, profile),
        "observed_at": _observation_date(record),
        "evidence": {
            "source_record_key": source_key,
            **(provenance or {}),
        },
        "publication": dict(PUBLICATION),
        "test_only": True,
    }


def _name_address(record: Mapping[str, Any]) -> tuple[str | None, str | None, list[str]]:
    normalized = _normalized(record)
    raw = record.get("source_values")
    source_values = raw if isinstance(raw, Mapping) else {}

    def value_for(field: str) -> str | None:
        direct = _text(normalized.get(field))
        if direct:
            return direct
        wanted = _norm(field)
        for source_field, source_value in source_values.items():
            if _norm(str(source_field)) == wanted:
                return _text(source_value)
        return None

    name = next(
        (value for field in ("canonical_name", "account_name", "name", "facility_name", "establishment_name", "trading_name", "operator_name") if (value := value_for(field))),
        None,
    )
    address_parts: list[tuple[str, str]] = []
    for label, fields in (
        ("street", ("street", "Address Line 1", "address_line_1")),
        ("city", ("city", "City")),
        ("state", ("state", "State")),
        ("postal_code", ("postal_code", "zip", "Zip")),
    ):
        value = next((value for field in fields if (value := value_for(field))), None)
        if value:
            address_parts.append((label, value))
    fields = [label for label, _ in address_parts]
    address = "|".join(_norm(value) for _, value in address_parts) if address_parts else None
    return (_norm(name) if name else None), address, fields


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _candidate(
    left: Mapping[str, Any],
    left_profile: str,
    right: Mapping[str, Any],
    right_profile: str,
    *,
    method: str,
    confidence: float,
    matched_identifiers: Mapping[str, str] | None,
    matched_fields: list[str] | None,
    provenance: Mapping[Any, Mapping[str, Any]],
    assertion_status: str = "candidate",
    reason: str | None = None,
) -> dict[str, Any]:
    left_source = _text(left.get("source_id")) or "unknown"
    right_source = _text(right.get("source_id")) or "unknown"
    left_key = _source_key(left)
    right_key = _source_key(right)
    left_provenance = _provenance(provenance, source_id=left_source, profile=left_profile)
    right_provenance = _provenance(provenance, source_id=right_source, profile=right_profile)
    provenance_ok = left_provenance is not None and right_provenance is not None
    evidence = {
        "source_record_keys": [left_key, right_key],
        "source_profiles": [left_profile, right_profile],
        "provenance": {
            f"{left_source}:{left_profile}": left_provenance,
            f"{right_source}:{right_profile}": right_provenance,
        },
        "matched_identifier_types": sorted((matched_identifiers or {}).keys()),
        "matched_fields": sorted(matched_fields or []),
    }
    identity = "|".join((left_source, left_key, right_source, right_key, method))
    result: dict[str, Any] = {
        "candidate_id": _stable_id("us-identity-candidate", identity),
        "candidate_type": "source_entity_crosswalk",
        "relationship_type": "observation_of_registration" if left_profile == "registrations" else "observation_of_establishment",
        "left": {"source_id": left_source, "source_record_key": left_key, "profile": left_profile},
        "right": {"source_id": right_source, "source_record_key": right_key, "profile": right_profile},
        "match_method": method,
        "matched_identifiers": dict(sorted((matched_identifiers or {}).items())),
        "confidence": confidence,
        "review_state": "review_required",
        "assertion_status": assertion_status,
        "observation_dates": [_observation_date(left), _observation_date(right)],
        "evidence": evidence,
        "publication": dict(PUBLICATION),
        "test_only": True,
    }
    if reason:
        result["quarantine_reason"] = reason
        result["reason"] = reason
    elif method == "exact_official_identifier":
        matched = ", ".join(sorted((matched_identifiers or {}).keys())) or "source-native identifiers"
        result["confidence_explanation"] = f"Exact agreement on {matched}; source records remain separate and require review."
    elif method == "alternate_name_address_exact":
        result["confidence_explanation"] = "Exact normalized name and complete address agreement is a review candidate only; no official identifier matched."
    else:
        result["confidence_explanation"] = "No defensible identity evidence was accepted; retained for private review only."
    if not provenance_ok and not reason:
        result["quarantine_reason"] = "missing_or_invalid_provenance"
        result["assertion_status"] = "quarantined"
        result["confidence_explanation"] = "Candidate lacks complete artifact provenance and is quarantined."
    return result


def _records_for(records: Iterable[Mapping[str, Any]], profile: str) -> list[Mapping[str, Any]]:
    if isinstance(records, Mapping):
        records = records.get("accepted", ())
    return [record for record in records if _profile(record, profile) == profile]


def _official_pairs(
    left_records: list[Mapping[str, Any]],
    left_profile: str,
    right_records: list[Mapping[str, Any]],
    right_profile: str,
) -> tuple[list[tuple[Mapping[str, Any], Mapping[str, Any], dict[str, str]]], list[dict[str, Any]]]:
    # Candidate generation must be keyed by an exact shared official value.
    # Comparing every registration with every report/inspection would turn a
    # pair of unrelated records with different certificate numbers into a
    # false ``conflicting_official_identifiers`` quarantine.  It also scales
    # quadratically on the real APHIS capture.  A conflict is meaningful only
    # after at least one source-native identifier has made the pair a candidate
    # (for example, the same customer number but a different certificate).
    right_index: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    collision_keys: dict[tuple[str, str, str | None], set[str]] = defaultdict(set)
    for record in right_records:
        source_key = _source_key(record)
        observed_at = _observation_date(record)
        for identifier_type, value in _identifiers(record, right_profile).items():
            key = (identifier_type, value)
            right_index[key].append(record)
            collision_keys[(identifier_type, value, observed_at)].add(source_key)

    pairs: list[tuple[Mapping[str, Any], Mapping[str, Any], dict[str, str]]] = []
    quarantined: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for left in left_records:
        left_ids = _identifiers(left, left_profile)
        possible_right: dict[str, Mapping[str, Any]] = {}
        for identifier_type, value in left_ids.items():
            for right in right_index.get((identifier_type, value), ()):
                possible_right[_source_key(right)] = right
        for right in possible_right.values():
            right_ids = _identifiers(right, right_profile)
            shared = {kind: value for kind, value in left_ids.items() if right_ids.get(kind) == value}
            conflicts = [kind for kind in set(left_ids) & set(right_ids) if left_ids[kind] != right_ids[kind]]
            if conflicts:
                quarantined.append({
                    "reason": "conflicting_official_identifiers",
                    "left_source_record_key": _source_key(left),
                    "right_source_record_key": _source_key(right),
                    "identifier_types": sorted(conflicts),
                    "_left_record": left,
                    "_right_record": right,
                })
                continue
            if not shared:
                continue
            identity_key = (_source_key(left), _source_key(right), ",".join(sorted(shared)))
            if identity_key in seen:
                continue
            seen.add(identity_key)
            collision = any(
                len(collision_keys[(kind, value, _observation_date(right))]) > 1
                for kind, value in shared.items()
            )
            if collision:
                quarantined.append({
                    "reason": "ambiguous_official_identifier",
                    "left_source_record_key": _source_key(left),
                    "right_source_record_key": _source_key(right),
                    "identifier_types": sorted(shared),
                    "_left_record": left,
                    "_right_record": right,
                })
            else:
                pairs.append((left, right, shared))
    return pairs, quarantined


def _alternate_pairs(
    left_records: list[Mapping[str, Any]],
    right_records: list[Mapping[str, Any]],
) -> tuple[list[tuple[Mapping[str, Any], Mapping[str, Any], list[str]]], list[dict[str, Any]]]:
    left_index: dict[tuple[str, str], list[tuple[Mapping[str, Any], list[str]]]] = defaultdict(list)
    right_index: dict[tuple[str, str], list[tuple[Mapping[str, Any], list[str]]]] = defaultdict(list)
    for record in left_records:
        name, address, fields = _name_address(record)
        if name and address:
            left_index[(name, address)].append((record, fields))
    for record in right_records:
        name, address, fields = _name_address(record)
        if name and address:
            right_index[(name, address)].append((record, fields))

    pairs: list[tuple[Mapping[str, Any], Mapping[str, Any], list[str]]] = []
    quarantined: list[dict[str, Any]] = []
    for key in sorted(set(left_index) & set(right_index)):
        lefts = left_index[key]
        rights = right_index[key]
        if len(lefts) != 1 or len(rights) != 1:
            for left, _ in lefts:
                for right, _ in rights:
                    quarantined.append({
                        "reason": "ambiguous_alternate_name_address",
                        "left_source_record_key": _source_key(left),
                        "right_source_record_key": _source_key(right),
                        "matched_fields": ["name", "address"],
                        "_left_record": left,
                        "_right_record": right,
                    })
            continue
        left, left_fields = lefts[0]
        right, right_fields = rights[0]
        left_ids = _identifiers(left, _profile(left))
        right_ids = _identifiers(right, _profile(right))
        conflicts = [kind for kind in set(left_ids) & set(right_ids) if left_ids[kind] != right_ids[kind]]
        if conflicts:
            quarantined.append({
                "reason": "conflicting_official_identifiers",
                "left_source_record_key": _source_key(left),
                "right_source_record_key": _source_key(right),
                "identifier_types": sorted(conflicts),
                "_left_record": left,
                "_right_record": right,
            })
            continue
        pairs.append((left, right, sorted(set(left_fields + right_fields))))
    return pairs, quarantined


def _quarantine_candidate(
    left: Mapping[str, Any],
    left_profile: str,
    right: Mapping[str, Any],
    right_profile: str,
    *,
    reason: str,
    method: str = "unresolved",
    provenance: Mapping[Any, Mapping[str, Any]],
    matched_fields: list[str] | None = None,
) -> dict[str, Any]:
    return _candidate(
        left,
        left_profile,
        right,
        right_profile,
        method=method,
        confidence=0.0,
        matched_identifiers=None,
        matched_fields=matched_fields,
        provenance=provenance,
        assertion_status="quarantined",
        reason=reason,
    )


def build_current_identity_graph(
    *,
    aphis_records: Mapping[str, Iterable[Mapping[str, Any]]],
    fsis_records: Iterable[Mapping[str, Any]],
    fsis_observations: Iterable[Mapping[str, Any]] = (),
    provenance: Mapping[Any, Mapping[str, Any]],
) -> dict[str, Any]:
    """Build deterministic private crosswalk candidates from adapter records.

    ``aphis_records`` is keyed by ``registrations``, ``annual_reports``, and
    ``inspections``.  The values are the accepted record objects returned by
    ``AphisPublicSearchAdapter.parse_bytes``.  ``fsis_records`` contains the
    accepted FSIS establishment objects; observations use the same record
    shape and should expose ``establishment_id`` or ``establishment_number``
    in ``normalized``.
    """
    registrations = _records_for(aphis_records.get("registrations", ()), "registrations")
    annual_reports = _records_for(aphis_records.get("annual_reports", ()), "annual_reports")
    amendments = _records_for(aphis_records.get("annual_reports", ()), "amendments")
    amendments.extend(_records_for(aphis_records.get("amendments", ()), "amendments"))
    inspections = _records_for(aphis_records.get("inspections", ()), "inspections")
    establishments = _records_for(fsis_records, "fsis_establishments")
    observations = _records_for(fsis_observations, "fsis_observations")

    all_records: list[tuple[Mapping[str, Any], str]] = []
    all_records.extend((record, "registrations") for record in registrations)
    all_records.extend((record, "annual_reports") for record in annual_reports)
    all_records.extend((record, "amendments") for record in amendments)
    all_records.extend((record, "inspections") for record in inspections)
    all_records.extend((record, "fsis_establishments") for record in establishments)
    all_records.extend((record, "fsis_observations") for record in observations)
    nodes = []
    for record, profile in all_records:
        nodes.append(_node(record, profile, _provenance(provenance, source_id=_text(record.get("source_id")) or "unknown", profile=profile)))
    nodes.sort(key=lambda node: node["entity_id"])

    candidates: list[dict[str, Any]] = []
    quarantined: list[dict[str, Any]] = []

    for left_profile, right_profile, left, right in (
        ("registrations", "annual_reports", registrations, annual_reports),
        ("registrations", "amendments", registrations, amendments),
        ("registrations", "inspections", registrations, inspections),
        ("fsis_establishments", "fsis_observations", establishments, observations),
    ):
        pairs, pair_quarantine = _official_pairs(left, left_profile, right, right_profile)
        conflicting_pairs = {
            (_text(item.get("left_source_record_key")), _text(item.get("right_source_record_key")))
            for item in pair_quarantine
            if item.get("reason") == "conflicting_official_identifiers"
        }
        for item in pair_quarantine:
            quarantined.append(
                _quarantine_candidate(
                    item.pop("_left_record"),
                    left_profile,
                    item.pop("_right_record"),
                    right_profile,
                    reason=item["reason"],
                    method="exact_official_identifier",
                    provenance=provenance,
                )
            )
        exact_keys = set()
        for left_record, right_record, identifiers in pairs:
            exact_keys.add((_source_key(left_record), _source_key(right_record)))
            if _suppressed(left_record) or _suppressed(right_record):
                quarantined.append(_quarantine_candidate(left_record, left_profile, right_record, right_profile, reason="suppressed_or_restricted", method="exact_official_identifier", provenance=provenance))
                continue
            candidate = _candidate(
                left_record,
                left_profile,
                right_record,
                right_profile,
                method="exact_official_identifier",
                confidence=1.0 if len(identifiers) > 1 else 0.9,
                matched_identifiers=identifiers,
                matched_fields=None,
                provenance=provenance,
            )
            (quarantined if candidate["assertion_status"] == "quarantined" else candidates).append(candidate)

        alternate, alternate_quarantine = _alternate_pairs(left, right)
        for item in alternate_quarantine:
            quarantined.append(
                _quarantine_candidate(
                    item.pop("_left_record"),
                    left_profile,
                    item.pop("_right_record"),
                    right_profile,
                    reason=item["reason"],
                    method="alternate_name_address_exact",
                    provenance=provenance,
                    matched_fields=item.get("matched_fields"),
                )
            )
        for left_record, right_record, fields in alternate:
            key = (_source_key(left_record), _source_key(right_record))
            if key in exact_keys or key in conflicting_pairs:
                continue
            reason = "suppressed_or_restricted" if _suppressed(left_record) or _suppressed(right_record) else None
            candidate = (
                _quarantine_candidate(left_record, left_profile, right_record, right_profile, reason=reason, method="alternate_name_address_exact", provenance=provenance, matched_fields=fields)
                if reason
                else _candidate(left_record, left_profile, right_record, right_profile, method="alternate_name_address_exact", confidence=0.45, matched_identifiers=None, matched_fields=fields, provenance=provenance)
            )
            (quarantined if candidate["assertion_status"] == "quarantined" else candidates).append(candidate)

        # A record with neither an official key nor a complete bounded
        # alternate key must remain visible to review, but cannot become an
        # identity edge.
        for left_record in left:
            if not _identifiers(left_record, left_profile):
                for right_record in right:
                    if not _identifiers(right_record, right_profile) and _source_key(left_record) != _source_key(right_record):
                        if not _name_address(left_record)[0] or not _name_address(left_record)[1] or not _name_address(right_record)[0] or not _name_address(right_record)[1]:
                            quarantined.append(
                                _quarantine_candidate(
                                    left_record,
                                    left_profile,
                                    right_record,
                                    right_profile,
                                    reason="missing_official_identifier",
                                    provenance=provenance,
                                )
                            )

    for item in quarantined:
        item.pop("_left_record", None)
        item.pop("_right_record", None)
        item.setdefault("review_state", "review_required")
        item.setdefault("assertion_status", "quarantined")
        item.setdefault("publication", dict(PUBLICATION))
        item["test_only"] = True
    candidates.sort(key=lambda item: item["candidate_id"])
    quarantined.sort(key=lambda item: (_text(item.get("left_source_record_key")) or _text(item.get("left", {}).get("source_record_key")) or "", _text(item.get("right_source_record_key")) or _text(item.get("right", {}).get("source_record_key")) or "", _text(item.get("reason")) or _text(item.get("quarantine_reason")) or ""))
    source_hashes = {}
    for value in provenance.values():
        if isinstance(value, Mapping):
            digest = _text(value.get("artifact_sha256") or value.get("sha256"))
            if digest:
                source_hashes[digest] = digest
    manifest = {
        "schema_version": CONTRACT_VERSION,
        "candidate_count": len(candidates),
        "quarantined_count": len(quarantined),
        "candidate_relationship_types": dict(sorted(Counter(item["relationship_type"] for item in candidates).items())),
        "match_methods": dict(sorted(Counter(item["match_method"] for item in candidates).items())),
        "source_artifact_sha256": sorted(source_hashes),
        "storage_state": "private",
        "privacy_status": "pending",
        "review_state": "review_required",
        "publication_status": "not_eligible",
        "release_id": None,
        "auto_merge": False,
        "test_only": True,
    }
    return {"schema_version": CONTRACT_VERSION, "entities": nodes, "candidates": candidates, "quarantined": quarantined, "manifest": manifest}


def write_current_identity_graph(run_dir: str | Path, graph: Mapping[str, Any]) -> dict[str, Any]:
    """Atomically write the row-private candidate handoff and manifest."""
    root = Path(run_dir)
    source_manifest = graph.get("manifest")
    if not isinstance(source_manifest, Mapping) or any(
        (
            source_manifest.get("storage_state") != "private",
            source_manifest.get("publication_status") != "not_eligible",
            source_manifest.get("test_only") is not True,
            source_manifest.get("auto_merge") is not False,
        )
    ):
        raise ValueError("current identity graph is not a blocked private test-only candidate")
    candidates = list(graph.get("candidates", ()))
    entities = list(graph.get("entities", ()))
    quarantined = list(graph.get("quarantined", ()))
    for row in (*candidates, *entities, *quarantined):
        publication = row.get("publication")
        if row.get("test_only") is not True or not isinstance(publication, Mapping) or publication.get("publication_status") != "not_eligible":
            raise ValueError("current identity row is not a blocked private test-only candidate")
    _, candidate_sha, _ = atomic_jsonl(root / "candidate" / "identity-links.jsonl", candidates)
    _, entity_sha, _ = atomic_jsonl(root / "candidate" / "entities.jsonl", entities)
    _, quarantine_sha, _ = atomic_jsonl(root / "quarantined" / "identity-links.jsonl", quarantined)
    manifest = dict(graph["manifest"])
    manifest.update({
        "candidate_sha256": candidate_sha,
        "entity_sha256": entity_sha,
        "quarantine_sha256": quarantine_sha,
        "candidate_rows": len(candidates),
        "entity_rows": len(entities),
        "quarantine_rows": len(quarantined),
        "idempotency_key": hashlib.sha256((candidate_sha + entity_sha + quarantine_sha).encode()).hexdigest(),
    })
    atomic_json(root / "identity-graph-manifest.json", manifest)
    return manifest
