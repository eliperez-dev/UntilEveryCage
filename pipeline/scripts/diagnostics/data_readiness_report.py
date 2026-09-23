"""Build the D1 row-free data-readiness report.

The report is intentionally an aggregate contract, not a source-row export.
It keeps observations, candidate identities, coordinate/display states,
quarantine, and human gates separate.  In particular, a source observation is
never silently renamed to a facility.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping


REPORT_VERSION = "d1-data-readiness-v1"
PUBLICATION_BLOCKED = "blocked"

_FORBIDDEN_KEYS = frozenset(
    {
        "records",
        "rows",
        "source_values",
        "raw_fields",
        "address",
        "street",
        "latitude",
        "longitude",
        "coordinates",
        "geocoder_query",
        "geocoder_response",
        "private_path",
        "private_root",
    }
)


class DataReadinessError(ValueError):
    """The row-free readiness input is incomplete or inconsistent."""


def _int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise DataReadinessError(f"{field} must be a non-negative integer")
    return value


def _required(mapping: Mapping[str, Any], field: str) -> Any:
    if field not in mapping:
        raise DataReadinessError(f"missing aggregate field: {field}")
    return mapping[field]


def _safe(value: Any, path: str = "report") -> None:
    """Reject payload-shaped keys before a report can be written."""
    if isinstance(value, Mapping):
        leaked = sorted(_FORBIDDEN_KEYS.intersection(value))
        if leaked:
            raise DataReadinessError(f"row/private payload key in {path}: {leaked}")
        for key, child in value.items():
            _safe(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _safe(child, f"{path}[{index}]")


def _source(source: Mapping[str, Any], required: tuple[str, ...]) -> dict[str, Any]:
    result = dict(source)
    for field in required:
        _int(_required(source, field), field)
    return result


def build_report(
    *,
    fsis: Mapping[str, Any],
    italy: Mapping[str, Any],
    france: Mapping[str, Any],
    denmark: Mapping[str, Any],
    as_of_utc: str = "2026-09-21T00:00:00Z",
) -> dict[str, Any]:
    """Build and validate the approved D1 aggregate contract.

    Inputs are row-free metrics obtained from restricted acquisition/review
    packets.  This function does not read private roots or attempt geocoding.
    """
    fsis = _source(fsis, ("candidate_count", "numeric_coordinate_count", "city_geocode_count"))
    italy = _source(
        italy,
        (
            "observation_count",
            "provisional_identity_count",
            "numeric_coordinate_count",
            "city_only_count",
            "rejected_zero_coordinate_count",
        ),
    )
    france = _source(
        france,
        (
            "section_i_count",
            "section_ii_count",
            "union_candidate_count",
            "numeric_coordinate_count",
            "city_postal_count",
        ),
    )
    denmark = _source(denmark, ("observation_count", "validation_finding_count", "legacy_v1_count"))

    if fsis["candidate_count"] != 7241 or fsis["numeric_coordinate_count"] != 7241:
        raise DataReadinessError("FSIS aggregate must contain 7,241 candidates and numeric coordinates")
    if fsis["city_geocode_count"] != 0:
        raise DataReadinessError("FSIS city-geocode count must remain zero")
    if italy["observation_count"] != 41849 or italy["provisional_identity_count"] != 25316:
        raise DataReadinessError("Italy observation/provisional identity totals changed")
    if (italy["numeric_coordinate_count"], italy["city_only_count"], italy["rejected_zero_coordinate_count"]) != (24263, 1053, 486):
        raise DataReadinessError("Italy coordinate-state totals changed")
    if france["section_i_count"] != 1449 or france["section_ii_count"] != 1068:
        raise DataReadinessError("France section totals changed")
    if france["union_candidate_count"] != 2283 or france["numeric_coordinate_count"] != 0:
        raise DataReadinessError("France union/coordinate totals changed")
    if france["city_postal_count"] != 2283:
        raise DataReadinessError("France city/postal candidate total changed")
    if denmark["observation_count"] != 58766 or denmark["validation_finding_count"] != 57:
        raise DataReadinessError("Denmark retained-evidence totals changed")
    if denmark["legacy_v1_count"] != 1561:
        raise DataReadinessError("Denmark legacy V1 comparison total changed")

    candidate_total = (
        fsis["candidate_count"]
        + italy["provisional_identity_count"]
        + france["union_candidate_count"]
    )
    numeric_total = (
        fsis["numeric_coordinate_count"]
        + italy["numeric_coordinate_count"]
        + france["numeric_coordinate_count"]
    )
    city_total = fsis["city_geocode_count"] + italy["city_only_count"] + france["city_postal_count"]
    if (candidate_total, numeric_total, city_total) != (34840, 31504, 3336):
        raise DataReadinessError("D1 total arithmetic does not reconcile")

    report: dict[str, Any] = {
        "schema_version": REPORT_VERSION,
        "as_of_utc": as_of_utc,
        "corpus_state": "row-free-real-data-shaped-private-readiness",
        "evidence": {
            "us.fsis": {
                "basis": "official aggregate observation plus restricted candidate metrics",
                "current_row_artifact": "not captured; direct routes blocked",
                "row_payloads_included": False,
            },
            "it.853-2004": {
                "basis": "restricted row-free QA aggregate",
                "row_payloads_included": False,
            },
            "fr.dgal.union": {
                "basis": "row-free cross-section reconciliation; 233 overlap signals remain review-only",
                "row_payloads_included": False,
            },
            "dk.smiley": {
                "basis": "retained private run aggregate and source-key identity contract",
                "facility_identity_claim": "not established",
                "row_payloads_included": False,
            },
        },
        "publication": {
            "release_created": False,
            "release_promoted": False,
            "public_api_rows": 0,
            "publication_eligibility": PUBLICATION_BLOCKED,
            "project_approval": "not-recorded",
        },
        "observations": {
            "fsis": {
                "source_id": "us.fsis",
                "observation_unit": "source candidate aggregate; not a checked-in row corpus",
                "count": fsis["candidate_count"],
            },
            "italy": {
                "source_id": "it.853-2004",
                "observation_unit": "source observation",
                "count": italy["observation_count"],
            },
            "france": {
                "source_ids": ["fr.dgal.section-i", "fr.dgal.section-ii"],
                "observation_unit": "source observation; section identities remain separate",
                "section_i": france["section_i_count"],
                "section_ii": france["section_ii_count"],
            },
            "denmark": {
                "source_id": "dk.smiley",
                "observation_unit": "source observation; never labeled as a facility",
                "count": denmark["observation_count"],
                "distinct_source_observation_identity_count": denmark["observation_count"],
                "facility_identity_count": None,
                "identity_state": "source-key identity only; facility reconciliation not established",
            },
        },
        "candidates": {
            "by_source": {
                "us.fsis": fsis["candidate_count"],
                "it.853-2004": italy["provisional_identity_count"],
                "fr.dgal.union": france["union_candidate_count"],
            },
            "total": candidate_total,
            "identity_semantics": "provisional/source-scoped candidates; no canonical facility merge",
        },
        "coordinate_states": {
            "numeric_coordinate": {
                "by_source": {
                    "us.fsis": fsis["numeric_coordinate_count"],
                    "it.853-2004": italy["numeric_coordinate_count"],
                    "fr.dgal.union": france["numeric_coordinate_count"],
                },
                "total": numeric_total,
                "review_state": "pending human coordinate/privacy review",
            },
            "city_or_postal_geocode": {
                "by_source": {
                    "us.fsis": fsis["city_geocode_count"],
                    "it.853-2004": italy["city_only_count"],
                    "fr.dgal.union": france["city_postal_count"],
                },
                "total": city_total,
                "display_precision": "city-or-postal; never an exact facility point",
            },
            "rejected_zero_coordinates": {
                "by_source": {"it.853-2004": italy["rejected_zero_coordinate_count"]},
                "total": italy["rejected_zero_coordinate_count"],
                "meaning": "source-scoped candidate groups with a zero/zero pair and no usable non-zero coordinate pair; actual city values permit coarse placement",
            },
            "denmark": {
                "source_id": "dk.smiley",
                "unresolved_observations": denmark["observation_count"],
                "approved_numeric_coordinates": 0,
                "display_state": "no coordinate display approved; city/postal display count not supplied",
            },
        },
        "quarantine": {
            "denmark_validation_findings": denmark["validation_finding_count"],
            "record_level_counts": "not supplied in this row-free report",
            "unknown_is_not_zero": True,
            "policy": "ambiguous, unsafe, or unreviewed material remains restricted/quarantined",
        },
        "human_gates": {
            "source_terms_and_rights": "pending named review",
            "privacy_and_location": "pending record screening",
            "coordinate_precision": "pending review",
            "classification_and_identity": "pending review; no automatic merges",
            "project_approval": "not recorded",
            "publication": PUBLICATION_BLOCKED,
        },
        "private_rehearsal": {
            "status": "passed_offline; no authorized private handoff available",
            "database_started": False,
            "api_started": False,
            "reason": "D1 worktree contains no authorized private row handoff; no private path or row payload was imported",
            "fail_closed": True,
        },
        "limitations": [
            "Counts are row-free aggregates from restricted evidence and do not publish source rows.",
            "Observations, provisional candidates, and facilities are distinct concepts.",
            "Unknown quarantine and Denmark city/postal counts are not treated as zero.",
            "No source disappearance is interpreted as closure.",
            "No release, promotion, deployment, or human approval is created by this report.",
        ],
    }
    _safe(report)
    return report


def canonical_bytes(report: Mapping[str, Any]) -> bytes:
    _safe(report)
    return (json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = build_report(
        fsis={"candidate_count": 7241, "numeric_coordinate_count": 7241, "city_geocode_count": 0},
        italy={"observation_count": 41849, "provisional_identity_count": 25316, "numeric_coordinate_count": 24263, "city_only_count": 1053, "rejected_zero_coordinate_count": 486},
        france={"section_i_count": 1449, "section_ii_count": 1068, "union_candidate_count": 2283, "numeric_coordinate_count": 0, "city_postal_count": 2283},
        denmark={"observation_count": 58766, "validation_finding_count": 57, "legacy_v1_count": 1561},
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_bytes(report))
    print(json.dumps({"output": str(args.output), "schema_version": REPORT_VERSION}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
