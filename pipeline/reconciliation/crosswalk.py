"""Aggregate V1-to-V2 comparison without identity guesses.

This module deliberately accepts only an explicit, source-qualified key. It
does not fuzzy-match names, addresses, geocoder results, or coordinates, and
it does not interpret a missing V2 observation as closure.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


class CrosswalkError(ValueError):
    """Raised when a comparison input violates the crosswalk contract."""


def _rows(path: Path, kind: str) -> list[dict[str, Any]]:
    if not path.exists():
        raise CrosswalkError(f"missing {kind} input: {path}")
    try:
        if path.suffix.lower() == ".csv":
            with path.open(newline="", encoding="utf-8-sig") as handle:
                return list(csv.DictReader(handle))
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, UnicodeError, json.JSONDecodeError, csv.Error) as exc:
        raise CrosswalkError(f"could not read {kind} input: {path}") from exc


def _value(row: dict[str, Any], path: str) -> Any:
    value: Any = row
    for part in path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def _keys(rows: Iterable[dict[str, Any]], field: str, label: str) -> tuple[set[str], set[str], int]:
    keys: list[str] = []
    missing = 0
    for row in rows:
        value = _value(row, field)
        if value is None or not str(value).strip():
            missing += 1
            continue
        keys.append(str(value).strip())
    counts = Counter(keys)
    ambiguous = {key for key, count in counts.items() if count > 1}
    return set(keys), ambiguous, missing


def _coordinate_stats(rows: Iterable[dict[str, Any]], path: str) -> dict[str, int]:
    states = Counter()
    for row in rows:
        value = _value(row, path)
        if value is None or value == "":
            states["missing"] += 1
        else:
            states["present"] += 1
    return dict(sorted(states.items()))


def _field_counts(rows: Iterable[dict[str, Any]], path: str) -> dict[str, int]:
    values = Counter()
    for row in rows:
        value = _value(row, path)
        if value is not None and str(value).strip():
            values[str(value).strip()] += 1
    return dict(sorted(values.items()))


def compare_v1_v2(
    v1_path: str | Path,
    v2_path: str | Path,
    *,
    v1_key: str,
    v2_key: str,
    v1_country: str,
    v2_source_id: str,
    v1_coordinate_field: str | None = None,
    v2_coordinate_field: str = "normalized.coordinates",
    v2_classification_field: str = "normalized.classification",
    v2_effective_date_field: str = "normalized.effective_date",
) -> dict[str, Any]:
    """Return a row-free, deterministic crosswalk report.

    Matching is exact and key-based only. Duplicate keys are excluded from
    matches and reported as ``ambiguous``. ``not_observed_in_v2`` is an
    observation difference, never a closure or deletion decision.
    """
    v1 = _rows(Path(v1_path), "V1")
    v2 = _rows(Path(v2_path), "V2")
    if not v1_country or not v2_source_id:
        raise CrosswalkError("country and source_id are required")
    v1_keys, v1_ambiguous, v1_missing = _keys(v1, v1_key, "V1")
    v2_keys, v2_ambiguous, v2_missing = _keys(v2, v2_key, "V2")
    ambiguous = v1_ambiguous | v2_ambiguous
    matched = (v1_keys & v2_keys) - ambiguous
    return {
        "report_version": "v1-v2-crosswalk-1",
        "country_code": v1_country,
        "v2_source_id": v2_source_id,
        "matching": {"strategy": "exact_key_only", "fuzzy_matching": False, "coordinate_matching": False},
        "counts": {
            "v1_rows": len(v1), "v2_rows": len(v2), "matched": len(matched),
            "ambiguous": len(ambiguous), "v1_missing_key": v1_missing,
            "v2_missing_key": v2_missing, "v2_only": len(v2_keys - v1_keys - ambiguous),
            "not_observed_in_v2": len(v1_keys - v2_keys - ambiguous),
        },
        "interpretation": {
            "not_observed_in_v2_is_closure": False,
            "ambiguous_keys_are_matched": False,
            "identity_decisions_created": False,
            "raw_rows_in_report": False,
        },
        "v1_coordinates": _coordinate_stats(v1, v1_coordinate_field) if v1_coordinate_field else {"not_compared": len(v1)},
        "v2_coordinates": _coordinate_stats(v2, v2_coordinate_field),
        "v2_classifications": _field_counts(v2, v2_classification_field),
        "v2_effective_dates": _field_counts(v2, v2_effective_date_field),
        "quarantine": {"v2_rows": sum(1 for row in v2 if row.get("quarantine_reason") or row.get("reasons"))},
    }
