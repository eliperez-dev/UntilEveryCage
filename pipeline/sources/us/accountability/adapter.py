"""Deterministic, private graph-candidate contract for the US pilot.

The input is a reviewed link ledger, not a name-matching job. Each row is one
asserted relationship with two typed source-native endpoints and independent
evidence provenance. The adapter emits no database writes and no public
release.
"""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any

from pipeline.contracts.adapter_contract import SourceArtifact
from pipeline.contracts.source_lifecycle import atomic_json, atomic_jsonl, private_manifest

ROOT = Path(__file__).parent
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))

ENTITY_TYPES = frozenset({
    "facility", "establishment_approval", "operator", "legal_entity", "parent",
    "brand", "inspection", "violation", "enforcement", "laboratory",
    "aggregate_observation",
})
RELATIONSHIPS: dict[str, tuple[str, frozenset[str]]] = {
    "establishment_approval_for": ("establishment_approval", frozenset({"facility"})),
    "operates": ("operator", frozenset({"facility"})),
    "operator_is_legal_entity": ("operator", frozenset({"legal_entity"})),
    "parent_of": ("legal_entity", frozenset({"legal_entity", "parent"})),
    "brand_of": ("brand", frozenset({"legal_entity"})),
    "inspection_observes": ("inspection", frozenset({"facility", "operator"})),
    "violation_observed_in": ("violation", frozenset({"inspection"})),
    "enforcement_for": ("enforcement", frozenset({"violation"})),
    "laboratory_supports": ("laboratory", frozenset({"inspection", "aggregate_observation"})),
    "aggregate_describes": ("aggregate_observation", frozenset({"facility", "operator"})),
    "regulatory_authority_for": ("legal_entity", frozenset({"facility", "operator", "inspection"})),
}
CONFIDENCE = frozenset({"high", "medium", "low"})
REVIEW_STATES = frozenset({"evidence_verified", "review_required", "quarantined"})
MATCH_METHODS = frozenset({"exact_source_id", "explicit_reviewed_link", "temporal_source_link"})
REJECTED_MATCH_METHODS = frozenset({"name_only", "address_only", "phone_only", "fuzzy_name", "geocoder"})
SUPPRESSION_STATES = frozenset({"eligible", "suppressed", "restricted", "unknown"})
REQUIRED_HEADERS = (
    "subject_type", "subject_source_id", "subject_source_native_id", "subject_name",
    "object_type", "object_source_id", "object_source_native_id", "object_name",
    "relationship_type", "evidence_source_id", "evidence_source_native_id",
    "observation_date", "retrieved_at_utc", "valid_from", "valid_to", "confidence",
    "review_state", "match_method", "evidence_url", "evidence_excerpt", "suppression_state",
)
REFERENCE_DATE = date(2026, 9, 15)


class AccountabilityContractError(ValueError):
    """The link ledger does not satisfy the candidate contract."""


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _iso_date(value: str | None, field: str, *, required: bool = False) -> date | None:
    text = _clean(value)
    if not text:
        if required:
            raise AccountabilityContractError(f"missing {field}")
        return None
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise AccountabilityContractError(f"{field} must be ISO-8601 date") from exc


def _iso_datetime(value: str | None, field: str) -> str:
    text = _clean(value)
    if not text:
        raise AccountabilityContractError(f"missing {field}")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AccountabilityContractError(f"{field} must be ISO-8601 datetime") from exc
    if parsed.tzinfo is None:
        raise AccountabilityContractError(f"{field} must include a timezone")
    return text


def _entity_ref(entity_type: str, source_id: str, native_id: str) -> dict[str, str]:
    return {"entity_type": entity_type, "source_id": source_id, "source_native_id": native_id}


def _entity_key(ref: dict[str, str]) -> tuple[str, str, str]:
    return ref["entity_type"], ref["source_id"], ref["source_native_id"]


def _stable_entity_id(ref: dict[str, str]) -> str:
    value = "|".join((ref["entity_type"], ref["source_id"], ref["source_native_id"]))
    return "candidate-entity-" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


def _entity(ref: dict[str, str], name: str, *, observed_at: str, evidence: dict[str, str]) -> dict[str, Any]:
    return {
        "entity_id": _stable_entity_id(ref),
        **ref,
        "display_name": name,
        "observation_date": observed_at,
        "evidence": evidence,
        "privacy_gate": "pending-review",
        "publication_gate": "blocked",
        "test_only": True,
    }


def _relationship(row: dict[str, str], *, observed_at: str, retrieved_at: str, source_row: int) -> tuple[dict[str, Any], tuple[dict[str, Any], dict[str, Any]]]:
    subject = _entity_ref(row["subject_type"], row["subject_source_id"], row["subject_source_native_id"])
    object_ = _entity_ref(row["object_type"], row["object_source_id"], row["object_source_native_id"])
    evidence = {
        "source_id": row["evidence_source_id"],
        "source_native_id": row["evidence_source_native_id"],
        "url": row["evidence_url"],
        "excerpt": row["evidence_excerpt"],
    }
    identity = {"subject": subject, "object": object_, "relationship_type": row["relationship_type"], "source_native_id": row["evidence_source_native_id"], "observation_date": observed_at}
    relation_id = "candidate-relationship-" + hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:24]
    relation = {
        "relationship_id": relation_id,
        "relationship_type": row["relationship_type"],
        "subject": subject,
        "object": object_,
        "source_id": row["evidence_source_id"],
        "source_native_ids": {
            "subject": subject["source_native_id"],
            "object": object_["source_native_id"],
            "evidence": row["evidence_source_native_id"],
        },
        "observation_date": observed_at,
        "retrieved_at_utc": retrieved_at,
        "valid_from": row.get("valid_from") or None,
        "valid_to": row.get("valid_to") or None,
        "confidence": row["confidence"],
        "review_state": row["review_state"],
        "match_method": row["match_method"],
        "evidence": evidence,
        "source_row": source_row,
        "publication_gate": "blocked",
        "test_only": True,
    }
    return relation, (
        _entity(subject, row["subject_name"], observed_at=observed_at, evidence=evidence),
        _entity(object_, row["object_name"], observed_at=observed_at, evidence=evidence),
    )


class UsAccountabilityAdapter:
    source_id = CONFIG["source_id"]
    adapter_version = CONFIG["adapter_version"]
    schema_version = CONFIG["contract_version"]

    def __init__(self, *, stale_after_days: int = CONFIG["stale_after_days"], reference_date: date = REFERENCE_DATE) -> None:
        if stale_after_days < 0:
            raise ValueError("stale_after_days must be non-negative")
        self.stale_after_days = stale_after_days
        self.reference_date = reference_date

    def parse_bytes(self, content: bytes) -> dict[str, Any]:
        digest = hashlib.sha256(content).hexdigest()
        try:
            reader = csv.DictReader(content.decode("utf-8-sig").splitlines(), strict=True)
            headers = tuple(reader.fieldnames or ())
            rows = list(reader)
        except (UnicodeDecodeError, csv.Error) as exc:
            raise AccountabilityContractError("malformed or unsupported UTF-8 CSV") from exc
        if headers != REQUIRED_HEADERS:
            missing = [header for header in REQUIRED_HEADERS if header not in headers]
            extra = [header for header in headers if header not in REQUIRED_HEADERS]
            raise AccountabilityContractError(f"unsupported link-ledger schema; missing={missing}, extra={extra}")
        if len(headers) != len(set(headers)) or any(None in row for row in rows):
            raise AccountabilityContractError("schema drift: duplicate or extra link-ledger columns")

        accepted: list[dict[str, Any]] = []
        quarantined: list[dict[str, Any]] = []
        entities: dict[tuple[str, str, str], dict[str, Any]] = {}
        identifiers: dict[tuple[str, str], tuple[str, str]] = {}
        relationship_rows: list[tuple[dict[str, Any], dict[str, str], int]] = []

        for line, row in enumerate(rows, 2):
            reasons: list[str] = []
            try:
                required = ("subject_type", "subject_source_id", "subject_source_native_id", "subject_name", "object_type", "object_source_id", "object_source_native_id", "object_name", "relationship_type", "evidence_source_id", "evidence_source_native_id", "confidence", "review_state", "match_method", "evidence_url", "evidence_excerpt", "suppression_state")
                reasons.extend(f"missing_{field}" for field in required if not _clean(row.get(field)))
                if row.get("subject_type") not in ENTITY_TYPES or row.get("object_type") not in ENTITY_TYPES:
                    reasons.append("unknown_entity_type")
                relation_spec = RELATIONSHIPS.get(row.get("relationship_type", ""))
                if relation_spec is None:
                    reasons.append("unknown_relationship_type")
                elif row["subject_type"] != relation_spec[0] or row["object_type"] not in relation_spec[1]:
                    reasons.append("relationship_endpoint_type_mismatch")
                if row.get("confidence") not in CONFIDENCE:
                    reasons.append("unknown_confidence")
                if row.get("review_state") not in REVIEW_STATES or row.get("review_state") == "quarantined":
                    reasons.append("invalid_review_state")
                if row.get("match_method") in REJECTED_MATCH_METHODS:
                    reasons.append("non_defensible_match_method")
                elif row.get("match_method") not in MATCH_METHODS:
                    reasons.append("unknown_match_method")
                if row.get("suppression_state") not in SUPPRESSION_STATES:
                    reasons.append("unknown_suppression_state")
                elif row["suppression_state"] != "eligible":
                    reasons.append("suppressed_or_restricted")
                observed = _iso_date(row.get("observation_date"), "observation_date", required=True)
                retrieved = _iso_datetime(row.get("retrieved_at_utc"), "retrieved_at_utc")
                start = _iso_date(row.get("valid_from"), "valid_from")
                end = _iso_date(row.get("valid_to"), "valid_to")
                if start and end and end < start:
                    reasons.append("valid_to_precedes_valid_from")
                if observed and (self.reference_date - observed).days > self.stale_after_days:
                    reasons.append("stale_evidence")
                if observed and datetime.fromisoformat(retrieved.replace("Z", "+00:00")).date() < observed:
                    reasons.append("retrieval_precedes_observation")
                row_identities: list[tuple[tuple[str, str], tuple[str, str]]] = []
                for side in ("subject", "object"):
                    source_id, native_id = row[f"{side}_source_id"], row[f"{side}_source_native_id"]
                    identity_key = (source_id, native_id)
                    identity_value = (row[f"{side}_type"], row[f"{side}_name"])
                    prior = identifiers.get(identity_key)
                    if prior and prior != identity_value:
                        reasons.append("conflicting_source_identifier")
                    row_identities.append((identity_key, identity_value))
                if row.get("match_method") == "explicit_reviewed_link":
                    same_name = [key for key, value in identifiers.items() if value[1] == row.get("object_name") and key[0] == row.get("object_source_id")]
                    if len(same_name) > 1 and (row["object_source_id"], row["object_source_native_id"]) not in same_name:
                        reasons.append("ambiguous_duplicate_name")
                if not reasons:
                    for identity_key, identity_value in row_identities:
                        identifiers[identity_key] = identity_value
            except AccountabilityContractError as exc:
                reasons.append(str(exc).replace(" ", "_"))
                observed = None
                retrieved = None

            if reasons:
                quarantined.append({"source_row": line, "reasons": tuple(dict.fromkeys(reasons)), "source_values": dict(row)})
                continue
            relation, node_rows = _relationship(row, observed_at=observed.isoformat(), retrieved_at=retrieved, source_row=line)  # type: ignore[union-attr]
            entities[_entity_key(relation["subject"])] = node_rows[0]
            entities[_entity_key(relation["object"])] = node_rows[1]
            relationship_rows.append((relation, row, line))

        # Ownership is history: non-overlapping periods survive. Contradictory
        # operators for the same facility and overlapping validity quarantine.
        ownership: dict[tuple[str, str], list[tuple[dict[str, Any], dict[str, str], int]]] = {}
        for relation, row, line in relationship_rows:
            if relation["relationship_type"] == "operates":
                ownership.setdefault((relation["object"]["source_id"], relation["object"]["source_native_id"]), []).append((relation, row, line))
        conflicting_ids: set[str] = set()
        for observations in ownership.values():
            for index, (left, _, _) in enumerate(observations):
                left_start = date.fromisoformat(left["valid_from"] or left["observation_date"])
                left_end = date.fromisoformat(left["valid_to"]) if left["valid_to"] else date.max
                for right, _, _ in observations[index + 1:]:
                    right_start = date.fromisoformat(right["valid_from"] or right["observation_date"])
                    right_end = date.fromisoformat(right["valid_to"]) if right["valid_to"] else date.max
                    if left["subject"] != right["subject"] and max(left_start, right_start) <= min(left_end, right_end):
                        conflicting_ids.update((left["relationship_id"], right["relationship_id"]))
        if conflicting_ids:
            retained: list[tuple[dict[str, Any], dict[str, str], int]] = []
            for relation, row, line in relationship_rows:
                if relation["relationship_id"] in conflicting_ids:
                    quarantined.append({"source_row": line, "reasons": ("overlapping_ownership_conflict",), "source_values": dict(row)})
                else:
                    retained.append((relation, row, line))
            relationship_rows = retained
            used = {_entity_key(relation["subject"]) for relation, _, _ in retained} | {_entity_key(relation["object"]) for relation, _, _ in retained}
            entities = {key: entity for key, entity in entities.items() if key in used}

        accepted = sorted((relation for relation, _, _ in relationship_rows), key=lambda relation: relation["relationship_id"])
        entity_rows = sorted(entities.values(), key=lambda entity: entity["entity_id"])
        quarantined.sort(key=lambda item: int(item["source_row"]))
        return {
            "accepted": accepted,
            "entities": entity_rows,
            "quarantined": quarantined,
            "source_sha256": digest,
            "schema_fingerprint": hashlib.sha256(json.dumps(headers, separators=(",", ":")).encode()).hexdigest(),
            "headers": headers,
            "input_rows": len(rows),
        }

    def run(self, raw_path: str | Path, run_dir: str | Path, artifact: SourceArtifact) -> dict[str, Any]:
        raw = Path(raw_path).read_bytes()
        if artifact.sha256 != hashlib.sha256(raw).hexdigest() or artifact.byte_size != len(raw):
            raise ValueError("artifact provenance mismatch")
        result = self.parse_bytes(raw)
        root = Path(run_dir)
        _, relationships_sha, _ = atomic_jsonl(root / "candidate" / "relationships.jsonl", result["accepted"])
        _, entities_sha, _ = atomic_jsonl(root / "candidate" / "entities.jsonl", result["entities"])
        atomic_jsonl(root / "quarantined" / "relationships.jsonl", result["quarantined"])
        reasons = Counter(reason for item in result["quarantined"] for reason in item["reasons"])
        manifest = private_manifest(
            source_id=self.source_id, adapter_version=self.adapter_version,
            schema_version=self.schema_version, artifact=artifact,
            input_rows=result["input_rows"], normalized_rows=len(result["accepted"]),
            quarantined_rows=len(result["quarantined"]), normalized_sha256=relationships_sha,
            parsed_sha256=entities_sha, anomaly_counts=dict(sorted(reasons.items())),
        )
        manifest.update({
            "candidate_contract": "us-accountability-graph-candidate-v1",
            "schema_fingerprint": result["schema_fingerprint"],
            "entity_rows": len(result["entities"]),
            "relationship_rows": len(result["accepted"]),
            "quarantined_relationship_rows": len(result["quarantined"]),
            "entity_types": dict(sorted(Counter(entity["entity_type"] for entity in result["entities"]).items())),
            "relationship_types": dict(sorted(Counter(relation["relationship_type"] for relation in result["accepted"]).items())),
            "candidate_relationships_sha256": relationships_sha,
            "candidate_entities_sha256": entities_sha,
            "test_only": True,
            "graph_migration": False,
            "geocoding": "disabled",
            "publication_gate": "blocked",
            "coverage": "Synthetic/sanitized contract fixture for FSIS, APHIS, and deferred legal-entity evidence links; not a national coverage claim",
        })
        atomic_json(root / "manifest.json", manifest)
        return manifest
