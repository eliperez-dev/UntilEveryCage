"""Run the US accountability link ledger through private candidate staging."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from pipeline.common.acquisition import utc_now
from pipeline.contracts.adapter_contract import SourceArtifact
from pipeline.contracts.source_lifecycle import atomic_json

from .adapter import CONFIG, UsAccountabilityAdapter


def assisted_capture_contract() -> dict:
    return {
        "source_id": CONFIG["source_id"],
        "method": "operator-assisted-source-link-ledger",
        "steps": [
            "Acquire FSIS and APHIS exports only through their source-local assisted contracts.",
            "Record source-native IDs and dates for each candidate endpoint; do not copy raw rows into Git.",
            "Add a legal-entity, parent, brand, SEC, EPA, OSHA, or other government link only when a reviewer records an explicit source-native identifier and reuse/terms decision.",
            "Run this ledger adapter with private staging, then inspect the row-free review packet before any disposable candidate import.",
        ],
        "controls": [
            "No fuzzy name, address, phone, geocoder, or access-control bypass",
            "Ownership changes are temporal events; overlapping contradictory links quarantine",
            "Suppressed/restricted links never enter candidate JSONL",
            "No graph migration, release promotion, public API, map, export, or UI",
        ],
        "source_routes": {
            "fsis": "https://www.fsis.usda.gov/inspection/establishments/meat-poultry-and-egg-product-inspection-directory",
            "aphis": "https://www.aphis.usda.gov/animal-care/awa-services/usda-animal-care-public-search-tool",
            "sec": "deferred until source-specific terms and exact CIK evidence are reviewed",
            "epa_osha": "deferred; no link is emitted without a source-native identifier and reuse decision",
        },
    }


def refresh(*, raw_path: str | Path, run_dir: str | Path, retrieved_at_utc: str | None = None, effective_date: str | None = None) -> dict:
    raw = Path(raw_path).read_bytes()
    retrieved = retrieved_at_utc or utc_now()
    adapter = UsAccountabilityAdapter()
    artifact = SourceArtifact(
        source_url=CONFIG["source_url"], retrieved_at_utc=retrieved,
        sha256=hashlib.sha256(raw).hexdigest(), byte_size=len(raw),
        effective_date=effective_date or "unknown", code_version=adapter.adapter_version,
        config_version=adapter.schema_version,
        rights_caveat="Link-ledger source rights and attribution require per-source review before any reuse",
        privacy_caveat="Private test-only candidate; identity, address, phone, and coordinate review pending",
        coverage="Bounded explicit-link pilot; no national completeness claim",
    )
    root = Path(run_dir)
    metadata = {
        "acquisition_method": "assisted_local_capture",
        "source_id": CONFIG["source_id"],
        "artifact": Path(raw_path).name,
        "artifact_path": str(Path(raw_path).resolve()),
        "requested_url": CONFIG["source_url"],
        "final_url": CONFIG["source_url"],
        "retrieved_at_utc": retrieved,
        "effective_date": effective_date or "unknown",
        "sha256": artifact.sha256,
        "byte_size": artifact.byte_size,
        "code_version": adapter.adapter_version,
        "config_version": adapter.schema_version,
        "retention": {"class": "restricted-research-evidence", "public_exposure": False, "review_required": True},
    }
    atomic_json(root / "acquisition-metadata.json", metadata)
    manifest = adapter.run(raw_path, root, artifact)
    contract = assisted_capture_contract()
    atomic_json(root / "assisted-capture-contract.json", contract)
    packet = {
        "schema_version": "us-accountability-review-packet-v1",
        "source_id": CONFIG["source_id"],
        "purpose": "Human review aid for a private, synthetic/test-only graph-candidate pilot; not release approval",
        "what_the_pilot_proves": [
            "A facility, its FSIS establishment approval, an operator, a legal entity, a parent, and a brand can remain distinct typed candidates.",
            "APHIS registration/inspection, violation, enforcement, laboratory, and aggregate observations can remain separate evidence objects.",
            "Every accepted relationship carries source IDs, observation/retrieval dates, relationship type, confidence/review state, and evidence.",
            "Ambiguous, stale, conflicting, or suppressed relationships are quarantined deterministically.",
        ],
        "what_remains_inference": [
            "No name, address, phone, geocoder, or fuzzy match establishes identity.",
            "The checked-in SEC identifiers and all row values are synthetic; they do not assert a live SEC, EPA, OSHA, FSIS, or APHIS match.",
            "An explicit reviewed link is a candidate relationship, not a statement that the project has approved publication or legal ownership.",
            "Source disappearance is not closure, and an inspection or aggregate is not a facility-master assertion.",
        ],
        "source_rights_and_acquisition": {
            "fsis": "Use the existing operator-assisted official export contract; direct 403 responses remain fail-closed and are never bypassed.",
            "aphis": "Use the existing profile-explicit public-search assisted export; registrations, inspections, annual reports, laboratories, and aggregates remain separate.",
            "sec_epa_osha": "Deferred until a source-specific terms/reuse decision and defensible source-native identifier evidence are retained with the run.",
        },
        "coverage": "Synthetic/sanitized fixture only; no national completeness, currentness, or publication claim",
        "scaling_cost": {
            "per_relationship": "one explicit source-native link review plus provenance/evidence storage",
            "per_refresh": "source acquisition, schema/count review, identity conflict scan, stale scan, quarantine review, and deterministic artifact hashing",
            "unbounded_work_not_included": "bulk fuzzy entity resolution, residential exposure, target scoring, public publication, UI, or graph migration",
        },
        "counts": {
            "input_rows": manifest["input_rows"],
            "relationships": manifest["relationship_rows"],
            "entities": manifest["entity_rows"],
            "quarantined_relationships": manifest["quarantined_relationship_rows"],
        },
        "gates": {
            "test_only": True,
            "release_state": "not-created",
            "publication_state": "private-candidate",
            "publication_gate": "blocked",
            "graph_migration": False,
            "geocoding": "disabled",
        },
        "row_payloads_included": False,
    }
    atomic_json(root / "review-packet.json", packet)
    status = {
        "status": "candidate-ready" if manifest["normalized_rows"] else "quarantine-only",
        "run_dir": str(root),
        "source_id": CONFIG["source_id"],
        "release_state": "not-created",
        "publication_state": "private-candidate",
        "publication_gate": "blocked",
        "test_only": True,
    }
    atomic_json(root / "run-status.json", status)
    return {"manifest": manifest, "status": status}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--retrieved-at-utc")
    parser.add_argument("--effective-date")
    args = parser.parse_args()
    try:
        result = refresh(raw_path=args.raw, run_dir=args.run_dir, retrieved_at_utc=args.retrieved_at_utc, effective_date=args.effective_date)
    except (OSError, ValueError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps({"status": result["status"]["status"], "run_dir": result["status"]["run_dir"]}, sort_keys=True))
    return 0 if result["status"]["status"] == "candidate-ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
