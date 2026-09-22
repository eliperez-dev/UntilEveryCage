"""D6.1 private graph verification report contract.

This module defines the aggregate-only report emitted by the D6.1 verification
lane.  It is intentionally independent of the matcher and persistence
implementations so a real Docker/Postgres rehearsal can populate the same
schema once those lanes are integrated.

The report must never contain private row values, source paths, or raw
evidence.  Counts are useful for release review; they are not a publication
projection and do not authorize identity merges or claim transfer.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


D61_REPORT_SCHEMA_VERSION = "d6.1-real-verification-v1"
D61_PAGE_MAX = 100
REAL_REHEARSAL_ASSERTION = "nonzero genuine inferred connection required"


class D61ReportError(ValueError):
    """Raised when an aggregate D6.1 report violates its contract."""


def _count(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise D61ReportError(f"{field} must be a non-negative integer")
    return value


def _counts(value: Mapping[str, Any], field: str) -> dict[str, int]:
    if not isinstance(value, Mapping):
        raise D61ReportError(f"{field} must be an object")
    return {str(key): _count(child, f"{field}.{key}") for key, child in value.items()}


def _row_free(value: Any, path: str = "report") -> None:
    """Reject raw/private values and path-like fields in report output."""
    forbidden_keys = {
        "source_values", "raw_fields", "coordinates", "latitude", "longitude",
        "address", "street", "phone", "email", "private_path", "path",
        "root", "private_root", "database_url", "dsn", "source_record_key",
    }
    if isinstance(value, Mapping):
        leaked = forbidden_keys.intersection(value)
        if leaked:
            raise D61ReportError(f"row-free report contains restricted fields at {path}: {sorted(leaked)}")
        for key, child in value.items():
            _row_free(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _row_free(child, f"{path}[{index}]")


def build_report(
    *,
    execution: str,
    authorized_handoffs: int = 0,
    private_rows_consumed: int = 0,
    candidate_count: int = 0,
    candidate_exact_count: int = 0,
    candidate_inferred_count: int = 0,
    persisted_exact_count: int = 0,
    persisted_inferred_count: int = 0,
    skipped_ambiguous_count: int = 0,
    skipped_reasons: Mapping[str, int] | None = None,
    negative_controls: int = 0,
    conflicting_controls: int = 0,
    genuine_inferred_connections: int = 0,
    real_rehearsal_executed: bool = False,
    idempotent: bool | None = None,
    api_pages: Mapping[str, int] | None = None,
    public_rows: int = 0,
    public_edges: int = 0,
    blockers: list[str] | tuple[str, ...] = (),
) -> dict[str, Any]:
    """Build and validate a deterministic aggregate D6.1 report.

    ``real_rehearsal_executed`` is deliberately separate from ``execution``:
    an offline/private-root diagnostic may produce useful candidate counts but
    cannot claim the mandatory Docker/Postgres assertion passed.
    """
    if not isinstance(execution, str) or not execution.strip():
        raise D61ReportError("execution must be a non-empty string")
    if not isinstance(real_rehearsal_executed, bool):
        raise D61ReportError("real_rehearsal_executed must be boolean")
    for field, value in (
        ("authorized_handoffs", authorized_handoffs),
        ("private_rows_consumed", private_rows_consumed),
        ("candidate_count", candidate_count),
        ("candidate_exact_count", candidate_exact_count),
        ("candidate_inferred_count", candidate_inferred_count),
        ("persisted_exact_count", persisted_exact_count),
        ("persisted_inferred_count", persisted_inferred_count),
        ("skipped_ambiguous_count", skipped_ambiguous_count),
        ("negative_controls", negative_controls),
        ("conflicting_controls", conflicting_controls),
        ("genuine_inferred_connections", genuine_inferred_connections),
        ("public_rows", public_rows),
        ("public_edges", public_edges),
    ):
        _count(value, field)
    reasons = _counts(skipped_reasons or {}, "skipped.reasons")
    if sum(reasons.values()) > skipped_ambiguous_count:
        raise D61ReportError("skipped.reasons cannot exceed skipped.ambiguous_blocks")
    pages = _counts(api_pages or {}, "api.pages")
    if any(value > D61_PAGE_MAX for value in pages.values()):
        raise D61ReportError("API page counts cannot exceed the page maximum")
    if idempotent is not None and not isinstance(idempotent, bool):
        raise D61ReportError("idempotent must be boolean or null")
    if not isinstance(blockers, (list, tuple)) or any(not isinstance(item, str) or not item.strip() for item in blockers):
        raise D61ReportError("blockers must contain non-empty strings")
    blockers = list(dict.fromkeys(blockers))
    if not real_rehearsal_executed:
        blockers.append("mandatory real Docker/Postgres inferred-edge rehearsal is pending")
    if real_rehearsal_executed:
        if authorized_handoffs < 1:
            blockers.append("real rehearsal did not consume an authorized retained handoff")
        if genuine_inferred_connections < 1:
            blockers.append("real Docker/Postgres rehearsal did not prove a genuine inferred connection")
        if persisted_inferred_count < 1:
            blockers.append("real rehearsal persisted zero inferred edges")
        if negative_controls < 1:
            blockers.append("real rehearsal is missing a negative control")
        if conflicting_controls < 1:
            blockers.append("real rehearsal is missing a conflicting control")
    if public_rows != 0 or public_edges != 0:
        raise D61ReportError("D6.1 verification must report zero public output")
    status = "verified" if real_rehearsal_executed and genuine_inferred_connections > 0 and not blockers else "pending-real-rehearsal"
    report = {
        "schema_version": D61_REPORT_SCHEMA_VERSION,
        "status": status,
        "scope": {
            "execution": execution,
            "authorized_handoffs": authorized_handoffs,
            "private_rows_consumed": private_rows_consumed,
            "row_payloads_in_report": False,
        },
        "candidates": {
            "total": candidate_count,
            "exact": candidate_exact_count,
            "inferred": candidate_inferred_count,
            "ruleset_output_only": True,
        },
        "persisted": {
            "total": persisted_exact_count + persisted_inferred_count,
            "exact": persisted_exact_count,
            "inferred": persisted_inferred_count,
            "idempotent": idempotent,
            "storage_cap": None,
        },
        "skipped": {
            "ambiguous_blocks": skipped_ambiguous_count,
            "reasons": reasons,
        },
        "controls": {
            "negative": negative_controls,
            "conflicting": conflicting_controls,
            "genuine_inferred_connections": genuine_inferred_connections,
            "automatic_merge": False,
            "claim_transfer": False,
        },
        "api": {
            "page_max": D61_PAGE_MAX,
            "storage_cap": None,
            "pages_observed": pages,
            "filters": ["connection_type", "min_confidence", "source_id", "entity_id", "include_conflicting", "suppressed", "cursor"],
            "inferred_metadata": True,
            "disclaimer": "Confidence is a deterministic ruleset estimate, not a measured probability.",
        },
        "publication": {
            "public_rows": public_rows,
            "public_edges": public_edges,
            "public_projection": False,
            "publication_status": "not_eligible",
        },
        "real_rehearsal": {
            "required": True,
            "executed": real_rehearsal_executed,
            "genuine_inferred_connections": genuine_inferred_connections,
            "assertion": REAL_REHEARSAL_ASSERTION,
        },
        "blockers": blockers,
    }
    validate_report(report)
    return report


def validate_report(report: Mapping[str, Any]) -> None:
    """Validate a report loaded from disk; fail closed on unknown shape."""
    if not isinstance(report, Mapping) or report.get("schema_version") != D61_REPORT_SCHEMA_VERSION:
        raise D61ReportError(f"schema_version must be {D61_REPORT_SCHEMA_VERSION}")
    if report.get("status") not in {"verified", "pending-real-rehearsal"}:
        raise D61ReportError("unknown D6.1 status")
    for section in ("scope", "candidates", "persisted", "skipped", "controls", "api", "publication", "real_rehearsal"):
        if not isinstance(report.get(section), Mapping):
            raise D61ReportError(f"{section} must be an object")
    if report["scope"].get("row_payloads_in_report") is not False:
        raise D61ReportError("row_payloads_in_report must be false")
    if report["api"].get("page_max") != D61_PAGE_MAX or report["api"].get("storage_cap") is not None:
        raise D61ReportError("API must distinguish page maximum from unbounded storage")
    if report["publication"].get("public_rows") != 0 or report["publication"].get("public_edges") != 0:
        raise D61ReportError("public output must remain zero")
    if report["real_rehearsal"].get("required") is not True:
        raise D61ReportError("real rehearsal is mandatory")
    _row_free(report)


__all__ = ["D61_PAGE_MAX", "D61_REPORT_SCHEMA_VERSION", "D61ReportError", "REAL_REHEARSAL_ASSERTION", "build_report", "validate_report"]
