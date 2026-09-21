"""Row-free FSIS current-to-legacy comparison helpers.

The legacy snapshot is a historical input, not a current-source claim.  This
module only emits aggregate counts and exact-key set differences when a
current parsed artifact is available.  Missing current observations remain
unknown and are never labelled closed.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


FALSE_VALUES = frozenset({"", "0", "false", "no", "none", "n/a", "na", "null"})
IDENTITY_ALIASES = {
    "establishment_id": ("establishment_id", "establishment id", "mpi id", "fsis id"),
    "establishment_number": (
        "establishment_number",
        "establishment number",
        "establishment no",
        "establishment no.",
        "plant number",
        "plant_number",
        "number",
    ),
}


def _header_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def _clean(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _value(row: dict[str, Any], aliases: Iterable[str]) -> str:
    wanted = {_header_key(alias) for alias in aliases}
    for key, value in row.items():
        if _header_key(str(key)) in wanted:
            return _clean(value)
    return ""


def _identity_token(row: dict[str, Any]) -> tuple[str, str] | None:
    for kind in ("establishment_id", "establishment_number"):
        value = _value(row, IDENTITY_ALIASES[kind])
        if value:
            return kind, value
    return None


def _identity_set(rows: Iterable[dict[str, Any]]) -> tuple[set[tuple[str, str]], Counter[str]]:
    identities: set[tuple[str, str]] = set()
    fields: Counter[str] = Counter()
    for row in rows:
        token = _identity_token(row)
        if token:
            identities.add(token)
            fields[token[0]] += 1
    return identities, fields


def _duplicate_facts(rows: list[dict[str, Any]]) -> dict[str, int]:
    alias_counts: Counter[tuple[str, str]] = Counter()
    for row in rows:
        for kind, aliases in IDENTITY_ALIASES.items():
            value = _value(row, aliases)
            if value:
                alias_counts[(kind, value)] += 1
    duplicates = {key: count for key, count in alias_counts.items() if count > 1}
    duplicate_rows = sum(
        1
        for row in rows
        if any((kind, _value(row, aliases)) in duplicates for kind, aliases in IDENTITY_ALIASES.items())
    )
    return {"duplicate_identity_aliases": len(duplicates), "duplicate_identity_rows": duplicate_rows}


def _category_facts(rows: list[dict[str, Any]], headers: tuple[str, ...]) -> dict[str, Any]:
    normalized_headers = {header: _header_key(header) for header in headers}
    slaughter_fields = sorted(header for header, key in normalized_headers.items() if "slaughter" in key)
    processing_fields = sorted(header for header, key in normalized_headers.items() if "processing" in key)

    def has_value(row: dict[str, Any], fields: list[str]) -> bool:
        return any(_clean(row.get(field)).lower() not in FALSE_VALUES for field in fields)

    return {
        "slaughter_field_count": len(slaughter_fields),
        "processing_field_count": len(processing_fields),
        "slaughter_rows_with_value": sum(1 for row in rows if has_value(row, slaughter_fields)),
        "processing_rows_with_value": sum(1 for row in rows if has_value(row, processing_fields)),
        "rows_with_any_activity_value": sum(
            1 for row in rows if has_value(row, slaughter_fields) or has_value(row, processing_fields)
        ),
        "rows_with_no_activity_value": sum(
            1 for row in rows if not has_value(row, slaughter_fields) and not has_value(row, processing_fields)
        ),
    }


def _read_csv(path: Path) -> tuple[tuple[str, ...], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        headers = tuple(reader.fieldnames or ())
        if not headers:
            raise ValueError(f"missing CSV header: {path}")
        return headers, list(reader)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSONL at {path}:{line_number}") from exc
            if not isinstance(item, dict):
                raise ValueError(f"JSONL record is not an object at {path}:{line_number}")
            records.append(item)
    return records


def _current_identity_set(records: Iterable[dict[str, Any]]) -> tuple[set[tuple[str, str]], Counter[str]]:
    rows: list[dict[str, Any]] = []
    for item in records:
        source_values = item.get("source_values") or {}
        directory = source_values.get("directory") if isinstance(source_values, dict) else None
        if isinstance(directory, dict):
            rows.append(directory)
            continue
        normalized = item.get("normalized") or {}
        if isinstance(normalized, dict):
            rows.append(normalized)
    return _identity_set(rows)


def compare_legacy(
    legacy_path: str | Path,
    *,
    current_records_path: str | Path | None = None,
    current_manifest_path: str | Path | None = None,
) -> dict[str, Any]:
    """Build a row-free FSIS legacy comparison report."""
    legacy = Path(legacy_path)
    headers, rows = _read_csv(legacy)
    legacy_ids, legacy_identity_fields = _identity_set(rows)
    legacy_summary: dict[str, Any] = {
        "artifact_path": str(legacy),
        "status": "legacy-snapshot",
        "rows": len(rows),
        "columns": len(headers),
        "source_native_establishments": len(legacy_ids),
        "missing_identity_rows": len(rows) - sum(legacy_identity_fields.values()),
        "identity_field_rows": dict(sorted(legacy_identity_fields.items())),
        **_duplicate_facts(rows),
        "category_coverage": _category_facts(rows, headers),
        "currentness_claim": False,
    }

    current: dict[str, Any]
    current_ids: set[tuple[str, str]] | None = None
    if current_records_path is None:
        current = {
            "status": "not-observed",
            "artifact_available": False,
            "rows": None,
            "source_native_establishments": None,
            "limitation": "No current FSIS row artifact was captured; route returned HTTP 403.",
        }
    else:
        current_path = Path(current_records_path)
        records = _read_jsonl(current_path)
        current_ids, current_identity_fields = _current_identity_set(records)
        current = {
            "status": "observed-private-artifact",
            "artifact_available": True,
            "artifact_path": str(current_path),
            "rows": len(records),
            "source_native_establishments": len(current_ids),
            "identity_field_rows": dict(sorted(current_identity_fields.items())),
            "currentness_claim": False,
        }
        if current_manifest_path is not None:
            manifest = json.loads(Path(current_manifest_path).read_text(encoding="utf-8"))
            if isinstance(manifest, dict) and isinstance(manifest.get("source_metrics"), dict):
                current["source_metrics"] = manifest["source_metrics"]

    if current_ids is None:
        comparison = {
            "status": "current-not-observed",
            "additions": None,
            "not_observed": None,
            "unresolved_current_rows": None,
            "not_observed_means_closure": False,
            "limitation": "Additions and not-observed counts require a captured current row artifact; absence is not closure.",
        }
    else:
        comparison = {
            "status": "exact-key-set-comparison",
            "additions": len(current_ids - legacy_ids),
            "not_observed": len(legacy_ids - current_ids),
            "unresolved_current_rows": len(current_ids & legacy_ids),
            "not_observed_means_closure": False,
            "identity_rule": "exact source-native establishment ID, falling back to exact source-native establishment number",
        }

    return {
        "report_version": "us-fsis-legacy-comparison-v1",
        "source_id": "us.fsis",
        "legacy": legacy_summary,
        "current": current,
        "comparison": comparison,
        "publication_state": "private-candidate-only",
        "row_payloads_included": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--legacy", type=Path, required=True)
    parser.add_argument("--current-records", type=Path)
    parser.add_argument("--current-manifest", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = compare_legacy(
        args.legacy,
        current_records_path=args.current_records,
        current_manifest_path=args.current_manifest,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(args.output), "status": report["comparison"]["status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
