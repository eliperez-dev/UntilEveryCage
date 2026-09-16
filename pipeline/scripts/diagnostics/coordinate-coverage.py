#!/usr/bin/env python3
"""Write a row-free aggregate report of coordinate evidence states.

The input is a JSONL stage export.  Only aggregate counts are written; source
keys, names, addresses, coordinates, queries, and geocoder responses are never
copied to the report.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


STATES = ("source_supplied", "geocoded_exact", "approximate_coarse", "unresolved", "restricted")


def _has_source_coordinate(record: dict[str, Any]) -> bool:
    coordinates = record.get("coordinates")
    return isinstance(coordinates, dict) and all(
        coordinates.get(key) is not None for key in ("latitude", "longitude")
    )


def coordinate_state(record: dict[str, Any]) -> str:
    """Classify one observation without exposing any record value."""
    if record.get("restricted") is True or record.get("privacy_status") in {
        "restricted",
        "failed",
        "suppressed",
    }:
        return "restricted"
    if _has_source_coordinate(record):
        return "source_supplied"
    geocode = record.get("geocode")
    if not isinstance(geocode, dict):
        geocode = {}
    status = geocode.get("status") or record.get("geocoding_status")
    precision = geocode.get("precision") or record.get("coordinate_precision")
    if status == "accepted" and geocode.get("result") is not None:
        return "geocoded_exact" if precision in (None, "exact", "rooftop", "parcel") else "approximate_coarse"
    if status in {"review_required", "approximate", "coarse"} or precision in {"city", "coarse", "approximate"}:
        return "approximate_coarse"
    return "unresolved"


def build_report(input_path: Path) -> dict[str, Any]:
    counts = Counter()
    facility_ids: set[str] = set()
    records_seen = 0
    with input_path.open(encoding="utf-8") as source:
        for line in source:
            if not line.strip():
                continue
            record = json.loads(line)
            if not isinstance(record, dict):
                raise ValueError("each JSONL item must be an object")
            records_seen += 1
            counts[coordinate_state(record)] += 1
            facility_id = record.get("facility_id")
            if facility_id is not None:
                facility_ids.add(str(facility_id))
    return {
        "report_version": "coordinate-coverage-1",
        "observations": records_seen,
        "unique_facilities": len(facility_ids),
        "coordinate_states": {state: counts[state] for state in STATES},
        "raw_rows_in_report": False,
        "sensitive_fields_in_report": False,
        "semantics": "Counts are observations; unique_facilities uses facility_id when present.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = build_report(args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
