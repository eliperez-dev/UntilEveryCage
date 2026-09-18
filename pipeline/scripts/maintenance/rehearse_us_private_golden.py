"""Run a private, row-free U.S. golden-country rehearsal.

The rehearsal deliberately uses checked-in sanitized fixtures for the row
bearing stages.  The tracked FSIS and APHIS proof manifests are included only
as aggregate current-evidence boundaries; legacy snapshots are never used as
fixture input or as a substitute for a current source capture.

The disposable private run exercises acquisition metadata/assisted handoff,
typed adapters, quarantine, source-local identity, geospatial readiness,
accountability candidates, candidate construction, the private preview
contract, suppression, rerun stability, and operator review packets.  Raw,
parsed, normalized, candidate, and graph payloads stay under the ignored
private directory and are never copied into the output report.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

from pipeline.common.identity import record_key
from pipeline.common.orchestrator import run_private_lifecycle
from pipeline.common.source_operations import finalize_run_operations
from pipeline.contracts.adapter_contract import SourceArtifact
from pipeline.contracts.private_run import write_private_run_report
from pipeline.contracts.source_health import build_health_snapshot, write_health_snapshot
from pipeline.contracts.source_lifecycle import atomic_bytes, atomic_json
from pipeline.scripts.diagnostics.current_geospatial_readiness import audit_current
from pipeline.scripts.maintenance.rehearse_candidate_private_frontend import rehearse_candidate
from pipeline.sources.us.accountability.adapter import UsAccountabilityAdapter
from pipeline.sources.us.aphis.handoff import import_private_candidate
from pipeline.sources.us.aphis.refresh import refresh as refresh_aphis
from pipeline.sources.us.fsis.adapter import FsisMpiAdapter
from pipeline.sources.us.fsis.refresh import refresh as refresh_fsis


REPORT_VERSION = "us-private-golden-rehearsal-v1"
AS_OF_UTC = "2026-09-18T00:00:00Z"
FIXTURE_EFFECTIVE_DATE = "2026-09-14"
FORBIDDEN_KEYS = frozenset(
    {
        "records",
        "rows",
        "source_values",
        "raw_fields",
        "payload",
        "address",
        "street",
        "latitude",
        "longitude",
        "coordinates",
        "geocoder_query",
        "geocoder_response",
    }
)


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _fixture_artifact(path: Path, *, source_url: str, code_version: str, config_version: str, coverage: str, effective_date: str | None = FIXTURE_EFFECTIVE_DATE) -> SourceArtifact:
    return SourceArtifact(
        source_url=source_url,
        retrieved_at_utc=AS_OF_UTC,
        sha256=_sha256(path),
        byte_size=path.stat().st_size,
        effective_date=effective_date,
        code_version=code_version,
        config_version=config_version,
        rights_caveat="Sanitized fixture; source terms and field-level publication review remain open",
        privacy_caveat="Private staging; names, addresses, contacts, and coordinates require review",
        coverage=coverage,
    )


def _count_source_local_ids(path: Path, *fields: str) -> int:
    count = 0
    for row in _jsonl(path):
        normalized = row.get("normalized") if isinstance(row.get("normalized"), dict) else {}
        if any(normalized.get(field) for field in fields):
            count += 1
    return count


def _handoff_summary(path: Path) -> dict[str, Any]:
    manifest = _read_json(path)
    return {
        "available": True,
        "candidate_count": manifest.get("normalized_rows", manifest.get("candidate_rows", 0)),
        "candidate_sha256": manifest.get("normalized_sha256", manifest.get("records_sha256")),
        "graph_candidate_count": manifest.get("graph_candidate_rows", 0),
        "release_state": manifest.get("release_state"),
        "publication_state": manifest.get("publication_state"),
        "auto_merge": manifest.get("auto_merge", False),
    }


def _acquisition_summary(value: dict[str, Any]) -> dict[str, Any]:
    if "acquisition_method" in value:
        return {
            "method": value.get("acquisition_method"),
            "source_url": value.get("final_url") or value.get("requested_url"),
            "retrieved_at_utc": value.get("retrieved_at_utc"),
            "effective_date": value.get("effective_date"),
            "sha256": value.get("sha256"),
            "byte_size": value.get("byte_size"),
        }
    roles = {}
    for role, metadata in sorted(value.items()):
        if not isinstance(metadata, dict):
            continue
        roles[role] = {
            "method": metadata.get("acquisition_method"),
            "source_url": metadata.get("final_url") or metadata.get("requested_url"),
            "retrieved_at_utc": metadata.get("retrieved_at_utc"),
            "effective_date": metadata.get("effective_date"),
            "sha256": metadata.get("sha256"),
            "byte_size": metadata.get("byte_size"),
        }
    return {"method": "preserved_local_artifact_bundle", "roles": roles}


def _profile_summary(*, source_id: str, profile: str, root: Path, status: dict[str, Any], identity_fields: tuple[str, ...], handoff: Path | None) -> dict[str, Any]:
    lifecycle = Path(status["run_dir"])
    manifest = _read_json(lifecycle / "manifest.json")
    acquisition = _read_json(root / "acquisition-metadata.json")
    normalized_path = lifecycle / "normalized" / "records.jsonl"
    return {
        "source_id": source_id,
        "profile": profile,
        "status": status.get("status"),
        "acquisition": _acquisition_summary(acquisition),
        "stages": {
            "input_count": manifest.get("input_rows"),
            "normalized_count": manifest.get("normalized_rows"),
            "quarantine_count": manifest.get("quarantined_rows"),
            "quarantine_reasons": manifest.get("anomaly_counts", {}),
            "schema_fingerprint": manifest.get("schema_fingerprint"),
            "normalized_sha256": manifest.get("normalized_sha256"),
        },
        "source_local_identity": {
            "identified_count": _count_source_local_ids(normalized_path, *identity_fields),
            "identity_scope": "source-local; no cross-source merge",
        },
        "handoff": _handoff_summary(handoff) if handoff and handoff.is_file() else {"available": False},
        "operator_artifacts": {
            "qa": (lifecycle / "qa.json").is_file(),
            "health": (lifecycle / "source-health.json").is_file(),
            "review_packet": (lifecycle / "review-packet.json").is_file(),
            "release_diff": (lifecycle / "release-diff.json").is_file(),
        },
        "release": {
            "state": manifest.get("release_state", "not-created"),
            "publication_state": manifest.get("publication_state", "private-candidate"),
            "geocoding": manifest.get("geocoding", "disabled"),
            "public_exposure": False,
        },
    }


def _finalize_fsis_review(root: Path, status: dict[str, Any]) -> dict[str, Any]:
    lifecycle = Path(status["run_dir"])
    manifest = _read_json(lifecycle / "manifest.json")
    write_private_run_report(lifecycle, manifest)
    status = finalize_run_operations(
        root / "operations",
        lifecycle,
        manifest=manifest,
        status=status,
        config={
            "source_id": "us.fsis",
            "review_blockers": {
                "source": ["sanitized fixture only; current FSIS capture remains separately blocked"],
                "publication": ["no human approval or release promotion in rehearsal"],
            },
        },
    )
    write_health_snapshot(
        lifecycle / "source-health.json",
        build_health_snapshot(lifecycle, as_of_utc=AS_OF_UTC),
    )
    atomic_json(lifecycle / "run-status.json", status)
    return status


def _current_evidence(root: Path) -> dict[str, Any]:
    fsis_path = root / "data" / "manifests" / "us-fsis-proof-2026-09-18.json"
    aphis_path = root / "data" / "manifests" / "us-aphis-wave1-real-data-proof-2026-09-18.json"
    fsis = _read_json(fsis_path)
    aphis = _read_json(aphis_path)
    retrieval = aphis.get("retrieval", {})
    return {
        "interpretation": "aggregate current-evidence boundaries only; no current row payload is used as fixture input",
        "fsis": {
            "proof_manifest": fsis_path.name,
            "page_observed_in_normal_browser": fsis.get("page_observed_in_normal_browser"),
            "last_updated_observed": fsis.get("page_last_updated_observed"),
            "direct_csv_status": fsis.get("direct_csv_acquisition", {}).get("status"),
            "direct_csv_http_statuses": {
                "directory": fsis.get("direct_csv_acquisition", {}).get("directory_by_number_http_status"),
                "demographics": fsis.get("direct_csv_acquisition", {}).get("demographics_http_status"),
            },
            "raw_artifacts_captured": bool(fsis.get("direct_csv_acquisition", {}).get("raw_artifacts_captured")),
            "current_source_claim": bool(fsis.get("legacy_continuity_rehearsal", {}).get("current_source_claim")),
        },
        "aphis": {
            "proof_manifest": aphis_path.name,
            "captured_for": aphis.get("captured_for"),
            "release_state": aphis.get("release_state"),
            "publication_gate": aphis.get("publication_gate"),
            "profiles": {
                "annual_reports": {
                    "displayed_count": retrieval.get("annual_reports", {}).get("displayed_result_count"),
                    "captured_page_count": retrieval.get("annual_reports", {}).get("raw_pages"),
                    "capture_status": retrieval.get("annual_reports", {}).get("refresh_pages_succeeded"),
                },
                "registrations": {
                    "displayed_count": retrieval.get("registrations", {}).get("displayed_result_count"),
                    "captured_page_count": retrieval.get("registrations", {}).get("raw_pages"),
                    "failed_page_count": retrieval.get("registrations", {}).get("refresh_pages_failed"),
                },
                "inspections": {
                    "displayed_count": retrieval.get("inspections", {}).get("displayed_result_count"),
                    "captured_page_count": retrieval.get("inspections", {}).get("raw_pages"),
                    "remaining_pagination_count": retrieval.get("inspections", {}).get("pagination_boundary_remaining_rows"),
                },
            },
            "document_artifacts_captured": aphis.get("documents_and_amendments", {}).get("acquired_document_artifacts"),
            "failed_capture_count": len(aphis.get("failures", [])),
        },
        "state_inspection_programs": {
            "included": False,
            "semantics": "no state roster was acquired; absence is not closure",
        },
        "legacy_data_substitution": False,
    }


def _geospatial_summary(root: Path, profiles: list[dict[str, Any]]) -> dict[str, Any]:
    manifest_path = root / "candidate-sources.json"
    atomic_json(manifest_path, {"sources": profiles})
    audit = audit_current(manifest_path, root, AS_OF_UTC)
    totals = audit.get("totals_available_rows_only", {})
    per_source = []
    for item in audit.get("sources", []):
        metrics = item.get("metrics") or {}
        privacy = metrics.get("privacy_review_queue") or {}
        coordinate = metrics.get("coordinate_review_queue") or {}
        per_source.append(
            {
                "source_id": item.get("source_id"),
                "available": metrics.get("available", False),
                "candidate_count": metrics.get("records"),
                "display_states": metrics.get("display_states"),
                "evidence_states": metrics.get("evidence_states"),
                "privacy_review_count": privacy.get("rows"),
                "coordinate_review_count": coordinate.get("rows"),
                "suppressed_count": metrics.get("suppressed_rows"),
                "audit_status": metrics.get("audit_status"),
            }
        )
    return {
        "sources_checked": audit.get("sources_listed"),
        "sources_available": audit.get("sources_available"),
        "candidate_count": totals.get("records", 0),
        "display_state_totals": {key.removeprefix("display_"): value for key, value in totals.items() if key.startswith("display_")},
        "evidence_state_totals": {key.removeprefix("evidence_"): value for key, value in totals.items() if key.startswith("evidence_")},
        "privacy_review_count": totals.get("privacy_review_rows", 0),
        "coordinate_review_count": totals.get("coordinate_review_rows", 0),
        "suppressed_count": totals.get("suppressed_rows", 0),
        "per_source": per_source,
        "geocoding": "disabled; source coordinates remain pending review and missing coordinates remain unknown",
    }


def _graph_summary(repository_root: Path, private_root: Path) -> dict[str, Any]:
    fixture = repository_root / "pipeline" / "sources" / "us" / "accountability" / "fixtures" / "synthetic_link_ledger.csv"
    graph_root = private_root / "accountability"
    artifact = _fixture_artifact(
        fixture,
        source_url="https://www.fsis.usda.gov/inspection/establishments/meat-poultry-and-egg-product-inspection-directory",
        code_version="us-accountability-golden-rehearsal-v1",
        config_version="us-accountability-pilot-v1",
        coverage="Synthetic/sanitized FSIS and APHIS link-ledger fixture only; no national coverage claim",
        effective_date="2026-09-15",
    )
    manifest = UsAccountabilityAdapter(reference_date=date(2026, 9, 15)).run(fixture, graph_root, artifact)
    return {
        "input_kind": "synthetic/sanitized link-ledger fixture",
        "input_count": manifest.get("input_rows"),
        "accepted_candidate_count": manifest.get("relationship_rows"),
        "quarantine_count": manifest.get("quarantined_relationship_rows"),
        "quarantine_reasons": manifest.get("anomaly_counts", {}),
        "entity_count": manifest.get("entity_rows"),
        "relationship_types": manifest.get("relationship_types", {}),
        "source_local_identity_only": True,
        "cross_source_identity_joins_attempted": 0,
        "name_address_phone_coordinate_joins_attempted": 0,
        "auto_merge": False,
        "publication_status": manifest.get("publication_gate", "blocked"),
        "candidate_sha256": manifest.get("candidate_relationships_sha256"),
        "raw_candidates_private": True,
    }


def _assert_row_free(value: Any, path: str = "report") -> None:
    if isinstance(value, dict):
        leaked = FORBIDDEN_KEYS.intersection(value)
        if leaked:
            raise ValueError(f"row-bearing key in {path}: {sorted(leaked)}")
        for key, child in value.items():
            _assert_row_free(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _assert_row_free(child, f"{path}[{index}]")


def _run_rehearsal(repository_root: Path, private_root: Path) -> dict[str, Any]:
    private_root.mkdir(parents=True, exist_ok=True)
    fsis_directory = repository_root / "pipeline" / "sources" / "us" / "fsis" / "fixtures" / "valid.csv"
    fsis_demographics = repository_root / "pipeline" / "sources" / "us" / "fsis" / "fixtures" / "demographics.csv"
    aphis_fixtures = repository_root / "pipeline" / "sources" / "us" / "aphis" / "fixtures"

    fsis_root = private_root / "fsis"
    fsis_status = refresh_fsis(
        run_dir=fsis_root,
        directory_path=fsis_directory,
        demographics_path=fsis_demographics,
        retrieved_at_utc=AS_OF_UTC,
        effective_date=FIXTURE_EFFECTIVE_DATE,
        mode="handoff",
        max_age_days=3650,
    )
    fsis_status = _finalize_fsis_review(fsis_root, fsis_status)
    fsis_lifecycle = Path(fsis_status["run_dir"])
    fsis_handoff = fsis_lifecycle / "handoff" / "manifest.json"

    aphis_profiles = ("annual_reports", "registrations", "inspections")
    profile_statuses: dict[str, dict[str, Any]] = {}
    profile_summaries: list[dict[str, Any]] = []
    for profile in aphis_profiles:
        profile_root = private_root / f"aphis-{profile}"
        status = refresh_aphis(
            run_dir=profile_root,
            profile=profile,
            raw_path=aphis_fixtures / f"{profile}.csv",
            retrieved_at_utc=AS_OF_UTC,
            effective_date="2025" if profile == "annual_reports" else "2026-02-01",
            query_context={"selected_profile": profile, "fixture": True, "amended_reports_included": profile == "annual_reports"},
        )
        profile_statuses[profile] = status
        lifecycle = Path(status["run_dir"])
        handoff = lifecycle / "candidate-handoff" / "manifest.json"
        profile_summaries.append(
            _profile_summary(
                source_id="us.aphis",
                profile=profile,
                root=profile_root,
                status=status,
                identity_fields=("source_observation_key",),
                handoff=handoff,
            )
        )

    # Keep one deterministic malformed-row probe alongside (but outside) the
    # candidate set so the rehearsal proves that validation/quarantine is an
    # exercised path, not merely an untested field in a manifest.
    inspection_fixture = aphis_fixtures / "inspections.csv"
    inspection_lines = inspection_fixture.read_text(encoding="utf-8").splitlines()
    if len(inspection_lines) < 2:
        raise ValueError("APHIS inspection fixture needs a header and one data line")
    probe_path = private_root / "validation-probes" / "aphis-inspections-duplicate.csv"
    atomic_bytes(probe_path, ("\n".join([inspection_lines[0], inspection_lines[1], inspection_lines[1]]) + "\n").encode("utf-8"))
    probe_status = refresh_aphis(
        run_dir=private_root / "validation-probes" / "aphis-inspections",
        profile="inspections",
        raw_path=probe_path,
        retrieved_at_utc=AS_OF_UTC,
        effective_date="2026-02-01",
        query_context={"selected_profile": "inspections", "fixture": True, "probe": "duplicate-observation"},
    )
    probe_manifest = _read_json(Path(probe_status["run_dir"]) / "manifest.json")
    quarantine_probe = {
        "status": probe_status.get("status"),
        "input_count": probe_manifest.get("input_rows"),
        "normalized_count": probe_manifest.get("normalized_rows"),
        "quarantine_count": probe_manifest.get("quarantined_rows"),
        "quarantine_reasons": probe_manifest.get("anomaly_counts", {}),
        "candidate_included_in_release": False,
        "public_exposure": False,
    }

    fsis_summary = _profile_summary(
        source_id="us.fsis",
        profile="mpi-directory-plus-demographics",
        root=fsis_root,
        status=fsis_status,
        identity_fields=("establishment_id",),
        handoff=fsis_handoff,
    )
    source_summaries = [fsis_summary, *profile_summaries]

    candidate_entries = []
    geo_entries = []
    for summary in source_summaries:
        source_id = summary["source_id"]
        profile = summary["profile"]
        source_root = fsis_root if source_id == "us.fsis" else private_root / f"aphis-{profile}"
        lifecycle = Path((fsis_status if source_id == "us.fsis" else profile_statuses[profile])["run_dir"])
        handoff = lifecycle / ("handoff/manifest.json" if source_id == "us.fsis" else "candidate-handoff/manifest.json")
        lifecycle_manifest = lifecycle / "manifest.json"
        candidate_entries.append(
            {
                "source_id": source_id,
                "profile": profile,
                "status": "private-only",
                "normalized_count": summary["stages"]["normalized_count"],
                "quarantine_count": summary["stages"]["quarantine_count"],
                "candidate_handoff_manifest": str(handoff.relative_to(private_root)),
            }
        )
        geo_entries.append(
            {
                "source_id": source_id,
                "country_code": "US",
                "candidate_handoff_manifest": str(lifecycle_manifest.relative_to(private_root)),
                "normalized_count": summary["stages"]["normalized_count"],
            }
        )

    candidate_manifest = {
        "manifest_version": "us-private-candidate-rehearsal-v1",
        "country_code": "US",
        "input_kind": "sanitized fixtures only; current proof manifests are aggregate context",
        "sources": candidate_entries,
        "publication": {"release_created": False, "release_promoted": False, "project_approval": "not-approved"},
    }
    candidate_manifest_path = private_root / "candidate-manifest.json"
    atomic_json(candidate_manifest_path, candidate_manifest)
    preview_response = {
        "meta": {"test_only": True, "private_preview": True, "source_count": len(candidate_entries)},
        "publication": {"release_created": False, "public_api_count": 0},
    }
    frontend_report = rehearse_candidate(
        candidate_manifest_path,
        root=private_root,
        base_url="http://private-preview.invalid",
        token="fixture-token",
        request=lambda _base_url, _token: (200, preview_response),
    )

    geospatial = _geospatial_summary(private_root, geo_entries)
    graph = _graph_summary(repository_root, private_root)

    fsis_normalized = _jsonl(fsis_lifecycle / "normalized" / "records.jsonl")
    suppressed_key = record_key(fsis_normalized[0])
    suppression_status = run_private_lifecycle(
        fsis_directory,
        private_root / "suppression-replay",
        _fixture_artifact(
            fsis_directory,
            source_url="https://www.fsis.usda.gov/inspection/establishments/meat-poultry-and-egg-product-inspection-directory",
            code_version="us-fsis-candidate-v2",
            config_version="us-fsis-mpi-v1",
            coverage="Synthetic/sanitized FSIS directory fixture only; no currentness or completeness claim",
        ),
        FsisMpiAdapter(),
        suppressed_ids={suppressed_key},
        health_as_of_utc=AS_OF_UTC,
    )
    suppression_lifecycle = Path(suppression_status["run_dir"])
    suppression_candidate = suppression_lifecycle / "release-candidate" / "records.jsonl"
    suppression_lines = len(suppression_candidate.read_text(encoding="utf-8").splitlines()) if suppression_candidate.is_file() else 0
    suppression = {
        "status": suppression_status.get("status"),
        "input_count": suppression_status.get("manifest", {}).get("input_rows"),
        "suppressed_count": suppression_status.get("suppressed_count"),
        "candidate_count_after_suppression": suppression_lines,
        "public_exposure": False,
        "release_promoted": False,
        "reimport_reapplies_suppression": True,
    }

    fsis_rerun_root = private_root / "fsis-rerun"
    fsis_rerun_status = refresh_fsis(
        run_dir=fsis_rerun_root,
        directory_path=fsis_directory,
        demographics_path=fsis_demographics,
        retrieved_at_utc=AS_OF_UTC,
        effective_date=FIXTURE_EFFECTIVE_DATE,
        mode="handoff",
        max_age_days=3650,
    )
    rerun_manifest = _read_json(Path(fsis_rerun_status["run_dir"]) / "manifest.json")
    first_manifest = _read_json(fsis_lifecycle / "manifest.json")
    first_handoff = _read_json(fsis_handoff)
    rerun_handoff = _read_json(Path(fsis_rerun_status["run_dir"]) / "handoff" / "manifest.json")
    annual_handoff = Path(profile_statuses["annual_reports"]["run_dir"]) / "candidate-handoff"
    first_import = _read_json(annual_handoff / "manifest.json")
    second_import_root = private_root / "aphis-annual-reports-rerun-import"
    second_import = import_private_candidate(annual_handoff, second_import_root)
    rerun = {
        "fsis": {
            "same_artifact_sha256": first_manifest.get("sha256") == rerun_manifest.get("sha256"),
            "same_normalized_sha256": first_manifest.get("normalized_sha256") == rerun_manifest.get("normalized_sha256"),
            "same_counts": all(first_manifest.get(key) == rerun_manifest.get(key) for key in ("input_rows", "normalized_rows", "quarantined_rows")),
            "same_handoff_sha256": first_handoff.get("normalized_sha256") == rerun_handoff.get("normalized_sha256"),
            "public_exposure": False,
        },
        "aphis_private_import": {
            "same_handoff_sha256": first_import.get("normalized_sha256") == second_import.get("handoff_sha256"),
            "same_imported_count": first_import.get("normalized_rows") == second_import.get("imported_rows"),
            "database_import": second_import.get("database_import"),
            "public_exposure": second_import.get("public_exposure"),
        },
    }

    all_packets = [item["operator_artifacts"] for item in source_summaries]
    review_packet = {
        "source_packet_count": len(all_packets),
        "qa_packets_present": sum(int(item["qa"]) for item in all_packets),
        "health_snapshots_present": sum(int(item["health"]) for item in all_packets),
        "review_packets_present": sum(int(item["review_packet"]) for item in all_packets),
        "release_diffs_present": sum(int(item["release_diff"]) for item in all_packets),
        "row_payloads_included": False,
        "approval_effect": "none; operator packet is evidence for later human review",
    }

    report = {
        "report_version": REPORT_VERSION,
        "as_of_utc": AS_OF_UTC,
        "country_code": "US",
        "mechanical_contract_state": "passed",
        "outcome": {
            "private_rehearsal": "complete",
            "release_state": "not-created",
            "publication_gate": "blocked",
            "public_exposure": False,
            "human_approval": "not requested or performed",
            "national_completeness": "not assessed or claimed",
            "legacy_substitution": False,
        },
        "current_evidence_boundary": _current_evidence(repository_root),
        "source_profiles": source_summaries,
        "geospatial_readiness": geospatial,
        "accountability_graph": graph,
        "validation_quarantine_probe": quarantine_probe,
        "candidate_release": {
            "sources": len(candidate_entries),
            "normalized_candidate_count": sum(int(item["normalized_count"]) for item in candidate_entries),
            "quarantine_count": sum(int(item["quarantine_count"]) for item in candidate_entries),
            "release_created": False,
            "release_promoted": False,
            "public_api_count": 0,
            "public_map_count": 0,
            "public_export_count": 0,
            "project_approval": "not-approved",
        },
        "private_api_frontend": {
            "status": frontend_report["status"],
            "preview_probe": frontend_report["frontend_preview"]["state"],
            "test_only": frontend_report["frontend_preview"]["test_only"],
            "private_preview": frontend_report["frontend_preview"]["private_preview"],
            "raw_fields_absent": frontend_report["frontend_preview"]["raw_fields_absent"],
            "payloads_included": frontend_report["private_payloads_included"],
        },
        "suppression": suppression,
        "rerun_idempotency": rerun,
        "operator_review_packet": review_packet,
        "limitations_and_blockers": [
            "FSIS current direct CSV acquisition is blocked by the observed 403 route; the fixture handoff is not a current national facility capture.",
            "APHIS current proof is profile- and page-bounded, has failed captures and an inspection pagination boundary, and is not an animal-use census.",
            "State MPI/CIS rosters were not acquired in this rehearsal.",
            "Sanitized fixtures exercise contracts only; factual accuracy, privacy eligibility, project approval, and publication remain unassessed.",
            "Geocoding is disabled; source coordinates remain pending review and missing coordinates remain unknown.",
        ],
    }
    _assert_row_free(report)
    return report


def run(*, repository_root: str | Path, output: str | Path, private_dir: str | Path | None = None) -> dict[str, Any]:
    """Run the rehearsal and write only the aggregate report to ``output``."""
    repository = Path(repository_root).resolve()
    output_path = Path(output)
    if private_dir is not None:
        report = _run_rehearsal(repository, Path(private_dir))
    else:
        with tempfile.TemporaryDirectory(prefix="uec-us-private-golden-") as directory:
            report = _run_rehearsal(repository, Path(directory))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_json(output_path, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."), help="repository root")
    parser.add_argument("--output", type=Path, required=True, help="tracked row-free output manifest")
    parser.add_argument("--private-dir", type=Path, help="ignored directory for row-bearing private artifacts")
    args = parser.parse_args()
    report = run(repository_root=args.root, output=args.output, private_dir=args.private_dir)
    print(json.dumps({
        "output": str(args.output),
        "mechanical_contract_state": report["mechanical_contract_state"],
        "release_state": report["outcome"]["release_state"],
        "public_exposure": report["outcome"]["public_exposure"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
