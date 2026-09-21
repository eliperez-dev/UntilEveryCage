"""Private, row-free rehearsal of the real legacy US USDA snapshots.

The checked-in files are V1-derived legacy snapshots, not current raw source
captures. This module uses them only to exercise the V2 adapters and the
accountability graph contract. It creates a private link ledger from explicit
source-local identifiers and dated source fields; it never joins FSIS to APHIS
by name, address, phone, coordinates, or proximity.
"""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from pipeline.sources.us.accountability.adapter import REQUIRED_HEADERS


FSIS_ROUTE = "https://www.fsis.usda.gov/sites/default/files/media_file/documents/MPI_Directory_by_Establishment_Number.csv"
APHIS_ROUTE = "https://www.aphis.usda.gov/animal-care/awa-services/usda-animal-care-public-search-tool"
CURRENT_PAGE = "https://www.fsis.usda.gov/inspection/establishments/meat-poultry-and-egg-product-inspection-directory"
LEGACY_AS_OF = "2026-09-17T00:00:00Z"


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _date(value: str, *, year_end: bool = False) -> str:
    text = _clean(value)
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass
    if year_end and len(text) == 4 and text.isdigit():
        return f"{text}-12-31"
    return ""


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _row_fingerprint(namespace: str, row: dict[str, str]) -> str:
    material = "\0".join((namespace, *(f"{key}={row.get(key, '')}" for key in sorted(row))))
    return hashlib.sha256(material.encode("utf-8", "surrogateescape")).hexdigest()


def _base(*, subject_type: str, subject_id: str, subject_name: str,
          object_type: str, object_id: str, object_name: str,
          relationship_type: str, evidence_source_id: str,
          evidence_native_id: str, observation_date: str,
          evidence_url: str, excerpt: str, profile: str) -> dict[str, str]:
    return {
        "subject_type": subject_type,
        "subject_source_id": evidence_source_id,
        "subject_source_native_id": subject_id,
        "subject_name": subject_name,
        "object_type": object_type,
        "object_source_id": evidence_source_id,
        "object_source_native_id": object_id,
        "object_name": object_name,
        "relationship_type": relationship_type,
        "evidence_source_id": evidence_source_id,
        "evidence_source_native_id": evidence_native_id,
        "observation_date": observation_date,
        "retrieved_at_utc": LEGACY_AS_OF,
        "valid_from": "",
        "valid_to": "",
        "confidence": "high" if relationship_type in {"establishment_approval_for", "regulatory_authority_for"} else "medium",
        "review_state": "review_required",
        "match_method": "exact_source_id",
        "evidence_url": evidence_url,
        "evidence_excerpt": excerpt,
        "suppression_state": "eligible",
        "evidence_profile": profile,
    }


def build_ledger_rows(fsis_rows: Iterable[dict[str, str]], inspection_rows: Iterable[dict[str, str]], annual_rows: Iterable[dict[str, str]]) -> tuple[list[dict[str, str]], dict[str, int]]:
    """Build explicit, source-local graph assertions from legacy rows."""
    rows: list[dict[str, str]] = []
    skipped = Counter()

    for row in fsis_rows:
        facility_id = _clean(row.get("establishment_id"))
        approval_id = _clean(row.get("establishment_number"))
        observed = _date(row.get("grant_date", ""))
        name = _clean(row.get("establishment_name"))
        if not facility_id or not approval_id or not name:
            skipped["fsis_missing_explicit_identity"] += 1
            continue
        if not observed:
            skipped["fsis_missing_observation_date"] += 1
            continue
        evidence_id = f"legacy-row:{facility_id}"
        excerpt = "FSIS legacy V1 snapshot row retains an establishment ID and establishment number; currentness and publication remain unverified."
        rows.append(_base(subject_type="establishment_approval", subject_id=f"approval:{approval_id}", subject_name=f"FSIS establishment approval {approval_id}", object_type="facility", object_id=facility_id, object_name=name, relationship_type="establishment_approval_for", evidence_source_id="us.fsis", evidence_native_id=evidence_id, observation_date=observed, evidence_url=FSIS_ROUTE, excerpt=excerpt, profile="legacy-fsis-locations"))
        rows.append(_base(subject_type="legal_entity", subject_id="authority:fsis", subject_name="USDA Food Safety and Inspection Service", object_type="facility", object_id=facility_id, object_name=name, relationship_type="regulatory_authority_for", evidence_source_id="us.fsis", evidence_native_id=evidence_id, observation_date=observed, evidence_url=CURRENT_PAGE, excerpt="The FSIS MPI Directory describes this source population as FSIS-regulated establishments; this is a source-scope assertion, not project approval.", profile="legacy-fsis-locations"))

    for row in inspection_rows:
        customer = _clean(row.get("Customer Number"))
        certificate = _clean(row.get("Certificate Number"))
        name = _clean(row.get("Account Name"))
        observed = _date(row.get("Status Date", ""))
        if not customer or not certificate or not name:
            skipped["aphis_inspections_missing_explicit_identity"] += 1
            continue
        if not observed:
            skipped["aphis_inspections_missing_observation_date"] += 1
            continue
        operator_id = f"operator:customer:{customer}"
        inspection_id = f"inspection:certificate:{certificate}:{observed}"
        evidence_id = f"legacy-row:{certificate}:{customer}"
        rows.append(_base(subject_type="inspection", subject_id=inspection_id, subject_name=f"APHIS inspection {certificate}", object_type="operator", object_id=operator_id, object_name=name, relationship_type="inspection_observes", evidence_source_id="us.aphis", evidence_native_id=evidence_id, observation_date=observed, evidence_url=APHIS_ROUTE, excerpt="APHIS legacy inspection snapshot retains certificate and customer identifiers in the same source row; it is not an FSIS facility assertion.", profile="legacy-aphis-inspections"))
        rows.append(_base(subject_type="legal_entity", subject_id="authority:aphis-animal-care", subject_name="USDA APHIS Animal Care", object_type="operator", object_id=operator_id, object_name=name, relationship_type="regulatory_authority_for", evidence_source_id="us.aphis", evidence_native_id=evidence_id, observation_date=observed, evidence_url=APHIS_ROUTE, excerpt="APHIS Animal Care public-search evidence is retained as a separate regulatory observation; no facility merge is inferred.", profile="legacy-aphis-inspections"))

    for row in annual_rows:
        customer = _clean(row.get("Customer Number_y")) or _clean(row.get("Customer Number_x"))
        certificate = _clean(row.get("Certificate Number"))
        name = _clean(row.get("Account Name"))
        observed = _date(row.get("Year", ""), year_end=True)
        if not customer or not certificate or not name:
            skipped["aphis_annual_reports_missing_explicit_identity"] += 1
            continue
        if not observed:
            skipped["aphis_annual_reports_missing_observation_date"] += 1
            continue
        operator_id = f"operator:customer:{customer}"
        aggregate_id = f"annual-report:{certificate}:{observed[:4]}"
        evidence_id = f"legacy-row:{certificate}:{customer}:{observed[:4]}"
        rows.append(_base(subject_type="aggregate_observation", subject_id=aggregate_id, subject_name=f"APHIS annual report {certificate} {observed[:4]}", object_type="operator", object_id=operator_id, object_name=name, relationship_type="aggregate_describes", evidence_source_id="us.aphis", evidence_native_id=evidence_id, observation_date=observed, evidence_url=APHIS_ROUTE, excerpt="APHIS annual-report snapshot is retained as an aggregate observation and does not establish an FSIS facility or laboratory identity.", profile="legacy-aphis-annual-reports"))
        rows.append(_base(subject_type="legal_entity", subject_id="authority:aphis-animal-care", subject_name="USDA APHIS Animal Care", object_type="operator", object_id=operator_id, object_name=name, relationship_type="regulatory_authority_for", evidence_source_id="us.aphis", evidence_native_id=evidence_id, observation_date=observed, evidence_url=APHIS_ROUTE, excerpt="APHIS annual-report evidence remains a separate source family under the Animal Care authority; amended reports and currentness require review.", profile="legacy-aphis-annual-reports"))

    return rows, dict(sorted(skipped.items()))


def write_ledger(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=REQUIRED_HEADERS, lineterminator="\n")
        writer.writeheader()
        writer.writerows([{key: row.get(key, "") for key in REQUIRED_HEADERS} for row in rows])


def row_free_metrics(*, fsis_path: Path, inspection_path: Path, annual_path: Path, ledger_rows: list[dict[str, str]], skipped: dict[str, int]) -> dict[str, Any]:
    source_rows = {"fsis_locations": _read(fsis_path), "aphis_inspections": _read(inspection_path), "aphis_annual_reports": _read(annual_path)}
    relationships = Counter(row["relationship_type"] for row in ledger_rows)
    profiles = Counter(row["evidence_profile"] for row in ledger_rows)
    dated = Counter(row["evidence_profile"] for row in ledger_rows if row.get("observation_date"))
    return {
        "schema_version": "us-real-legacy-graph-rehearsal-v1",
        "corpus_state": "private-regression-only",
        "input_kind": "existing-v1-derived-snapshot; not current raw acquisition",
        "publication_eligibility": "blocked",
        "source_boundaries": {
            "fsis": {"jurisdiction": "federal", "input_rows": len(source_rows["fsis_locations"]), "source_url": FSIS_ROUTE, "state_inspection_programs": "excluded"},
            "aphis_inspections": {"jurisdiction": "federal", "input_rows": len(source_rows["aphis_inspections"]), "source_url": APHIS_ROUTE, "evidence_family": "inspection observations; no FSIS facility merge"},
            "aphis_annual_reports": {"jurisdiction": "federal", "input_rows": len(source_rows["aphis_annual_reports"]), "source_url": APHIS_ROUTE, "evidence_family": "annual aggregate observations; may be amended"},
            "state_programs": {"included": False, "reason": "no state inspection source was supplied or inferred"},
        },
        "strata": {name: len(rows) for name, rows in source_rows.items()},
        "graph": {
            "ledger_input_rows": len(ledger_rows),
            "relationship_counts": dict(sorted(relationships.items())),
            "profile_counts": dict(sorted(profiles.items())),
            "dated_relationship_counts": dict(sorted(dated.items())),
            "cross_source_identity_joins_attempted": 0,
            "name_address_phone_coordinate_joins_attempted": 0,
            "candidate_rule": "exact source-native IDs in the same legacy source row only",
            "all_candidates": {"review_state": "review_required", "publication_gate": "blocked", "auto_merge": False, "geocoding": "disabled"},
        },
        "quality": {
            "skipped_or_quarantined_before_ledger": skipped,
            "input_rows_reconciled_to_source_local_graph_or_skip": (
                sum(1 for row in ledger_rows if row.get("evidence_profile") == "legacy-fsis-locations") // 2
                + skipped.get("fsis_missing_explicit_identity", 0)
                + skipped.get("fsis_missing_observation_date", 0) == len(source_rows["fsis_locations"])
                and sum(1 for row in ledger_rows if row.get("evidence_profile") == "legacy-aphis-inspections") // 2
                + skipped.get("aphis_inspections_missing_explicit_identity", 0)
                + skipped.get("aphis_inspections_missing_observation_date", 0) == len(source_rows["aphis_inspections"])
                and sum(1 for row in ledger_rows if row.get("evidence_profile") == "legacy-aphis-annual-reports") // 2
                + skipped.get("aphis_annual_reports_missing_explicit_identity", 0)
                + skipped.get("aphis_annual_reports_missing_observation_date", 0) == len(source_rows["aphis_annual_reports"])
            ),
            "accuracy": "not measured; no adjudicated real labels available",
        },
        "privacy_and_provenance": {
            "raw_values": "private adapter output only; not included in report",
            "coordinates": "not used for identity; geocoding disabled",
            "source_hashes": {key: hashlib.sha256(path.read_bytes()).hexdigest() for key, path in (("fsis_locations", fsis_path), ("aphis_inspections", inspection_path), ("aphis_annual_reports", annual_path))},
        },
        "limitations": [
            "The legacy V1 snapshots are not current raw FSIS or APHIS captures and are not represented as current evidence.",
            "The current FSIS page was observed in a browser with a Sep 14, 2026 update, but exact CSV downloads returned 403 outside that session; no current raw artifact is claimed.",
            "Graph yield is a candidate count, not accuracy, ownership truth, facility operation, or publication permission.",
            "A source disappearance is not closure; state inspection programs remain outside this federal-only rehearsal.",
        ],
    }
