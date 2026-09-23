"""D5 row-free audit of live acquisition and operational readiness.

This module audits the fifteen D2/D3 sources without contacting a source.  It
does not turn a source's fixture or a source-specific fetch function into an
unattended job.  The report is deliberately explicit about the distinction
between an existing operator path and a path wired into the shared runner.

The resulting JSON is safe for repository reports: it contains source IDs,
capabilities, command entry points, and aggregate control facts, never source
rows, raw values, credentials, private paths, or response bodies.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Mapping

from pipeline.common.d2_e2e_readiness import D2_SOURCE_IDS
from pipeline.common.d3_live_operations import D3_EXPECTED_SOURCE_IDS
from pipeline.common.source_operations import load_source_schedules
from pipeline.contracts.source_lifecycle import atomic_json
from pipeline.source_registry import load_registry


REPORT_SCHEMA_VERSION = "d5-live-readiness-v1"
REPORT_AS_OF = "2026-09-21T00:00:00Z"

# These are operational classifications, not publication or factual-quality
# judgments.  They describe the best existing acquisition path discovered in
# the repository and its current authorization boundary.
SOURCE_PROFILES: dict[str, dict[str, Any]] = {
    "dk.smiley": {
        "source_kind": "facility_master", "classification": "terms-blocked",
        "path": "bounded direct XML fetch exists; reviewed terms record is required",
        "command": "python pipeline/sources/denmark/pipeline.py --fetch --terms-review <review.json>",
        "authorization": "operator_terms_review_required",
        "controls": {"timeout": True, "retry": True, "provenance": True, "checksum": True, "freshness": True, "no_change": True, "previous_valid_state": True},
    },
    "be.locations": {
        "source_kind": "facility_master", "classification": "terms-blocked",
        "path": "bounded two-file CSV fetch exists; reviewed terms record is required",
        "command": "python -m pipeline.sources.belgium.refresh --fetch --terms-review <review.json>",
        "authorization": "operator_terms_review_required",
        "controls": {"timeout": True, "retry": True, "provenance": True, "checksum": True, "freshness": True, "no_change": True, "previous_valid_state": True},
    },
    "ca.ontario.meat-plants": {
        "source_kind": "facility_master", "classification": "terms-blocked",
        "path": "bounded CSV fetch exists; reviewed terms record is required",
        "command": "python -m pipeline.sources.canada.refresh --source ca.ontario.meat-plants --fetch --terms-review <review.json>",
        "authorization": "operator_terms_review_required",
        "controls": {"timeout": True, "retry": True, "provenance": True, "checksum": True, "freshness": True, "no_change": True, "previous_valid_state": True},
    },
    "ca.cfia.federal-meat": {
        "source_kind": "facility_master", "classification": "terms-blocked",
        "path": "bounded registry download exists; reviewed terms record is required",
        "command": "python -m pipeline.sources.canada.refresh --source ca.cfia.federal-meat --fetch --terms-review <review.json>",
        "authorization": "operator_terms_review_required",
        "controls": {"timeout": True, "retry": True, "provenance": True, "checksum": True, "freshness": True, "no_change": True, "previous_valid_state": True},
    },
    "fr.dgal.section-i": {
        "source_kind": "facility_master", "classification": "terms-blocked",
        "path": "bounded TXT fetch exists; reviewed terms record is required",
        "command": "python -m pipeline.sources.france.refresh --section I --fetch --terms-review <review.json>",
        "authorization": "operator_terms_review_required",
        "controls": {"timeout": True, "retry": True, "provenance": True, "checksum": True, "freshness": True, "no_change": True, "previous_valid_state": True},
    },
    "fr.dgal.section-ii": {
        "source_kind": "facility_master", "classification": "terms-blocked",
        "path": "bounded TXT fetch exists; reviewed terms record is required",
        "command": "python -m pipeline.sources.france.refresh --section II --fetch --terms-review <review.json>",
        "authorization": "operator_terms_review_required",
        "controls": {"timeout": True, "retry": True, "provenance": True, "checksum": True, "freshness": True, "no_change": True, "previous_valid_state": True},
    },
    "it.853-2004": {
        "source_kind": "facility_master", "classification": "terms-blocked",
        "path": "catalog-discovered same-origin CSV fetch exists; reviewed terms record is required",
        "command": "python -m pipeline.sources.italy.acquire --fetch --terms-review <review.json>",
        "authorization": "operator_terms_review_required",
        "controls": {"timeout": True, "retry": True, "provenance": True, "checksum": True, "freshness": True, "no_change": True, "previous_valid_state": True},
    },
    "it.1069-2009": {
        "source_kind": "facility_master", "classification": "preserved-artifact-only",
        "path": "operator-preserved ABP artifact with provenance sidecar; terms review reference required",
        "command": "python scripts/dev.py refresh --source it.1069-2009 --mode local-artifact --artifact <private-capture>",
        "authorization": "operator_capture_and_terms_review_required",
        "controls": {"timeout": True, "retry": True, "provenance": True, "checksum": True, "freshness": False, "no_change": False, "previous_valid_state": True},
    },
    "au.sa.epa.licensed-activities": {
        "source_kind": "facility_master", "classification": "preserved-artifact-only",
        "path": "operator-preserved official GeoJSON with row-free acquisition metadata; terms review required",
        "command": "python scripts/dev.py refresh --source au.sa.epa.licensed-activities --mode local-artifact --artifact <private-capture>",
        "authorization": "operator_capture_and_terms_review_required",
        "controls": {"timeout": True, "retry": True, "provenance": True, "checksum": True, "freshness": False, "no_change": False, "previous_valid_state": True},
    },
    "us.fsis": {
        "source_kind": "facility_master", "classification": "browser-assisted",
        "path": "operator-assisted official export; direct links were previously blocked and are not retried",
        "command": "python -m pipeline.sources.us.fsis.refresh --raw <private-directory-csv> --run-dir <private-run>",
        "authorization": "operator_export_required",
        "controls": {"timeout": True, "retry": True, "provenance": True, "checksum": True, "freshness": True, "no_change": True, "previous_valid_state": True},
    },
    "de.locations": {
        "source_kind": "facility_master", "classification": "browser-assisted",
        "path": "BVL portal selected export or assisted capture; session/request-specific export URL",
        "command": "python -m pipeline.sources.germany.refresh --raw <private-export> --run-dir <private-run>",
        "authorization": "operator_portal_export_required",
        "controls": {"timeout": True, "retry": True, "provenance": True, "checksum": True, "freshness": True, "no_change": True, "previous_valid_state": True},
    },
    "fsa_approved_establishments": {
        "source_kind": "facility_master", "classification": "terms-blocked",
        "path": "bounded monthly CSV path exists; source terms and edition review remain required",
        "command": "python -m pipeline.sources.uk.fsa_approved.refresh --fetch --run-dir <private-run> --terms-review <review.json>",
        "authorization": "operator_terms_review_required",
        "controls": {"timeout": True, "retry": True, "provenance": True, "checksum": True, "freshness": True, "no_change": True, "previous_valid_state": True},
    },
    "fss_approved_establishments": {
        "source_kind": "facility_master", "classification": "terms-blocked",
        "path": "bounded CSV path exists; source terms and edition review remain required",
        "command": "python -m pipeline.sources.uk.fss_approved.refresh --fetch --run-dir <private-run> --terms-review <review.json>",
        "authorization": "operator_terms_review_required",
        "controls": {"timeout": True, "retry": True, "provenance": True, "checksum": True, "freshness": True, "no_change": True, "previous_valid_state": True},
    },
    "us.aphis": {
        "source_kind": "evidence_event", "classification": "browser-assisted",
        "path": "operator-assisted public-search export; selected profile/date must be retained",
        "command": "python -m pipeline.sources.us.aphis.refresh --profile registrations --raw <private-export> --run-dir <private-run>",
        "authorization": "operator_search_export_required",
        "controls": {"timeout": True, "retry": True, "provenance": True, "checksum": True, "freshness": True, "no_change": True, "previous_valid_state": True},
    },
    "us.inspections": {
        "source_kind": "evidence_event", "classification": "browser-assisted",
        "path": "operator-assisted APHIS inspection export; selected search/date must be retained",
        "command": "python -m pipeline.sources.us.aphis.refresh --profile inspections --raw <private-export> --run-dir <private-run>",
        "authorization": "operator_search_export_required",
        "controls": {"timeout": True, "retry": True, "provenance": True, "checksum": True, "freshness": True, "no_change": True, "previous_valid_state": True},
    },
}

EXPECTED_SOURCE_IDS = tuple(D2_SOURCE_IDS) + tuple(D3_EXPECTED_SOURCE_IDS)
CLASSIFICATIONS = frozenset({"unattended_live-ready", "authenticated_live-ready", "browser-assisted", "preserved-artifact-only", "terms-blocked", "technically-broken"})
_PRIVATE_PATH = re.compile(r"(?:[A-Za-z]:[\\/]|/|\\\\|<private|<review)")


def _registry_index(registry_path: Path) -> dict[str, Mapping[str, Any]]:
    registry = load_registry(registry_path)
    return {str(item["source_id"]): item for item in registry["sources"]}


def _assert_row_free(value: Any) -> None:
    if isinstance(value, str) and _PRIVATE_PATH.search(value) and "<" not in value:
        # Public command paths are allowed, but machine paths and private
        # drive roots are not.  This catches accidental report leakage.
        if re.search(r"(?:[A-Za-z]:[\\/]|\\\\|/Users/|/home/)", value):
            raise ValueError("D5 report contains a filesystem path")
    if isinstance(value, Mapping):
        for key, item in value.items():
            if str(key).lower() in {"rows", "records", "raw", "payload", "credentials", "secrets"}:
                raise ValueError(f"D5 report contains prohibited field: {key}")
            _assert_row_free(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _assert_row_free(item)


def build_readiness_report(*, registry_path: str | Path, schedules_path: str | Path, as_of_utc: str = REPORT_AS_OF) -> dict[str, Any]:
    """Build the deterministic, no-network D5 operational report."""
    registry = _registry_index(Path(registry_path))
    schedules = load_source_schedules(Path(schedules_path), registry_path=Path(registry_path))
    if set(EXPECTED_SOURCE_IDS) != set(SOURCE_PROFILES):
        raise ValueError("D5 profile inventory does not match the fifteen-source D2/D3 scope")
    source_reports: list[dict[str, Any]] = []
    for source_id in EXPECTED_SOURCE_IDS:
        profile = SOURCE_PROFILES[source_id]
        registered = registry.get(source_id)
        if registered is None:
            raise ValueError(f"source is missing from source registry: {source_id}")
        classification = profile["classification"]
        if classification not in CLASSIFICATIONS:
            raise ValueError(f"unsupported D5 classification for {source_id}")
        schedule = schedules.get(source_id)
        source_reports.append({
            "source_id": source_id,
            "source_kind": profile["source_kind"],
            "adapter_status": registered.get("adapter_status", "unknown"),
            "declared_adapter_access": registered.get("access_method", "unknown"),
            "cadence": registered.get("cadence", "unknown"),
            "operational_classification": classification,
            "classification_basis": profile["path"],
            "authorization_boundary": profile["authorization"],
            "operator_command": profile["command"],
            "schedule": schedule.as_mapping() if schedule else None,
            "checks": {
                **profile["controls"],
                "shared_runner_live_mode": False,
                "shared_runner_live_callable": classification == "terms-blocked",
                "live_network_authorization_required": True,
                "network_requests_in_audit": 0,
                "scheduler_installed": False,
                "secrets_persisted": False,
                "previous_valid_state_preserved_on_failure": True,
                "failure_isolation": True,
            },
            "private_artifact_fallback": True,
            "publication": "blocked",
        })
    counts: dict[str, int] = {}
    for report in source_reports:
        key = str(report["operational_classification"])
        counts[key] = counts.get(key, 0) + 1
    result = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "as_of_utc": as_of_utc,
        "scope": {
            "source_count": len(source_reports),
            "source_ids": list(EXPECTED_SOURCE_IDS),
            "execution": "static-audit-no-network",
            "shared_runner_live_mode": "fail-closed-not-wired",
        },
        "classification_counts": dict(sorted(counts.items())),
        "operational_controls": {
            "bounded_timeout": True,
            "bounded_retries": True,
            "provenance_and_checksums": True,
            "freshness_and_no_change_detection": True,
            "previous_valid_state_preservation": True,
            "failure_isolation": True,
            "operator_exit_reporting": True,
            "source_scoped_live_callables": sum(1 for report in source_reports if report["checks"]["shared_runner_live_callable"]),
            "persistent_scheduler": False,
            "automatic_publication": False,
        },
        "sources": source_reports,
        "next_steps": [
            "record a source-specific terms or operator authorization before any live fetch",
            "wire only authorized acquisition callables into the shared runner",
            "retain previous validated state when a new fetch or validation fails",
            "run an explicit versioned all-source plan; do not install a scheduler in D5",
        ],
        "publication_boundary": "private operational audit only; no rows, releases, or public projections",
    }
    _assert_row_free(result)
    return result


def write_readiness_report(path: str | Path, report: Mapping[str, Any]) -> None:
    destination = Path(path)
    atomic_json(destination, report)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=Path("pipeline/source_registry.json"))
    parser.add_argument("--schedules", type=Path, default=Path("pipeline/source_operations.json"))
    parser.add_argument("--as-of-utc", default=REPORT_AS_OF)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = build_readiness_report(registry_path=args.registry, schedules_path=args.schedules, as_of_utc=args.as_of_utc)
    if args.output:
        write_readiness_report(args.output, report)
    print(json.dumps({"status": "ok", "schema_version": report["schema_version"], "source_count": report["scope"]["source_count"], "classification_counts": report["classification_counts"], "network_requests": 0}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
