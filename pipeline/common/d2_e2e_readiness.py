"""Contract-focused, private D2 source-runner and readiness report.

This module deliberately exercises the runner boundary with synthetic fixture
summaries.  It does not acquire live sources and it never puts source rows,
addresses, coordinates, or private paths in its report.  A database sink is an
optional dependency-injected boundary used by the disposable Postgres E2E;
the default runner remains fast and dependency-free.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Sequence

from pipeline.common.refresh_runner import RefreshCatalog, RefreshRunner
from pipeline.contracts.refresh import AdapterCapabilities, RefreshRequest


REPORT_SCHEMA_VERSION = "d2-disposable-e2e-readiness-v1"
FIXTURE_VERSION = "d2-synthetic-display-states-v2"
D2_SOURCE_IDS = (
    "dk.smiley",
    "be.locations",
    "ca.ontario.meat-plants",
    "ca.cfia.federal-meat",
    "fr.dgal.section-i",
    "fr.dgal.section-ii",
    "it.853-2004",
    "it.1069-2009",
    "au.sa.epa.licensed-activities",
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


class _SyntheticRefreshAdapter:
    """Synthetic D2 adapter used to exercise the production runner."""

    adapter_version = FIXTURE_VERSION

    def __init__(self, source_id: str, *, fail: bool = False) -> None:
        self.source_id = source_id
        self.fail = fail

    def refresh(self, *, mode: str, run_dir: Path, artifact: Path | None,
                options: Mapping[str, object]) -> Mapping[str, object]:
        if self.fail:
            raise RuntimeError("injected_fixture_failure")
        summary = _fixture_summary()
        return {
            **summary,
            "review_required": True,
            "promoted": False,
            "public_api_rows": 0,
            "public_surfaces": {"api": False, "map": False, "csv": False},
        }


def _synthetic_catalog(*, fail_source: str | None = None) -> RefreshCatalog:
    catalog = RefreshCatalog.__new__(RefreshCatalog)
    catalog.sources = {source_id: {"source_id": source_id, "adapter_status": "implemented_partial"} for source_id in D2_SOURCE_IDS}
    catalog.capabilities = {}
    catalog.adapters = {}
    for source_id in D2_SOURCE_IDS:
        capabilities = AdapterCapabilities(
            source_id=source_id, adapter_version=FIXTURE_VERSION,
            schema_version=FIXTURE_VERSION, acquisition="fixture",
            geocoding="disabled", publication="human_gate_required",
        )
        catalog.capabilities[source_id] = capabilities
        catalog.register(_SyntheticRefreshAdapter(source_id, fail=source_id == fail_source), capabilities)
    return catalog


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
    _resume_results(resume_report, selected) if resume_report is not None else None
    runner_root = Path(__file__).with_name(".d2-runner")
    if resume_report is None:
        shutil.rmtree(runner_root, ignore_errors=True)

    importer = None
    if database_sink is not None:
        def importer(run_dir: Path, _database_url: str) -> Mapping[str, object]:
            source_id = run_dir.name
            inserted = database_sink(source_id, FIXTURE_CASES)
            if not isinstance(inserted, int) or inserted < 0 or inserted > 3:
                raise D2ReadinessError("database sink returned an invalid aggregate count")
            return {"inserted": inserted, "public_api_rows": 0}

    request = RefreshRequest(
        source_ids=tuple(selected), mode="fixture", output_root=runner_root,
        resume=resume_report is not None,
        import_candidates=database_sink is not None,
        database_url="postgresql://127.0.0.1/d2-disposable" if database_sink is not None else None,
    )
    runner_result = RefreshRunner(_synthetic_catalog(fail_source=fail_source), candidate_importer=importer).run(request)
    results: list[dict[str, object]] = []
    for item in runner_result["results"]:
        source_id = str(item["source_id"])
        status = "passed" if item["status"] == "succeeded" else item["status"]
        summary = item.get("summary") if isinstance(item.get("summary"), Mapping) else {}
        imported = summary.get("candidate_import") if isinstance(summary, Mapping) else {}
        inserted = int(imported.get("inserted", 0)) if isinstance(imported, Mapping) else 0
        if status == "failed":
            attempts = item.get("attempts") if isinstance(item.get("attempts"), list) else []
            error = str(attempts[0].get("error", "")) if attempts and isinstance(attempts[0], Mapping) else ""
            category = "injected_fixture_failure" if "injected_fixture_failure" in error else "private_candidate_insert_failure"
            results.append(_source_result(source_id, "failed", failure_category=category, database_candidate_rows=inserted))
        else:
            results.append(_source_result(source_id, status, database_candidate_rows=inserted))

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
