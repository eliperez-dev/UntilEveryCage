"""Shared readiness and publication-boundary model for country/source lanes.

Readiness is deliberately separate from factual review and publication.  A
source can be privately validated without being approved, and an approved
record can later be suppressed.  This module is a small, dependency-free
contract that adapters, diagnostics, and review tooling can share.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


READINESS_SCHEMA_VERSION = "country-source-readiness-v1"

READINESS_STATES = frozenset(
    {
        "not-started",
        "reconnaissance",
        "blocked",
        "private-candidate",
        "private-validated",
        "awaiting-owner-review",
        "approved-for-release",
        "published",
        "suppressed",
    }
)
OWNER_REVIEW_STATES = frozenset(
    {"not-requested", "awaiting-owner-review", "approved", "rejected"}
)

_ALLOWED_TRANSITIONS = {
    "not-started": {"not-started", "reconnaissance", "blocked"},
    "reconnaissance": {"reconnaissance", "blocked", "private-candidate"},
    "blocked": {"blocked", "reconnaissance", "private-candidate"},
    "private-candidate": {
        "private-candidate",
        "private-validated",
        "blocked",
        "awaiting-owner-review",
        "suppressed",
    },
    "private-validated": {
        "private-validated",
        "awaiting-owner-review",
        "blocked",
        "suppressed",
    },
    "awaiting-owner-review": {
        "awaiting-owner-review",
        "approved-for-release",
        "blocked",
        "suppressed",
    },
    "approved-for-release": {
        "approved-for-release",
        "published",
        "blocked",
        "suppressed",
    },
    "published": {"published", "suppressed", "blocked"},
    "suppressed": {"suppressed", "private-candidate", "blocked"},
}


class ReadinessError(ValueError):
    """Raised when a readiness object violates the shared boundary."""


@dataclass(frozen=True)
class Readiness:
    """A serializable readiness decision with an explicit owner boundary."""

    state: str
    owner_review: str = "awaiting-owner-review"
    private_candidate: bool = False
    public_release_allowed: bool = False
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        validate_readiness(self.as_mapping())

    def as_mapping(self) -> dict[str, Any]:
        return {
            "schema_version": READINESS_SCHEMA_VERSION,
            "state": self.state,
            "owner_review": self.owner_review,
            "private_candidate": self.private_candidate,
            "public_release_allowed": self.public_release_allowed,
            "reasons": list(self.reasons),
        }


def validate_readiness(value: Mapping[str, Any]) -> None:
    """Validate an externally supplied readiness mapping fail-closed."""
    if value.get("schema_version") != READINESS_SCHEMA_VERSION:
        raise ReadinessError(f"schema_version must be {READINESS_SCHEMA_VERSION}")
    state = value.get("state")
    owner_review = value.get("owner_review")
    if state not in READINESS_STATES:
        raise ReadinessError(f"unknown readiness state: {state!r}")
    if owner_review not in OWNER_REVIEW_STATES:
        raise ReadinessError(f"unknown owner review state: {owner_review!r}")
    for key in ("private_candidate", "public_release_allowed"):
        if not isinstance(value.get(key), bool):
            raise ReadinessError(f"{key} must be boolean")
    reasons = value.get("reasons")
    if not isinstance(reasons, list) or any(not isinstance(item, str) or not item for item in reasons):
        raise ReadinessError("reasons must be a list of non-empty strings")
    if state in {"approved-for-release", "published"}:
        if owner_review != "approved" or value.get("public_release_allowed") is not True:
            raise ReadinessError("release-ready states require approved owner review and public_release_allowed=true")
    else:
        if value.get("public_release_allowed") is not False:
            raise ReadinessError("non-release-ready states must not allow public release")
    if state == "awaiting-owner-review" and owner_review != "awaiting-owner-review":
        raise ReadinessError("awaiting-owner-review must retain the same owner boundary")


def readiness_from_status(status: Mapping[str, Any]) -> Readiness:
    """Derive a conservative readiness state from the source-status vocabulary.

    Existing status files intentionally do not contain approvals.  Therefore a
    privately acquired source becomes ``awaiting-owner-review`` at most; it can
    never be inferred as release-ready from acquisition or runtime health.
    """
    publication = str(status.get("publication_eligibility", "not_assessed"))
    acquisition = str(status.get("acquisition", "not_run"))
    metadata = str(status.get("metadata", "unknown"))
    explicit = status.get("readiness_state")
    owner_review = str(status.get("owner_review", "awaiting-owner-review"))
    if owner_review not in OWNER_REVIEW_STATES:
        owner_review = "awaiting-owner-review"

    if explicit in {"approved-for-release", "published"} and owner_review == "approved":
        state = str(explicit)
        return Readiness(state, owner_review, True, True, ())

    reasons: list[str] = []
    if publication in {"blocked", "not_assessed"}:
        reasons.append(f"publication:{publication}")
    if acquisition in {"blocked", "not_run"}:
        reasons.append(f"acquisition:{acquisition}")
    if metadata == "unknown":
        reasons.append("metadata:unknown")

    if acquisition == "not_run" and metadata in {"verified", "partial"}:
        state = "reconnaissance"
    elif acquisition == "blocked":
        state = "blocked"
    elif acquisition in {"artifact_private_only", "verified"}:
        state = "awaiting-owner-review"
    else:
        state = "not-started"
    if state == "awaiting-owner-review":
        owner_review = "awaiting-owner-review"
    return Readiness(state, owner_review, state in {"private-candidate", "private-validated", "awaiting-owner-review"}, False, tuple(sorted(set(reasons))))


def can_transition(current: str, target: str) -> bool:
    """Return whether a lane may move between states without skipping gates."""
    return target in _ALLOWED_TRANSITIONS.get(current, set())


def require_transition(current: str, target: str) -> None:
    """Raise when a requested state change skips the owner/publication gate."""
    if current not in READINESS_STATES or target not in READINESS_STATES:
        raise ReadinessError("readiness transition uses an unknown state")
    if not can_transition(current, target):
        raise ReadinessError(f"invalid readiness transition: {current} -> {target}")


def require_private_boundary(value: Mapping[str, Any]) -> None:
    """Assert that a readiness mapping cannot be interpreted as publication."""
    validate_readiness(value)
    if value["public_release_allowed"] or value["state"] in {"approved-for-release", "published"}:
        raise ReadinessError("private rehearsal cannot contain a release-ready readiness state")
