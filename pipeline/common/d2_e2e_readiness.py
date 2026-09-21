"""Contract-focused, private D2 source-runner and readiness report.

This module deliberately exercises the runner boundary with synthetic fixture
summaries.  It does not acquire live sources and it never puts source rows,
addresses, coordinates, or private paths in its report.  A database sink is an
optional dependency-injected boundary used by the disposable Postgres E2E;
the default runner remains fast and dependency-free.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Callable, Mapping, Sequence


REPORT_SCHEMA_VERSION = "d2-disposable-e2e-readiness-v1"
FIXTURE_VERSION = "d2-synthetic-display-states-v1"
D2_SOURCE_IDS = (
    "dk.smiley",
    "be.locations",
    "ca.ontario.meat-plants",
    "ca.cfia.federal-meat",
    "fr.dgal.section-i",
    "fr.dgal.section-ii",
    "it.853-2004",
)
DISPLAY_STATES = ("exact", "city", "unmapped", "restricted", "quarantine")


class D2ReadinessError(ValueError):
    """Raised when a private D2 runner contract is invalid."""


@dataclass(frozen=True)
class FixtureCase:
    """A row-free description of one synthetic lifecycle case."""

    display_state: str
    candidate: bool
    quarantined: bool = False
    restricted: bool = False


FIXTURE_CASES = (
    FixtureCase("exact", candidate=True),
    FixtureCase("city", candidate=True),
    FixtureCase("unmapped", candidate=True),
    FixtureCase("restricted", candidate=False, restricted=True),
    FixtureCase("quarantine", candidate=False, quarantined=True),
)


def _fixture_summary() -> dict[str, object]:
    states = {state: 0 for state in DISPLAY_STATES}
    for case in FIXTURE_CASES:
        states[case.display_state] += 1
    return {
        "input_rows": len(FIXTURE_CASES),
        "candidate_rows": sum(case.candidate for case in FIXTURE_CASES),
        "quarantine_rows": sum(case.quarantined for case in FIXTURE_CASES),
        "restricted_rows": sum(case.restricted for case in FIXTURE_CASES),
        "display_states": states,
    }


def _validate_result(result: Mapping[str, object]) -> None:
    if result.get("review_required") is not True:
        raise D2ReadinessError("every D2 fixture must retain review-required defaults")
    if result.get("promoted") is not False:
        raise D2ReadinessError("D2 fixtures must not be promoted")
    surfaces = result.get("public_surfaces")
    if surfaces != {"api": False, "map": False, "csv": False}:
        raise D2ReadinessError("D2 fixtures must remain off every public surface")
    if result.get("public_api_rows") != 0:
        raise D2ReadinessError("D2 private rehearsal must expose zero public API rows")
    if result.get("display_states") != _fixture_summary()["display_states"]:
        raise D2ReadinessError("fixture display-state contract drifted")


def _source_result(source_id: str, status: str, *, failure_category: str | None = None,
                   database_candidate_rows: int = 0) -> dict[str, object]:
    summary = _fixture_summary()
    result: dict[str, object] = {
        "source_id": source_id,
        "status": status,
        "input_rows": summary["input_rows"],
        "candidate_rows": summary["candidate_rows"],
        "quarantine_rows": summary["quarantine_rows"],
        "restricted_rows": summary["restricted_rows"],
        "display_states": summary["display_states"],
        "review_required": True,
        "public_api_rows": 0,
        "promoted": False,
        "public_surfaces": {"api": False, "map": False, "csv": False},
        "database_candidate_rows": database_candidate_rows,
    }
    if failure_category is not None:
        result["failure_category"] = failure_category
    _validate_result(result)
    return result


def _validate_selection(selected_sources: Sequence[str] | None) -> list[str]:
    selected = list(D2_SOURCE_IDS if selected_sources is None else selected_sources)
    if not selected:
        raise D2ReadinessError("at least one source must be selected")
    if len(set(selected)) != len(selected):
        raise D2ReadinessError("source selection contains duplicates")
    unknown = sorted(set(selected) - set(D2_SOURCE_IDS))
    if unknown:
        raise D2ReadinessError(f"source selection contains unknown source(s): {', '.join(unknown)}")
    return selected


def _resume_results(resume_report: Mapping[str, object], selected: Sequence[str]) -> dict[str, Mapping[str, object]]:
    if resume_report.get("schema_version") != REPORT_SCHEMA_VERSION:
        raise D2ReadinessError("resume report has an incompatible schema")
    if resume_report.get("fixture_version") != FIXTURE_VERSION:
        raise D2ReadinessError("resume report has an incompatible fixture version")
    scope = resume_report.get("scope")
    if not isinstance(scope, Mapping) or list(scope.get("selected_sources", ())) != list(selected):
        raise D2ReadinessError("resume report selection does not match this run")
    values = resume_report.get("sources")
    if not isinstance(values, list):
        raise D2ReadinessError("resume report is missing source results")
    return {str(item["source_id"]): item for item in values if isinstance(item, Mapping) and "source_id" in item}


def build_report(*, selected_sources: Sequence[str] | None = None,
                 fail_source: str | None = None,
                 resume_report: Mapping[str, object] | None = None,
                 database_sink: Callable[[str, tuple[FixtureCase, ...]], int] | None = None) -> dict[str, object]:
    """Run the deterministic private fixture contract in source order.

    ``database_sink`` is intentionally injected so the lightweight contract
    tests do not require Docker.  It must return only the count of synthetic
    private candidate rows inserted; it must not return rows or payloads.
    """
    selected = _validate_selection(selected_sources)
    if fail_source is not None and fail_source not in selected:
        raise D2ReadinessError("fail-source must be one of the selected sources")
    previous = _resume_results(resume_report, selected) if resume_report is not None and database_sink is None else {}
    results: list[dict[str, object]] = []
    for source_id in selected:
        prior = previous.get(source_id)
        if prior is not None and prior.get("status") in {"passed", "resumed"}:
            result = dict(prior)
            result["status"] = "resumed"
            results.append(result)
            continue
        if source_id == fail_source:
            results.append(_source_result(source_id, "failed", failure_category="injected_fixture_failure"))
            continue
        try:
            inserted = database_sink(source_id, FIXTURE_CASES) if database_sink is not None else 0
            if not isinstance(inserted, int) or inserted < 0 or inserted > 3:
                raise D2ReadinessError("database sink returned an invalid aggregate count")
            results.append(_source_result(source_id, "passed", database_candidate_rows=inserted))
        except Exception:
            # Failure isolation is deliberate: the remaining sources still run
            # and the aggregate exits nonzero below.
            results.append(_source_result(source_id, "failed", failure_category="private_candidate_insert_failure"))

    successful = [item for item in results if item["status"] in {"passed", "resumed"}]
    failed = [item for item in results if item["status"] == "failed"]
    report: dict[str, object] = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "fixture_version": FIXTURE_VERSION,
        "scope": {
            "mode": "all-eligible" if selected == list(D2_SOURCE_IDS) else "selected",
            "eligible_sources": list(D2_SOURCE_IDS),
            "selected_sources": selected,
            "execution": "sequential",
        },
        "source_run": {
            "live_acquisition": "not-run",
            "adapter_execution": "not-run",
            "synthetic_fixture_contract": "executed",
        },
        "aggregate": {
            "selected_sources": len(selected),
            "passed_sources": len(successful),
            "failed_sources": len(failed),
            "resumed_sources": sum(item["status"] == "resumed" for item in results),
            "input_rows": sum(int(item["input_rows"]) for item in successful),
            "candidate_rows": sum(int(item["candidate_rows"]) for item in successful),
            "quarantine_rows": sum(int(item["quarantine_rows"]) for item in successful),
            "restricted_rows": sum(int(item["restricted_rows"]) for item in successful),
            "database_candidate_rows": sum(int(item["database_candidate_rows"]) for item in successful),
            "public_api_rows": 0,
            "promoted_releases": 0,
            "exit_code": 0 if not failed else 1,
        },
        "readiness": {
            "state": "private-candidate" if not failed else "blocked",
            "owner_review": "awaiting-owner-review",
            "private_candidate": True,
            "public_release_allowed": False,
            "publication": "blocked",
            "reasons": [
                "synthetic_fixture_only",
                "live_acquisition_not_run",
                "review_required_defaults",
                "public_surfaces_disabled",
            ] + (["source_failure_isolated"] if failed else []),
        },
        "database": {
            "mode": "disposable-postgis" if database_sink is not None else "not-requested",
            "private_candidate_insertion": database_sink is not None,
            "public_api_rows": 0,
            "promotion": "disabled",
        },
        "sources": results,
    }
    return report


def canonical_bytes(report: Mapping[str, object]) -> bytes:
    """Serialize a report deterministically for idempotency assertions."""
    return (json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def write_report(path: Path, report: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(report))


def report_fingerprint(report: Mapping[str, object]) -> str:
    return hashlib.sha256(canonical_bytes(report)).hexdigest()
