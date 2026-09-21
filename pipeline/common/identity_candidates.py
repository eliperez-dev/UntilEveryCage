"""Safe identity-candidate and review/lineage contracts.

This module deliberately models *possible* connections, not canonical
identity.  A candidate can be useful to a reviewer while remaining private,
review-required, and unable to transfer claims or merge entities.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping


class CandidateSafetyError(ValueError):
    """Raised when a proposed edge would overstate identity evidence."""


_BANDS = ("exact", "high", "probable", "possible", "low")
_REVIEW_STATES = {"unreviewed", "review_required", "accepted", "rejected", "deferred", "conflicted", "superseded", "reversed"}
_REVIEW_ACTIONS = {"accept", "reject", "defer", "conflict", "supersede", "reverse"}
_SINGLE_SIGNAL_METHODS = {"name_only", "address_only", "phone_only", "proximity_only", "geocoder_only", "fuzzy_only"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CandidateSafetyError(f"{field} must be a non-empty string")
    return value.strip()


def _score(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
        raise CandidateSafetyError("confidence_score must be between 0 and 1")
    return round(float(value), 6)


def confidence_band(score: float, method: str, features: Mapping[str, Any], contradictions: Iterable[Any] = ()) -> str:
    """Return a deliberately conservative, explainable confidence band."""
    score = _score(score)
    method = _text(method, "match_method").lower()
    if method in _SINGLE_SIGNAL_METHODS:
        return "possible" if score < 0.75 else "probable"
    if method in {"exact_source_identifier", "authoritative_crosswalk"} and score >= 0.99 and not list(contradictions):
        return "exact"
    feature_count = len([key for key, value in features.items() if value not in (None, False, "", [], {})])
    if score >= 0.9 and feature_count >= 2 and not list(contradictions):
        return "high"
    if score >= 0.65 and feature_count >= 2:
        return "probable"
    return "possible" if score >= 0.35 else "low"


def _source_pair(left_source_id: str, right_source_id: str) -> tuple[str, str]:
    return _text(left_source_id, "left_source_id"), _text(right_source_id, "right_source_id")


def build_candidate_edge(
    *,
    source_id: str,
    source_record_key: str,
    left_identifier: Mapping[str, Any],
    right_identifier: Mapping[str, Any],
    match_method: str,
    confidence_score: float,
    contributing_features: Mapping[str, Any],
    contradictory_evidence: Iterable[Any] = (),
    provenance: Mapping[str, Any],
    algorithm_version: str,
    observed_at: str | None = None,
    candidate_id: str | None = None,
) -> dict[str, Any]:
    """Build a row-free candidate edge with fail-closed review defaults.

    Both endpoints remain source-qualified.  This function never emits an
    accepted edge, canonical ID, merge instruction, or claim-transfer flag.
    """
    source_id = _text(source_id, "source_id")
    source_record_key = _text(source_record_key, "source_record_key")
    method = _text(match_method, "match_method").lower()
    algorithm_version = _text(algorithm_version, "algorithm_version")
    if not isinstance(contributing_features, Mapping):
        raise CandidateSafetyError("contributing_features must be an object")
    if not isinstance(provenance, Mapping) or not provenance:
        raise CandidateSafetyError("provenance must be a non-empty object")
    contradictions = list(contradictory_evidence)
    score = _score(confidence_score)
    left_source, right_source = _source_pair(left_identifier.get("source_id"), right_identifier.get("source_id"))
    if left_source == right_source and left_identifier.get("value") == right_identifier.get("value"):
        raise CandidateSafetyError("candidate endpoints must be distinct")
    for endpoint, label in ((left_identifier, "left_identifier"), (right_identifier, "right_identifier")):
        _text(endpoint.get("identifier_type"), f"{label}.identifier_type")
        _text(endpoint.get("value"), f"{label}.value")
        if endpoint.get("identity_scope", "source_scoped") != "source_scoped":
            raise CandidateSafetyError("candidate identifiers must remain source-scoped")
    cross_source = left_source != right_source
    us_pair = {left_source, right_source} == {"us.aphis", "us.fsis"}
    if us_pair:
        # Even an explicit bridge is merely a review candidate.
        review_state = "review_required"
        if method not in {"explicit_authoritative_crosswalk", "human_supplied_bridge"}:
            raise CandidateSafetyError("APHIS/FSIS edges require an explicit bridge or remain unresolved")
    elif method in _SINGLE_SIGNAL_METHODS:
        feature_count = len([key for key, value in contributing_features.items() if value not in (None, False, "", [], {})])
        if feature_count < 2:
            raise CandidateSafetyError("single-signal identity matches remain unresolved")
        review_state = "review_required"
    else:
        review_state = "review_required"
    band = confidence_band(score, method, contributing_features, contradictions)
    disclaimer = (
        "Candidate connection only; not a canonical identity, not human verified, and must not transfer claims. "
        f"Confidence band: {band}. Review before relying on this connection."
    )
    payload = {
        "candidate_id": candidate_id or f"candidate:{source_id}:{source_record_key}:{left_source}:{right_source}",
        "source_id": source_id,
        "source_record_key": source_record_key,
        "left_identifier": {"source_id": left_source, **dict(left_identifier), "identity_scope": "source_scoped"},
        "right_identifier": {"source_id": right_source, **dict(right_identifier), "identity_scope": "source_scoped"},
        "cross_source": cross_source,
        "match_method": method,
        "confidence_score": score,
        "confidence_band": band,
        "contributing_features": dict(contributing_features),
        "contradictory_evidence": contradictions,
        "provenance": dict(provenance),
        "observed_at": observed_at or _now(),
        "algorithm_version": algorithm_version,
        "review_state": review_state,
        "storage_state": "private",
        "privacy_status": "pending",
        "publication_status": "not_eligible",
        "disclaimer": disclaimer,
        "automatic_merge": False,
        "transfers_claims": False,
    }
    return payload


def build_review_event(*, candidate_id: str, action: str, reason: str, reviewer_role: str, event_id: str | None = None, previous_event_id: str | None = None, decided_at: str | None = None) -> dict[str, Any]:
    """Create one append-only review decision; it never mutates a candidate."""
    action = _text(action, "action").lower()
    if action not in _REVIEW_ACTIONS:
        raise CandidateSafetyError(f"unsupported review action: {action}")
    return {
        "event_id": event_id or f"review:{_text(candidate_id, 'candidate_id')}:{action}",
        "candidate_id": candidate_id,
        "action": action,
        "reason": _text(reason, "reason"),
        "reviewer_role": _text(reviewer_role, "reviewer_role"),
        "previous_event_id": previous_event_id,
        "decided_at": decided_at or _now(),
        "publication_status": "not_eligible",
    }


def build_lineage_event(*, event_type: str, candidate_id: str, subject_identifier_ids: Iterable[str], reason: str, actor_role: str, event_id: str | None = None, occurred_at: str | None = None) -> dict[str, Any]:
    """Create append-only merge/split/reversal history without rewriting IDs."""
    event_type = _text(event_type, "event_type").lower()
    if event_type not in {"merge", "split", "reversal", "supersede"}:
        raise CandidateSafetyError("lineage event_type must be merge, split, reversal, or supersede")
    subjects = [_text(value, "subject_identifier_id") for value in subject_identifier_ids]
    if not subjects:
        raise CandidateSafetyError("lineage events require at least one subject identifier")
    return {
        "event_id": event_id or f"lineage:{_text(candidate_id, 'candidate_id')}:{event_type}",
        "event_type": event_type,
        "candidate_id": candidate_id,
        "subject_identifier_ids": subjects,
        "reason": _text(reason, "reason"),
        "actor_role": _text(actor_role, "actor_role"),
        "occurred_at": occurred_at or _now(),
        "canonical_merge_executed": False,
        "publication_status": "not_eligible",
    }


def build_review_packet_manifest(candidates: Iterable[Mapping[str, Any]], *, synthetic_correct: int = 0, synthetic_total: int = 0, human_adjudicated: int = 0, human_correct: int = 0, gold_set_available: bool = False) -> dict[str, Any]:
    """Return aggregate-only evaluation data; never serialize candidate rows."""
    items = list(candidates)
    bands = Counter(str(item.get("confidence_band", "unknown")) for item in items)
    methods = Counter(str(item.get("match_method", "unknown")) for item in items)
    states = Counter(str(item.get("review_state", "unknown")) for item in items)
    return {
        "schema_version": "identity-review-packet-v1",
        "candidate_count": len(items),
        "confidence_band_counts": dict(sorted(bands.items())),
        "match_method_counts": dict(sorted(methods.items())),
        "review_state_counts": dict(sorted(states.items())),
        "synthetic_metrics": {"correct": synthetic_correct, "total": synthetic_total, "precision": (synthetic_correct / synthetic_total if synthetic_total else None)},
        "human_adjudication": {"reviewed_count": human_adjudicated, "correct_count": human_correct, "precision": (human_correct / human_adjudicated if human_adjudicated else None), "gold_set_available": gold_set_available, "recall": None if not gold_set_available else "requires_gold_set"},
        "row_payloads_included": False,
        "public_exposure": False,
        "disclaimer": "Candidate edges are private leads, not canonical identities. Human precision is unavailable until an authorized sample is adjudicated; recall requires a gold set.",
    }

