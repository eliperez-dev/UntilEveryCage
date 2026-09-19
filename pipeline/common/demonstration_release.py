"""Validation helpers for the bounded real-data demonstration release lane.

These helpers deliberately accept only opaque identifiers and review metadata.
They never parse or emit source rows, addresses, coordinates, or reviewer
evidence.  The database-facing stages add the corresponding release members
and append-only review events after these documents pass validation.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any


MAX_DEMONSTRATION_RECORDS = 25
SELECTION_VERSION = "uec-demo-selection-v1"
REVIEW_VERSION = "uec-demo-review-v1"


class DemonstrationReleaseError(ValueError):
    """The demonstration release input is incomplete or unsafe."""


def _object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DemonstrationReleaseError(f"{label} is not valid JSON") from exc
    if not isinstance(value, dict):
        raise DemonstrationReleaseError(f"{label} must be a JSON object")
    return value


def _required_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DemonstrationReleaseError(f"{field} must be a non-empty string")
    return value.strip()


def _uuid(value: Any, field: str) -> str:
    raw = _required_string(value, field)
    try:
        return str(uuid.UUID(raw))
    except ValueError as exc:
        raise DemonstrationReleaseError(f"{field} must be a UUID") from exc


def load_selection(path: Path) -> dict[str, Any]:
    selection = _object(path, "selection")
    if selection.get("selection_version") != SELECTION_VERSION:
        raise DemonstrationReleaseError("selection_version is unsupported")
    selection["candidate_release_id"] = _required_string(selection.get("candidate_release_id"), "candidate_release_id")
    selection["source_id"] = _required_string(selection.get("source_id"), "source_id")
    selection["source_artifact_sha256"] = _required_string(selection.get("source_artifact_sha256"), "source_artifact_sha256").lower()
    if len(selection["source_artifact_sha256"]) != 64 or any(c not in "0123456789abcdef" for c in selection["source_artifact_sha256"]):
        raise DemonstrationReleaseError("source_artifact_sha256 must be a lowercase SHA-256 digest")
    record_ids = selection.get("record_ids")
    if not isinstance(record_ids, list) or not record_ids:
        raise DemonstrationReleaseError("record_ids must be a non-empty array")
    normalized = [_uuid(value, "record_ids[]") for value in record_ids]
    if len(normalized) != len(set(normalized)):
        raise DemonstrationReleaseError("record_ids must be unique")
    if len(normalized) > MAX_DEMONSTRATION_RECORDS:
        raise DemonstrationReleaseError(f"selection exceeds the {MAX_DEMONSTRATION_RECORDS}-record demonstration limit")
    selection["record_ids"] = normalized
    selection["selection_reason"] = _required_string(selection.get("selection_reason"), "selection_reason")
    return selection


def load_review(path: Path) -> dict[str, Any]:
    review = _object(path, "review")
    if review.get("review_version") != REVIEW_VERSION:
        raise DemonstrationReleaseError("review_version is unsupported")
    review["release_id"] = _required_string(review.get("release_id"), "release_id")
    review["source_id"] = _required_string(review.get("source_id"), "source_id")
    review["source_artifact_sha256"] = _required_string(review.get("source_artifact_sha256"), "source_artifact_sha256").lower()
    if len(review["source_artifact_sha256"]) != 64 or any(c not in "0123456789abcdef" for c in review["source_artifact_sha256"]):
        raise DemonstrationReleaseError("source_artifact_sha256 must be a lowercase SHA-256 digest")
    if review.get("rights_status") != "cleared":
        raise DemonstrationReleaseError("rights_status must be cleared before a demonstration can be approved")
    review["rights_reference"] = _required_string(review.get("rights_reference"), "rights_reference")
    review["reviewer_role"] = _required_string(review.get("reviewer_role"), "reviewer_role")
    review["reviewed_at"] = _required_string(review.get("reviewed_at"), "reviewed_at")
    decisions = review.get("decisions")
    if not isinstance(decisions, list) or not decisions:
        raise DemonstrationReleaseError("decisions must be a non-empty array")
    normalized_decisions = []
    seen: set[str] = set()
    for decision in decisions:
        if not isinstance(decision, dict):
            raise DemonstrationReleaseError("each decision must be an object")
        record_id = _uuid(decision.get("source_record_id"), "decisions[].source_record_id")
        if record_id in seen:
            raise DemonstrationReleaseError("decisions must contain one entry per source record")
        seen.add(record_id)
        factual = _required_string(decision.get("factual_review_status"), "decisions[].factual_review_status")
        privacy = _required_string(decision.get("privacy_screening_status"), "decisions[].privacy_screening_status")
        approval = _required_string(decision.get("maintainer_approval"), "decisions[].maintainer_approval")
        if factual not in {"reviewed", "rejected"} or privacy not in {"passed", "failed"} or approval not in {"approved", "denied"}:
            raise DemonstrationReleaseError("demonstration decisions must be explicit reviewed/privacy/approval outcomes")
        if decision.get("publication_eligible") is not True:
            raise DemonstrationReleaseError("every demonstration decision must explicitly set publication_eligible=true")
        if (factual, privacy, approval) != ("reviewed", "passed", "approved"):
            raise DemonstrationReleaseError("a blocked decision cannot approve the demonstration release")
        normalized_decisions.append({
            "source_record_id": record_id,
            "factual_review_status": factual,
            "privacy_screening_status": privacy,
            "maintainer_approval": approval,
            "publication_eligible": True,
            "note": _required_string(decision.get("note"), "decisions[].note"),
        })
    review["decisions"] = normalized_decisions
    return review
