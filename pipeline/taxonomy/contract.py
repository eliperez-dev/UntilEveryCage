"""Shared, versioned activity taxonomy contract.

This module deliberately contains vocabulary and deterministic normalization only.
Source adapters own evidence extraction and must not infer unknown source values.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Iterable


TAXONOMY_VERSION = "uec-taxonomy-v1"

PRIMARY_KEYS = (
    "animal_keeping_and_production",
    "slaughter",
    "processing_and_preparation",
    "research_and_animal_use",
    "other_regulated_premises",
    "unclassified",
)
MAPPING_METHODS = ("direct", "derived", "candidate")
MAPPING_STATUSES = (
    "mapped",
    "partial",
    "unmapped",
    "unclassified",
    "conflicting",
    "ambiguous",
)
DISPLAY_PRECEDENCE = (
    "slaughter",
    "research_and_animal_use",
    "animal_keeping_and_production",
    "processing_and_preparation",
    "other_regulated_premises",
    "unclassified",
)
_CONFIRMED_STATUSES = frozenset(("mapped", "partial"))
_UNRESOLVED_STATUSES = frozenset(("unmapped", "unclassified", "conflicting", "ambiguous"))


class TaxonomyContractError(ValueError):
    """Raised when a taxonomy or crosswalk payload violates the frozen contract."""


@dataclass(frozen=True)
class TaxonomyAssignment:
    primary_key: str
    method: str
    status: str
    observation_id: str
    source_record_id: str
    artifact_id: str
    crosswalk_version: str
    ruleset_version: str
    taxonomy_version: str = TAXONOMY_VERSION
    leaf_key: str | None = None
    leaf_label: str | None = None
    source_code_reference: str | None = None
    source_label_reference: str | None = None
    source_code: str | None = None
    source_label: str | None = None

    def __post_init__(self) -> None:
        if self.primary_key not in PRIMARY_KEYS:
            raise TaxonomyContractError(f"unknown primary taxonomy key: {self.primary_key}")
        if self.method not in MAPPING_METHODS:
            raise TaxonomyContractError(f"unknown mapping method: {self.method}")
        if self.status not in MAPPING_STATUSES:
            raise TaxonomyContractError(f"unknown mapping status: {self.status}")
        for field_name in ("observation_id", "source_record_id", "artifact_id", "taxonomy_version", "crosswalk_version", "ruleset_version"):
            if not getattr(self, field_name).strip():
                raise TaxonomyContractError(f"{field_name} is required")
        if self.leaf_label is not None and self.leaf_key is None:
            raise TaxonomyContractError("leaf_label requires leaf_key")
        if self.primary_key == "unclassified" and self.leaf_key is not None:
            raise TaxonomyContractError("unclassified assignments cannot claim a leaf activity")
        if self.primary_key == "unclassified" and self.status in _CONFIRMED_STATUSES:
            raise TaxonomyContractError("unclassified cannot be reported as a confirmed activity")
        if self.status in _UNRESOLVED_STATUSES and self.primary_key != "unclassified":
            raise TaxonomyContractError("unresolved assignments must use the unclassified primary key")
        if self.method == "candidate" and (self.primary_key != "unclassified" or self.status != "ambiguous"):
            raise TaxonomyContractError("candidate assignments must remain unclassified and ambiguous")

    def ordering_key(self) -> tuple[str, ...]:
        """Stable sort key; source values are compared but never rewritten."""
        return (
            self.primary_key,
            self.leaf_key or "",
            self.leaf_label or "",
            self.source_code_reference or "",
            self.source_label_reference or "",
            self.source_code or "",
            self.source_label or "",
            self.method,
            self.status,
        )


def canonical_assignments(assignments: Iterable[TaxonomyAssignment]) -> tuple[TaxonomyAssignment, ...]:
    """Validate one observation's assignment set and return canonical order.

    Repeated rows are rejected instead of silently collapsed. Re-running an
    identical set is idempotent at the database assignment-set key, while a
    duplicate within that set indicates malformed mapper output.
    """
    rows = tuple(assignments)
    if not rows:
        raise TaxonomyContractError("an assignment set must contain at least one assignment")
    lineage = {
        (row.observation_id, row.source_record_id, row.artifact_id,
         row.taxonomy_version, row.crosswalk_version, row.ruleset_version)
        for row in rows
    }
    if len(lineage) != 1:
        raise TaxonomyContractError("all assignments in a set must share observation, artifact, and version lineage")
    keys = [row.ordering_key() for row in rows]
    if len(set(keys)) != len(keys):
        raise TaxonomyContractError("duplicate taxonomy assignment")
    return tuple(sorted(rows, key=TaxonomyAssignment.ordering_key))


def assignment_set_key(assignments: Iterable[TaxonomyAssignment]) -> tuple[str, ...]:
    """Return the immutable database idempotency key for a projected set."""
    rows = canonical_assignments(assignments)
    first = rows[0]
    return (first.observation_id, first.taxonomy_version, first.crosswalk_version, first.ruleset_version)


def choose_display_category(assignments: Iterable[TaxonomyAssignment]) -> str:
    """Choose one compatibility category without discarding multi-activity rows."""
    rows = canonical_assignments(assignments)
    confirmed = {
        row.primary_key
        for row in rows
        if row.status in _CONFIRMED_STATUSES and row.method in ("direct", "derived")
    }
    return next((key for key in DISPLAY_PRECEDENCE if key in confirmed), "unclassified")


def primary_categories(assignments: Iterable[TaxonomyAssignment]) -> tuple[str, ...]:
    """Return every represented broad category in stable lexical order."""
    rows = canonical_assignments(assignments)
    keys = {
        row.primary_key
        for row in rows
        if row.primary_key == "unclassified"
        or (row.status in _CONFIRMED_STATUSES and row.method in ("direct", "derived"))
    }
    if not keys:
        keys.add("unclassified")
    return tuple(sorted(keys))


def validate_crosswalk(document: object) -> dict:
    """Check required crosswalk metadata and vocabulary without guessing rules."""
    if not isinstance(document, dict):
        raise TaxonomyContractError("crosswalk must be a JSON object")
    required = ("source_id", "taxonomy_version", "crosswalk_version", "ruleset_version", "rules")
    missing = [key for key in required if key not in document]
    if missing:
        raise TaxonomyContractError(f"crosswalk missing required fields: {', '.join(missing)}")
    if not all(isinstance(document[key], str) and document[key].strip() for key in required[:4]):
        raise TaxonomyContractError("crosswalk source and version fields must be non-empty strings")
    if document["taxonomy_version"] != TAXONOMY_VERSION:
        raise TaxonomyContractError("unsupported taxonomy version")
    if not isinstance(document["rules"], list):
        raise TaxonomyContractError("crosswalk rules must be an array")
    for index, rule in enumerate(document["rules"]):
        if not isinstance(rule, dict) or rule.get("method") not in MAPPING_METHODS:
            raise TaxonomyContractError(f"crosswalk rule {index} has an invalid method")
        if rule.get("status") not in MAPPING_STATUSES:
            raise TaxonomyContractError(f"crosswalk rule {index} has an invalid status")
        source_codes = rule.get("source_codes", [])
        source_labels = rule.get("source_labels", [])
        source_fields = rule.get("source_fields", [])
        if not isinstance(source_codes, list) or not isinstance(source_labels, list) or not isinstance(source_fields, list):
            raise TaxonomyContractError(f"crosswalk rule {index} selectors must be arrays")
        if any(not isinstance(value, str) or not value for value in (*source_codes, *source_labels, *source_fields)):
            raise TaxonomyContractError(f"crosswalk rule {index} selectors must be non-empty source strings")
        primaries = rule.get("primary_keys", [])
        if not isinstance(primaries, list) or not primaries or any(key not in PRIMARY_KEYS for key in primaries):
            raise TaxonomyContractError(f"crosswalk rule {index} has an invalid primary key")
        if rule["status"] in _UNRESOLVED_STATUSES and any(key != "unclassified" for key in primaries):
            raise TaxonomyContractError(f"crosswalk rule {index} guesses an unresolved classification")
        if "unclassified" in primaries and rule["status"] in _CONFIRMED_STATUSES:
            raise TaxonomyContractError(f"crosswalk rule {index} reports unclassified as a confirmed activity")
        if not source_codes and not source_labels and not source_fields:
            raise TaxonomyContractError(f"crosswalk rule {index} requires a source code, label, or field reference")
        if rule.get("leaf_key") is not None and (len(primaries) != 1 or primaries[0] == "unclassified"):
            raise TaxonomyContractError(f"crosswalk rule {index} leaf activity requires one classified primary")
    return document


def crosswalk_sha256(document: object) -> str:
    """Hash the validated crosswalk as canonical UTF-8 JSON."""
    validated = validate_crosswalk(document)
    payload = json.dumps(validated, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
