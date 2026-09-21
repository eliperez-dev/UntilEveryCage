"""Row-free data model for the private candidate review console.

This module derives operator context from the existing platform registry.  It
does not add a readiness state machine or make a release decision: the
classification is a conservative display label for acquisition/review
planning, while the source and country contracts remain authoritative.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping


REVIEW_CONSOLE_SCHEMA_VERSION = "private-review-console-v1"
READINESS_CLASSES = (
    "infrastructure-only",
    "acquisition-ready",
    "private-candidate-ready",
    "human-review-ready",
    "publication-eligible",
    "blocked",
)
ACQUIRED_STATES = frozenset({"artifact_private_only", "verified"})


def _as_text(value: Any, fallback: str = "unknown") -> str:
    return value.strip() if isinstance(value, str) and value.strip() else fallback


def classify_country(sources: Iterable[Mapping[str, Any]]) -> str:
    """Return a conservative operator label for one country.

    The label deliberately does not mirror ``Readiness.state``.  It is a
    human-facing matrix classification: blocked acquisition wins; only an
    explicit approved/public-release boundary can be publication-eligible.
    """
    items = list(sources)
    if not items:
        return "infrastructure-only"

    statuses = [item.get("status") if isinstance(item.get("status"), Mapping) else {} for item in items]
    acquisitions = {_as_text(status.get("acquisition"), "not_run") for status in statuses}
    if "blocked" in acquisitions:
        return "blocked"

    release_ready = all(
        item.get("owner_review", {}).get("state") == "approved"
        and item.get("readiness", {}).get("public_release_allowed") is True
        and item.get("publication", {}).get("state") in {"approved-for-release", "published"}
        for item in items
    )
    if release_ready:
        return "publication-eligible"

    acquired = acquisitions.intersection(ACQUIRED_STATES)
    pending = acquisitions.difference(ACQUIRED_STATES)
    if acquired and not pending:
        return "human-review-ready"
    if acquired:
        return "private-candidate-ready"
    if acquisitions == {"not_run"} and all(
        _as_text(status.get("metadata")) in {"verified", "partial"} for status in statuses
    ):
        return "acquisition-ready"
    return "infrastructure-only"


def _source_view(source: Mapping[str, Any]) -> dict[str, Any]:
    status = source.get("status") if isinstance(source.get("status"), Mapping) else {}
    readiness = source.get("readiness") if isinstance(source.get("readiness"), Mapping) else {}
    owner_review = source.get("owner_review") if isinstance(source.get("owner_review"), Mapping) else {}
    publication = source.get("publication") if isinstance(source.get("publication"), Mapping) else {}
    coverage = source.get("coverage") if isinstance(source.get("coverage"), Mapping) else {}
    attribution = source.get("attribution") if isinstance(source.get("attribution"), Mapping) else {}
    return {
        "source_id": _as_text(source.get("source_id")),
        "country_code": _as_text(source.get("country_code")),
        "jurisdiction_scope": _as_text(source.get("jurisdiction_scope")),
        "source_url": _as_text(source.get("source_url")),
        "access_method": _as_text(source.get("access_method")),
        "cadence": _as_text(source.get("cadence")),
        "attribution": {
            "source_origin": _as_text(attribution.get("source_origin")),
            "terms_status": _as_text(attribution.get("terms_status")),
            "attribution_required": attribution.get("attribution_required") is True,
            "notice": _as_text(attribution.get("notice")),
        },
        "coverage": {
            "completeness": _as_text(coverage.get("completeness")),
            "disappearance_semantics": _as_text(coverage.get("disappearance_semantics")),
            "limitations": [str(value) for value in coverage.get("limitations", []) if isinstance(value, str)],
        },
        "status": {
            "metadata": _as_text(status.get("metadata")),
            "acquisition": _as_text(status.get("acquisition")),
            "runtime_health": _as_text(status.get("runtime_health")),
            "publication_eligibility": _as_text(status.get("publication_eligibility")),
            "evidence": [str(value) for value in status.get("evidence", []) if isinstance(value, str)],
            "next_action": _as_text(status.get("next_action")),
        },
        "readiness": {
            "state": _as_text(readiness.get("state")),
            "owner_review": _as_text(readiness.get("owner_review")),
            "private_candidate": readiness.get("private_candidate") is True,
            "public_release_allowed": readiness.get("public_release_allowed") is True,
            "reasons": [str(value) for value in readiness.get("reasons", []) if isinstance(value, str)],
        },
        "owner_review": {
            "state": _as_text(owner_review.get("state")),
            "decision_recorded": bool(owner_review.get("decision_id")),
        },
        "publication": {
            "state": _as_text(publication.get("state")),
            "approval_required": publication.get("approval_required") is True,
            "reason": _as_text(publication.get("reason")),
        },
    }


def build_review_console_snapshot(registry: Mapping[str, Any], *, generated_at: str | None = None) -> dict[str, Any]:
    """Build a deterministic, row-free snapshot for the static operator UI."""
    source_records = [source for source in registry.get("sources", []) if isinstance(source, Mapping)]
    countries = [country for country in registry.get("countries", []) if isinstance(country, Mapping)]
    by_country: dict[str, list[Mapping[str, Any]]] = {}
    for source in source_records:
        code = _as_text(source.get("country_code"))
        by_country.setdefault(code, []).append(source)

    matrix: list[dict[str, Any]] = []
    for country in countries:
        code = _as_text(country.get("country_code"))
        sources = sorted(by_country.get(code, []), key=lambda source: _as_text(source.get("source_id")))
        source_views = [_source_view(source) for source in sources]
        status_counts = Counter(source["status"]["acquisition"] for source in source_views)
        source_summary = [
            f"{view['source_id']}: {view['status']['acquisition']} / {view['readiness']['state']}"
            for view in source_views
        ]
        matrix.append({
            "country_code": code,
            "display_name": _as_text(country.get("display_name"), code),
            "readiness_class": classify_country(sources),
            "source_count": len(source_views),
            "acquisition_counts": dict(sorted(status_counts.items())),
            "owner_review": _as_text((country.get("owner_review") or {}).get("state")),
            "publication_state": _as_text((country.get("publication") or {}).get("state")),
            "country_reasons": [
                str(reason)
                for reason in ((country.get("readiness") or {}).get("reasons") or [])
                if isinstance(reason, str)
            ],
            "sources": source_views,
            "summary": "No release approval is implied; inspect source gates below.",
            "basis": source_summary,
        })

    matrix.sort(key=lambda country: country["country_code"])
    counts = Counter(country["readiness_class"] for country in matrix)
    return {
        "schema_version": REVIEW_CONSOLE_SCHEMA_VERSION,
        "generated_at": generated_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "contract_versions": registry.get("contract_versions", {}),
        "source_of_truth": {
            "platform_registry": "pipeline/source_registry.json + docs/source-status.json",
            "publication_boundary": "private staging only; no release approval or promotion implied",
        },
        "derived_context": True,
        "country_count": len(matrix),
        "source_count": sum(country["source_count"] for country in matrix),
        "readiness_counts": dict(sorted(counts.items())),
        "readiness_classes": list(READINESS_CLASSES),
        "states": list(READINESS_CLASSES),
        "classification_notes": {
            "blocked": "At least one registered source reports acquisition=blocked; acquisition blockers take precedence.",
            "acquisition-ready": "All registered sources have verified or partial metadata and acquisition has not run; this is not an authorization to acquire.",
            "private-candidate-ready": "At least one source is privately acquired/verified, while another registered source remains pending; no release is implied.",
            "human-review-ready": "All registered sources are privately acquired/verified and await explicit human review; no approval is implied.",
            "publication-eligible": "Only explicit owner approval plus a release-allowed contract can produce this label; it is absent from the current baseline unless those fields are recorded.",
            "infrastructure-only": "The registry provides infrastructure context, but the acquisition state is incomplete or not yet classifiable.",
        },
        "countries": {
            country["country_code"]: {
                "name": country["display_name"],
                "state": country["readiness_class"],
                "summary": country["summary"],
                "basis": country["basis"],
                "source_count": country["source_count"],
                "acquisition_counts": country["acquisition_counts"],
                "owner_review": country["owner_review"],
                "publication_state": country["publication_state"],
                "country_reasons": country["country_reasons"],
                "sources": country["sources"],
            }
            for country in matrix
        },
        "country_records": matrix,
        "publication_boundary": "This row-free snapshot is operator context only. It cannot approve, promote, or publish a release.",
    }
