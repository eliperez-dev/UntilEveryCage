#!/usr/bin/env python3
"""Build a row-free aggregate distribution from private V2 normalized JSONL.

The input remains in local restricted storage. The output contains only
bounded aggregate strata used to shape a synthetic API rehearsal; it never
copies identifiers, names, addresses, coordinates, source values, or rows.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

MAX_RECORDS = 25_000
ALLOWED_CATEGORIES = {
    "slaughter", "fish_processing", "logistics_and_storage",
    "retail_and_prepared_food",
}
ALLOWED_PRECISIONS = {"exact", "city", "unmapped"}


def _normalized(payload: Any) -> dict[str, Any]:
    value = payload.get("normalized") if isinstance(payload, dict) else None
    return value if isinstance(value, dict) else payload if isinstance(payload, dict) else {}


def _category(value: Any) -> str:
    values = value if isinstance(value, (list, tuple)) else [value]
    for item in values:
        if isinstance(item, str) and item in ALLOWED_CATEGORIES:
            return item
    return "other"


def _precision(record: dict[str, Any]) -> str:
    value = record.get("display_precision")
    if isinstance(value, str) and value in ALLOWED_PRECISIONS:
        return value
    coordinates = record.get("coordinates")
    if isinstance(coordinates, (list, tuple)) and len(coordinates) == 2:
        try:
            longitude, latitude = float(coordinates[0]), float(coordinates[1])
            if -180 <= longitude <= 180 and -90 <= latitude <= 90:
                return "exact"
        except (TypeError, ValueError):
            pass
    return "unmapped"


def _country(record: dict[str, Any]) -> str:
    value = record.get("country_code")
    return value.upper() if isinstance(value, str) and len(value) == 2 and value.isascii() else "XX"


def build_distribution(inputs: list[Path], *, max_records: int = MAX_RECORDS) -> dict[str, Any]:
    if not inputs:
        raise ValueError("at least one private normalized JSONL input is required")
    if not 1 <= max_records <= MAX_RECORDS:
        raise ValueError(f"max_records must be between 1 and {MAX_RECORDS:,}")
    candidates: list[tuple[str, dict[str, Any]]] = []
    invalid_records = 0
    for path in inputs:
        if not path.is_file():
            raise ValueError(f"private normalized input is missing: {path}")
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    invalid_records += 1
                    continue
                record = _normalized(payload)
                if not record:
                    invalid_records += 1
                    continue
                candidates.append((hashlib.sha256(line.encode("utf-8")).hexdigest(), record))
    selected = sorted(candidates, key=lambda item: item[0])[:max_records]
    strata = Counter(
        (_country(record), _category(record.get("activity_categories") or record.get("classification_categories")), _precision(record))
        for _, record in selected
    )
    return {
        "schema_version": "v2-private-distribution-v1",
        "corpus_state": "private-regression-only",
        "publication_eligibility": "blocked",
        "selection": {
            "method": "stable-sha256-record-selection",
            "max_records": max_records,
            "selected_records": len(selected),
            "available_records": len(candidates),
            "invalid_records": invalid_records,
        },
        "distribution": [
            {"country_code": country, "category": category, "display_precision": precision, "records": count}
            for (country, category, precision), count in sorted(strata.items())
        ],
        "limitations": [
            "The benchmark expands only aggregate strata into synthetic values.",
            "No publication, release, factual review, or privacy approval is implied.",
            "Raw and normalized private inputs remain local and are never copied to the report.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--normalized", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-records", type=int, default=MAX_RECORDS)
    args = parser.parse_args()
    try:
        report = build_distribution(args.normalized, max_records=args.max_records)
    except ValueError as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"selected_records": report["selection"]["selected_records"], "publication_eligibility": report["publication_eligibility"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
