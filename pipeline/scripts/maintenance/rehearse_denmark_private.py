"""Build a deterministic, row-free report for a Denmark private rehearsal.

The source runner owns acquisition and staging.  This command only checks the
resulting private artifacts, compares a rerun, and exercises the separate
candidate-preview contract with an in-memory test-only response.  It never
imports a release, starts a server, or emits source rows.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.scripts.maintenance.rehearse_candidate_private_frontend import rehearse_candidate


REPORT_VERSION = "denmark-private-golden-rehearsal-v1"
FORBIDDEN_KEYS = frozenset({
    "source_values", "raw_fields", "address", "street", "latitude", "longitude",
    "coordinates", "records", "rows", "geocoder_query", "geocoder_response",
})


class RehearsalError(ValueError):
    """Private rehearsal evidence is incomplete or violates a boundary."""


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RehearsalError(f"invalid JSON artifact: {path}") from error
    if not isinstance(value, dict):
        raise RehearsalError(f"JSON artifact is not an object: {path}")
    return value


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _jsonl_count(path: Path) -> int:
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def _assert_row_free(value: Any, path: str = "report") -> None:
    if isinstance(value, dict):
        leaked = sorted(FORBIDDEN_KEYS.intersection(value))
        if leaked:
            raise RehearsalError(f"row-bearing key leaked at {path}: {leaked}")
        for key, child in value.items():
            _assert_row_free(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _assert_row_free(child, f"{path}[{index}]")


def _contract_request(_base_url: str, _token: str) -> tuple[int, dict[str, Any]]:
    """Return a safe synthetic preview response for the contract-only check."""
    return 200, {"meta": {"test_only": True, "private_preview": True}, "data": []}


def _build_preview_contract(run_dir: Path, candidate_rows: int) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="uec-denmark-preview-") as directory:
        manifest_path = Path(directory) / "candidate.json"
        manifest_path.write_text(json.dumps({
            "publication": {"release_created": False, "release_promoted": False, "project_approval": "not-approved"},
            "sources": [{
                "source_id": "dk.smiley",
                "candidate_handoff_manifest": str(run_dir / "candidate-handoff" / "manifest.json"),
                "normalized_rows": candidate_rows,
                "status": "private-only",
            }],
        }), encoding="utf-8")
        result = rehearse_candidate(
            manifest_path,
            root=run_dir,
            base_url="http://127.0.0.1",
            token="in-memory-contract-token",
            request=_contract_request,
        )
    return {
        "status": result["status"],
        "mode": "in-memory-contract-only",
        "test_only": result["frontend_preview"]["test_only"],
        "private_preview": result["frontend_preview"]["private_preview"],
        "raw_fields_absent": result["frontend_preview"]["raw_fields_absent"],
        "publication_boundary": result["publication_boundary"],
    }


def build_report(
    run_dir: str | Path,
    *,
    rerun_dir: str | Path | None = None,
    network_acquisition_status: str = "not-run",
    api_status: str = "not-run",
    suppression_status: str = "not-run",
) -> dict[str, Any]:
    root = Path(run_dir)
    manifest = _read(root / "manifest.json")
    qa = _read(root / "qa.json")
    status = _read(root / "run-status.json")
    queue = _read(root / "05-geocode-queue" / "geocode-queue-metadata.json")
    handoff = _read(root / "candidate-handoff" / "manifest.json")
    graph = _read(root / "graph" / "graph-candidates-manifest.json")
    review = _read(root / "review-packet.json")

    if manifest.get("source_id") != "dk.smiley":
        raise RehearsalError("run is not the Denmark Smiley source")
    if manifest.get("release_state") != "not-created" or manifest.get("publication_state") != "private-candidate":
        raise RehearsalError("private run has an unsafe release/publication state")
    if status.get("release_promoted") is not False or any(status.get("public_surfaces", {}).values()):
        raise RehearsalError("private run reports a promoted release or public surface")
    if manifest["input_rows"] != manifest["normalized_rows"] + manifest["quarantined_rows"]:
        raise RehearsalError("private manifest row counts do not reconcile")
    normalized_path = root / "normalized" / "records.jsonl"
    quarantined_path = root / "quarantined" / "records.jsonl"
    if _jsonl_count(normalized_path) != manifest["normalized_rows"] or _jsonl_count(quarantined_path) != manifest["quarantined_rows"]:
        raise RehearsalError("normalized/quarantine artifacts do not match the manifest")
    if handoff.get("release_state") != "not-created" or handoff.get("publication_state") != "private-candidate":
        raise RehearsalError("candidate handoff is not private and unpromoted")
    if handoff.get("normalized_rows") != manifest["normalized_rows"]:
        raise RehearsalError("candidate handoff count differs from accepted private rows")
    if graph.get("publication_status") != "not_eligible" or graph.get("storage_state") != "private":
        raise RehearsalError("graph candidate handoff is not private and review-required")
    if queue.get("records_seen") != manifest["normalized_rows"]:
        raise RehearsalError("geocode queue includes quarantined rows")
    if queue["records_seen"] != queue["records_queued"] + queue["records_with_source_coordinates"] + queue["records_without_usable_address"]:
        raise RehearsalError("geocode queue counts do not reconcile")
    if review.get("counts", {}).get("reconciles") is not True or review.get("publication_boundary") != "awaiting-owner-review; this packet is row-free evidence and cannot approve or promote a release":
        raise RehearsalError("operator review packet is incomplete")

    rerun = {"status": "not-run", "deterministic_artifacts": False, "new_rows": None}
    if rerun_dir is not None:
        other = Path(rerun_dir)
        comparisons = {
            "parsed": _sha(root / "01-parse" / "parsed-rows.jsonl") == _sha(other / "01-parse" / "parsed-rows.jsonl"),
            "normalized": _sha(normalized_path) == _sha(other / "normalized" / "records.jsonl"),
            "quarantine": _sha(quarantined_path) == _sha(other / "quarantined" / "records.jsonl"),
            "candidate_handoff": _sha(root / "candidate-handoff" / "normalized" / "records.jsonl") == _sha(other / "candidate-handoff" / "normalized" / "records.jsonl"),
            "graph": _sha(root / "graph" / "graph-candidates.jsonl") == _sha(other / "graph" / "graph-candidates.jsonl"),
            "geocode_queue": _sha(root / "05-geocode-queue" / "geocode-queue.jsonl") == _sha(other / "05-geocode-queue" / "geocode-queue.jsonl"),
        }
        rerun = {"status": "passed" if all(comparisons.values()) else "failed", "deterministic_artifacts": all(comparisons.values()), "new_rows": 0, "artifact_comparisons": comparisons}

    report = {
        "report_version": REPORT_VERSION,
        "status": "passed-private-staging",
        "fail_closed": True,
        "source": {
            "source_id": "dk.smiley",
            "source_url": manifest.get("source_url"),
            "retrieved_at_utc": manifest.get("retrieved_at_utc"),
            "effective_date": manifest.get("effective_date"),
            "sha256": manifest.get("sha256"),
            "byte_size": manifest.get("byte_size"),
            "acquisition_method": (manifest.get("acquisition") or {}).get("acquisition_method"),
            "terms_gate": "local preserved artifact; network terms approval not asserted",
        },
        "stages": {
            "parse_normalize_validate": "passed",
            "input_rows": manifest["input_rows"],
            "accepted_normalized_rows": manifest["normalized_rows"],
            "quarantined_rows": manifest["quarantined_rows"],
            "validation_finding_rows": manifest.get("validation_finding_rows"),
            "quarantine_reasons": manifest.get("anomaly_counts", {}),
        },
        "identity": {
            "source_scoped_identity": "passed",
            "candidate_facility_identifiers": graph.get("facility_identifier_candidates"),
            "candidate_organization_identifiers": graph.get("organization_identifier_candidates"),
            "operator_relationship_candidates": graph.get("operator_relationship_candidates"),
            "canonical_cross_source_merge": False,
        },
        "geocoding": {
            "source_coordinate_states": review.get("geospatial", {}).get("coordinate_state_counts", {}),
            "source_coordinates_queued": queue.get("records_with_source_coordinates"),
            "address_queue_rows": queue.get("records_queued"),
            "external_requests_made": False,
            "state": "pending-review; no geocoder calls",
        },
        "candidate_release": {
            "handoff_rows": handoff.get("normalized_rows"),
            "release_created": False,
            "release_promoted": False,
            "public_rows": 0,
            "publication_state": "private-candidate; human-gate-required",
        },
        "private_api_frontend": {
            "status": api_status,
            "contract": _build_preview_contract(root, manifest["normalized_rows"]),
            "public_api_rows": 0,
        },
        "suppression_restore": {
            "status": suppression_status,
            "required_behavior": "append-only suppression must cover list, detail, map, facets, export, history, reimport, restore, and geocode renewal",
        },
        "rerun": rerun,
        "operator_review": {
            "packet": "row-free",
            "release_state": review.get("gates", {}).get("release_state"),
            "owner_review": (review.get("platform") or {}).get("owner_review", {}).get("state"),
            "publication_boundary": review.get("publication_boundary"),
        },
        "acquisition_network_status": network_acquisition_status,
        "limitations": [
            "The checked-in Smiley XML is a retained local artifact, not a fresh network acquisition; its source/effective date is not independently re-established by this rehearsal.",
            "The source publisher supplies no dataset effective date; row-count drift against the prior expected count remains a review finding.",
            "Private API, suppression, and restoration statuses are caller-supplied observations; this command never starts or connects to a server.",
            "No source rows, addresses, coordinates, geocoder responses, or raw payloads are included in this report.",
        ],
        "private_payloads_included": False,
    }
    _assert_row_free(report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--rerun-dir", type=Path)
    parser.add_argument("--network-acquisition-status", default="not-run")
    parser.add_argument("--api-status", default="not-run")
    parser.add_argument("--suppression-status", default="not-run")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = build_report(
            args.run_dir,
            rerun_dir=args.rerun_dir,
            network_acquisition_status=args.network_acquisition_status,
            api_status=args.api_status,
            suppression_status=args.suppression_status,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"output": str(args.output), "status": report["status"], "rerun": report["rerun"]["status"]}, sort_keys=True))
        return 0
    except Exception as error:
        failure = {"report_version": REPORT_VERSION, "status": "blocked", "fail_closed": True, "blocker": str(error), "private_payloads_included": False}
        _assert_row_free(failure)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(failure, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"output": str(args.output), "status": "blocked", "blocker": str(error)}, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
