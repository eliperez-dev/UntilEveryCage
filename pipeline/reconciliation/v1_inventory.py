"""Row-free inventory of checked-in V1 country snapshots."""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path
from typing import Any

from .crosswalk import CrosswalkError

DEFAULT_COUNTRIES = ("ca", "de", "dk", "es", "fr", "it", "mx", "nz", "uk", "us")


def inventory_v1(path: str | Path, *, key_field: str = "establishment_id", coordinate_fields: tuple[str, str] = ("latitude", "longitude")) -> dict[str, Any]:
    source = Path(path)
    if not source.exists():
        raise CrosswalkError(f"missing V1 inventory input: {source}")
    try:
        with source.open(newline="", encoding="utf-8-sig") as handle:
            rows = list(csv.DictReader(handle))
    except (OSError, UnicodeError, csv.Error) as exc:
        raise CrosswalkError(f"could not read V1 inventory input: {source}") from exc
    values = [str(row.get(key_field) or "").strip() for row in rows]
    present = [value for value in values if value]
    duplicate_keys = {key for key, count in Counter(present).items() if count > 1}
    coords_present = sum(1 for row in rows if all(str(row.get(field) or "").strip() for field in coordinate_fields))
    return {
        "report_version": "v1-inventory-1",
        "source_path": source.as_posix(),
        "comparison_status": "blocked_no_private_v2_artifact",
        "counts": {"rows": len(rows), "keys_present": len(present), "keys_missing": len(rows) - len(present), "duplicate_keys": len(duplicate_keys), "coordinate_pairs_present": coords_present},
        "key": {"field": key_field, "strategy": "exact_key_only", "ambiguous_keys_are_not_resolved": True},
        "interpretation": {"v1_rows_are_current": False, "missing_v2_means_closed": False, "identity_decisions_created": False, "raw_rows_in_report": False},
    }
