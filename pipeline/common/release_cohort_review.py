"""Bounded, release-scoped cohort review contracts and set-based worker scope."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any


HEX64 = re.compile(r"^[0-9a-f]{64}$")
DISPLAY_CATEGORIES = {
    "animal_keeping_and_production", "slaughter", "processing_and_preparation",
    "research_and_animal_use", "other_regulated_premises", "unclassified",
}
TAXONOMY_VERSION = "uec-taxonomy-v1"


class CohortReviewError(ValueError):
    """The review document or current candidate cohort fails closed."""


def canonical_sha256(value: Any) -> str:
    payload = (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _text(value: Any, field: str, *, maximum: int = 2000) -> str:
    if (not isinstance(value, str) or not value.strip() or len(value) > maximum
            or any(ord(character) < 32 for character in value)):
        raise CohortReviewError(f"{field} must be a non-empty safe string")
    return value.strip()


def _reference(value: Any, field: str) -> str:
    text = _text(value, field, maximum=500)
    if not re.fullmatch(r"[A-Za-z0-9:/._#-]+", text):
        raise CohortReviewError(f"{field} must be a safe reference token or URL without query data")
    return text


def _timestamp(value: Any, field: str) -> str:
    text = _text(value, field, maximum=64)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        raise CohortReviewError(f"{field} must be an ISO timestamp") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CohortReviewError(f"{field} must include a timezone")
    return text


def validate_document(document: Any) -> dict[str, Any]:
    """Validate the operator-authored allowlisted document, never infer decisions."""
    if not isinstance(document, dict) or document.get("schema_version") != "uec-release-cohort-review-v1":
        raise CohortReviewError("review document schema is unsupported")
    allowed_top = {"schema_version", "release_id", "profile", "ruleset_version", "freeze_sha256",
                   "inventory_sha256", "member_sha256", "member_count", "reviewer", "review_method",
                   "review_evidence_reference", "source_artifact_scopes"}
    if set(document) != allowed_top:
        raise CohortReviewError("review document contains fields outside the safe allowlist")
    required_hashes = ("freeze_sha256", "inventory_sha256", "member_sha256")
    for field in required_hashes:
        if not isinstance(document.get(field), str) or not HEX64.fullmatch(document[field]):
            raise CohortReviewError(f"{field} must be a lowercase SHA-256 digest")
    count = document.get("member_count")
    if not isinstance(count, int) or isinstance(count, bool) or count < 1:
        raise CohortReviewError("member_count must be a positive integer")
    _text(document.get("release_id"), "release_id", maximum=200)
    if document.get("profile") not in {"official", "secondary", "community"}:
        raise CohortReviewError("profile is unsupported")
    _text(document.get("ruleset_version"), "ruleset_version", maximum=200)
    reviewer = document.get("reviewer")
    if not isinstance(reviewer, dict):
        raise CohortReviewError("reviewer must be an object")
    _text(reviewer.get("actor"), "reviewer.actor", maximum=300)
    _text(reviewer.get("role"), "reviewer.role", maximum=100)
    if set(reviewer) != {"actor", "role", "reviewed_at"}:
        raise CohortReviewError("reviewer contains fields outside the safe allowlist")
    _timestamp(reviewer.get("reviewed_at"), "reviewer.reviewed_at")
    for field in ("review_method", "review_evidence_reference"):
        _text(document.get(field), field)
    _reference(document.get("review_evidence_reference"), "review_evidence_reference")
    scopes = document.get("source_artifact_scopes")
    if not isinstance(scopes, list) or not scopes:
        raise CohortReviewError("source_artifact_scopes must be a non-empty list")
    seen: set[tuple[str, str]] = set()
    scope_fields = {"source_id", "artifact_id", "artifact_sha256", "factual_review_status",
                    "privacy_screening_status", "privacy_method", "privacy_evidence_reference",
                    "maintainer_approval", "publication_eligible", "project_approval_method",
                    "project_approval_evidence_reference", "redistribution_status", "rights_actor",
                    "rights_reference", "rights_decided_at", "classification_interpretation_status",
                    "classification_method", "classification_evidence_reference",
                    "geometry_interpretation_status", "geometry_method", "geometry_evidence_reference",
                    "taxonomy_version", "crosswalk_version", "classification_ruleset_version",
                    "excluded_display_categories", "exclusion_reason_category", "exclusion_policy_reference"}
    for scope in scopes:
        if not isinstance(scope, dict):
            raise CohortReviewError("source artifact scope must be an object")
        if set(scope) - scope_fields:
            raise CohortReviewError("source artifact scope contains fields outside the safe allowlist")
        source_id = _text(scope.get("source_id"), "scope.source_id", maximum=200)
        artifact_id = _text(scope.get("artifact_id"), "scope.artifact_id", maximum=64)
        key = (source_id, artifact_id)
        if key in seen:
            raise CohortReviewError("source/artifact scopes must be unique")
        seen.add(key)
        digest = scope.get("artifact_sha256")
        if not isinstance(digest, str) or not HEX64.fullmatch(digest):
            raise CohortReviewError("scope.artifact_sha256 must be a lowercase SHA-256 digest")
        if scope.get("factual_review_status") not in {"unreviewed", "reviewed", "rejected"}:
            raise CohortReviewError("factual_review_status is unsupported")
        if scope.get("privacy_screening_status") not in {"pending", "passed", "failed"}:
            raise CohortReviewError("privacy_screening_status is unsupported")
        if scope.get("maintainer_approval") not in {"pending", "approved", "denied"}:
            raise CohortReviewError("maintainer_approval is unsupported")
        if not isinstance(scope.get("publication_eligible"), bool):
            raise CohortReviewError("publication_eligible must be an explicit boolean")
        if scope.get("redistribution_status") not in {"cleared", "unknown", "restricted"}:
            raise CohortReviewError("redistribution_status is unsupported")
        if scope.get("classification_interpretation_status") not in {"approved", "unreviewed", "rejected"}:
            raise CohortReviewError("classification_interpretation_status is unsupported")
        if scope.get("geometry_interpretation_status") not in {"approved", "unreviewed", "rejected"}:
            raise CohortReviewError("geometry_interpretation_status is unsupported")
        if scope.get("taxonomy_version") != TAXONOMY_VERSION:
            raise CohortReviewError("taxonomy_version must match the confirmed taxonomy")
        _text(scope.get("crosswalk_version"), "scope.crosswalk_version", maximum=200)
        _text(scope.get("classification_ruleset_version"), "scope.classification_ruleset_version", maximum=200)
        _text(scope.get("classification_method"), "scope.classification_method")
        _text(scope.get("classification_evidence_reference"), "scope.classification_evidence_reference")
        _text(scope.get("geometry_method"), "scope.geometry_method")
        _text(scope.get("geometry_evidence_reference"), "scope.geometry_evidence_reference")
        for field in ("privacy_method", "privacy_evidence_reference", "project_approval_method",
                      "project_approval_evidence_reference", "rights_actor", "rights_reference"):
            _text(scope.get(field), f"scope.{field}")
        for field in ("privacy_evidence_reference", "project_approval_evidence_reference", "rights_reference",
                      "classification_evidence_reference", "geometry_evidence_reference"):
            _reference(scope.get(field), f"scope.{field}")
        _timestamp(scope.get("rights_decided_at"), "scope.rights_decided_at")
        excluded = scope.get("excluded_display_categories", [])
        if (not isinstance(excluded, list) or any(item not in DISPLAY_CATEGORIES for item in excluded)
                or len(set(excluded)) != len(excluded)):
            raise CohortReviewError("excluded_display_categories must contain unique confirmed taxonomy IDs")
        if excluded:
            _text(scope.get("exclusion_reason_category"), "scope.exclusion_reason_category", maximum=100)
            _reference(scope.get("exclusion_policy_reference"), "scope.exclusion_policy_reference")
    return document


# Join this CTE in one set-based query to obtain the only cohort members whose
# derived geometry interpretation has an explicit scoped approval. Callers
# must supply release_id and only consume rows joined by the observation binding.
APPROVED_GEOMETRY_MEMBERS_CTE = """
WITH approved_geometry_members AS (
    SELECT member.release_id, member.facility_id, member.observation_id,
           observation.source_record_id, record.source_id, record.artifact_id,
           scope.member_sha256, scope.artifact_sha256,
           scope.taxonomy_version, scope.crosswalk_version,
           scope.classification_ruleset_version
    FROM uec.release_members member
    JOIN uec.releases release ON release.release_id=member.release_id
    JOIN uec.observations observation ON observation.observation_id=member.observation_id
    JOIN uec.source_records record ON record.source_record_id=observation.source_record_id
    JOIN uec.release_cohort_review_current scope
      ON scope.release_id=member.release_id
     AND scope.source_id=record.source_id
     AND scope.artifact_id=record.artifact_id
     AND scope.geometry_interpretation_status='approved'
    JOIN uec.raw_artifacts artifact
      ON artifact.artifact_id=record.artifact_id AND artifact.sha256=scope.artifact_sha256
    JOIN uec.observation_taxonomy_assignment_sets assignments
      ON assignments.observation_id=observation.observation_id
     AND assignments.source_record_id=observation.source_record_id
     AND assignments.source_id=record.source_id
     AND assignments.artifact_id=record.artifact_id
     AND assignments.taxonomy_version=scope.taxonomy_version
     AND assignments.crosswalk_version=scope.crosswalk_version
     AND assignments.ruleset_version=scope.classification_ruleset_version
    WHERE member.release_id=%s
      AND release.status IN ('candidate','validated','promoted')
      AND release.test_only IS FALSE
      AND release.profile=scope.profile
      AND release.ruleset_version=scope.ruleset_version
      AND release.summary->>'candidate_only'='true'
      AND release.summary->>'freeze_sha256'=scope.freeze_sha256
      AND release.summary->>'inventory_sha256'=scope.inventory_sha256
      AND NOT EXISTS (
          SELECT 1 FROM uec.observation_taxonomy_assignment_sets newer
          WHERE newer.observation_id=assignments.observation_id
            AND newer.taxonomy_version=assignments.taxonomy_version
            AND (newer.created_at,newer.assignment_set_id)>(assignments.created_at,assignments.assignment_set_id)
      )
)
"""


def geometry_approval_sql(select_sql: str) -> str:
    """Prefix a worker SELECT with the reusable approved-member CTE."""
    if not isinstance(select_sql, str) or not select_sql.lstrip().upper().startswith("SELECT "):
        raise CohortReviewError("geometry query must begin with SELECT")
    return APPROVED_GEOMETRY_MEMBERS_CTE + "\n" + select_sql
