"""Deterministic, private, row-free evaluation of the real legacy corpus.

This measures source coordinates and source-native identity fields. It never
geocodes, fuzzy-matches, joins by names/proximity, or emits rows, IDs, names,
addresses, or coordinates. It is an evaluation report, not an accuracy claim:
accuracy requires adjudicated labels that this corpus does not contain.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable


CORPUS_COUNTRIES = ("ca", "de", "dk", "es", "fr", "mx", "nz", "uk", "us")
US_SAMPLE_SIZES = {
    "fsis_locations": 3_500,
    "fsis_inspections": 2_500,
    "aphis_observations": 1_000,
}
US_SAMPLE_FILES = {
    "fsis_locations": "us/locations.csv",
    "fsis_inspections": "us/inspection_reports.csv",
    "aphis_observations": "us/aphis_data_final.csv",
}
ID_FIELDS = (
    "establishment_id", "establishment_number", "Certificate Number",
    "Certificate Number_x", "Certificate Number_y", "Customer Number",
    "Customer Number_x", "Customer Number_y", "facility_id", "operator_id",
)
NAME_FIELDS = (
    "establishment_name", "Account Name", "account_name", "facility_name",
    "operator_name", "name",
)
CITY_FIELDS = ("city", "City", "City-State-Zip")
LAT_FIELDS = ("latitude", "Latitude", "Geocodio Latitude", "lat")
LON_FIELDS = ("longitude", "Longitude", "Geocodio Longitude", "lon", "lng")
ADDRESS_FIELDS = (
    "street", "address", "Address Line 1", "Address Line 2", "City-State-Zip",
)
PRIVACY_PATTERNS = {
    "residential_or_private_term": re.compile(r"\b(private|residential|home|farmhouse)\b", re.I),
    "care_of_or_mailbox": re.compile(r"\b(c/o|care\s+of|p\.?\s*o\.?\s*box)\b", re.I),
    "unit_or_apartment": re.compile(r"\b(apt|apartment|unit|suite)\b", re.I),
}
EXPLICIT_ENDPOINT_PAIRS = (
    ("operator_id", "facility_id"),
    ("operator_id", "establishment_id"),
    ("subject_source_native_id", "object_source_native_id"),
)


def _text(row: dict[str, str], fields: Iterable[str]) -> str:
    for field in fields:
        value = row.get(field)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _number(value: str | None) -> float | None:
    try:
        return float(value.strip()) if value and value.strip() else None
    except (AttributeError, ValueError):
        return None


def _coordinate(row: dict[str, str]) -> tuple[str, float | None, float | None]:
    raw_lat, raw_lon = _text(row, LAT_FIELDS), _text(row, LON_FIELDS)
    lat, lon = _number(raw_lat), _number(raw_lon)
    if lat is None or lon is None:
        return "missing_or_non_numeric", lat, lon
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return "out_of_range", lat, lon
    if lat == 0 and lon == 0:
        return "zero_pair", lat, lon
    return "valid", lat, lon


def _precision(row: dict[str, str]) -> str:
    raw_lat, raw_lon = _text(row, LAT_FIELDS), _text(row, LON_FIELDS)
    digits = []
    for value in (raw_lat, raw_lon):
        if "." in value:
            digits.append(len(value.split(".", 1)[1].rstrip("0")))
        else:
            digits.append(0)
    if not digits or not _coordinate(row)[0] == "valid":
        return "not_available"
    maximum = max(digits)
    return f"decimal_digits_{maximum}" if maximum <= 6 else "decimal_digits_7_plus"


def _source_id(row: dict[str, str]) -> tuple[str, str] | None:
    for field in ID_FIELDS:
        value = row.get(field)
        if value is not None and str(value).strip():
            return field, str(value).strip()
    return None


def _identity_quality(row: dict[str, str]) -> str:
    identifier = _source_id(row)
    has_name = bool(_text(row, NAME_FIELDS))
    has_city = bool(_text(row, CITY_FIELDS))
    if identifier and has_name and has_city:
        return "strong"
    if identifier and (has_name or has_city):
        return "partial"
    return "weak_or_missing"


def _privacy_reasons(row: dict[str, str]) -> tuple[str, ...]:
    address = " ".join(str(row.get(field) or "") for field in ADDRESS_FIELDS)
    return tuple(name for name, pattern in PRIVACY_PATTERNS.items() if pattern.search(address))


def _category(row: dict[str, str]) -> str:
    active = {key.lower() for key, value in row.items() if value and str(value).strip().lower() not in {"0", "false", "no", "none", "nan"}}
    if any("slaughter" in key for key in active):
        return "slaughter_or_processing"
    if any("process" in key for key in active):
        return "processing"
    if any("inspection" in key or "license" in key or "certificate" in key for key in active):
        return "inspection_or_license"
    return "other"


def _fingerprint(namespace: str, row_number: int, row: dict[str, str]) -> str:
    stable = "\0".join((namespace, str(row_number), *(str(row.get(key) or "") for key in sorted(row))))
    return hashlib.sha256(stable.encode("utf-8", "surrogateescape")).hexdigest()


def _read(path: Path) -> list[tuple[int, dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [(number, row) for number, row in enumerate(csv.DictReader(handle), start=2)]


def _source_metrics(path: Path, rows: list[tuple[int, dict[str, str]]], source_name: str) -> dict:
    coordinates = Counter()
    precision = Counter()
    identities = Counter()
    categories = Counter()
    privacy = Counter()
    id_rows: defaultdict[tuple[str, str], list[tuple[str, str, str]]] = defaultdict(list)
    for row_number, row in rows:
        coordinate_state, _, _ = _coordinate(row)
        coordinates[coordinate_state] += 1
        precision[_precision(row)] += 1
        identity = _source_id(row)
        identities[_identity_quality(row)] += 1
        categories[_category(row)] += 1
        reasons = _privacy_reasons(row)
        for reason in reasons:
            privacy[reason] += 1
        if identity:
            signature = (_text(row, NAME_FIELDS), _text(row, CITY_FIELDS), coordinate_state,
                         _text(row, LAT_FIELDS), _text(row, LON_FIELDS))
            id_rows[identity].append(signature)

    duplicate_rows = sum(max(0, len(values) - 1) for values in id_rows.values())
    conflicting_keys = sum(len({signature for signature in values}) > 1 for values in id_rows.values())
    conflicting_rows = sum(len(values) for values in id_rows.values() if len({signature for signature in values}) > 1)
    total = len(rows)
    return {
        "source": source_name,
        "path": path.as_posix(),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "bytes": path.stat().st_size,
        "rows": total,
        "coordinates": dict(sorted(coordinates.items())),
        "coordinate_valid_rate": round(coordinates["valid"] / total, 6) if total else None,
        "coordinate_precision": dict(sorted(precision.items())),
        "identity_quality": dict(sorted(identities.items())),
        "source_identifier_rows": sum(len(values) for values in id_rows.values()),
        "source_identifier_unique": len(id_rows),
        "duplicate_source_identifier_rows": duplicate_rows,
        "duplicate_source_identifier_rate": round(duplicate_rows / total, 6) if total else None,
        "identity_conflict_keys": conflicting_keys,
        "identity_conflict_rows": conflicting_rows,
        "identity_conflict_rate": round(conflicting_rows / total, 6) if total else None,
        "category_composition": dict(sorted(categories.items())),
        "privacy_review_queue": {
            "flagged_rows": sum(1 for row_number, row in rows if _privacy_reasons(row)),
            "flagged_rate": round(sum(1 for row_number, row in rows if _privacy_reasons(row)) / total, 6) if total else None,
            "by_reason": dict(sorted(privacy.items())),
        },
    }


def _sample_metrics(path: Path, requested: int, source_name: str) -> dict:
    rows = _read(path)
    ranked = sorted((_fingerprint(source_name, number, row), number, row) for number, row in rows)
    if len(ranked) < requested:
        raise ValueError(f"{path} has {len(ranked)} rows; {requested} required")
    selected = ranked[:requested]
    identifiers = [_source_id(row) for _, _, row in selected]
    explicit_edges = sum(
        any(bool(_text(row, (left,))) and bool(_text(row, (right,)))
            for left, right in EXPLICIT_ENDPOINT_PAIRS)
        for _, _, row in selected
    )
    return {
        "path": path.as_posix(),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "available_rows": len(rows),
        "requested_rows": requested,
        "selected_rows": len(selected),
        "coordinate_metrics": _source_metrics(path, [(number, row) for _, number, row in selected], source_name),
        "source_native_identifier_rows": sum(identifier is not None for identifier in identifiers),
        "source_native_identifier_unique": len({identifier for identifier in identifiers if identifier is not None}),
        "source_native_identifier_missing_rows": sum(identifier is None for identifier in identifiers),
        "explicit_endpoint_pair_rows": explicit_edges,
        "cross_source_relationship_candidates": 0,
        "name_or_proximity_matches_attempted": 0,
        "candidate_rule": "exact source-native identifiers only; no cross-source endpoint pair exists in these legacy files",
    }


def build_report(root: Path = Path("static_data"), *, as_of: str = "") -> dict:
    files = {country: root / country / "locations.csv" for country in CORPUS_COUNTRIES}
    missing = [path.as_posix() for path in files.values() if not path.is_file()]
    if missing:
        raise ValueError("missing corpus inputs: " + ", ".join(missing))
    source_metrics = []
    totals = Counter()
    composition = Counter()
    for country, path in files.items():
        rows = _read(path)
        metric = _source_metrics(path, rows, f"v1.{country}.locations")
        source_metrics.append(metric)
        totals.update({"rows": metric["rows"], "valid_coordinates": metric["coordinates"].get("valid", 0), "missing_or_invalid_coordinates": metric["rows"] - metric["coordinates"].get("valid", 0), "duplicate_identifier_rows": metric["duplicate_source_identifier_rows"], "identity_conflict_rows": metric["identity_conflict_rows"], "privacy_flagged_rows": metric["privacy_review_queue"]["flagged_rows"]})
        for category, count in metric["category_composition"].items():
            composition[(country, category)] += count

    samples = {
        name: _sample_metrics(root / path, count, name)
        for name, path in US_SAMPLE_FILES.items()
        for count in (US_SAMPLE_SIZES[name],)
    }
    sample_totals = Counter()
    for sample in samples.values():
        sample_totals.update({"selected_rows": sample["selected_rows"], "source_native_identifier_rows": sample["source_native_identifier_rows"], "missing_source_native_identifier_rows": sample["source_native_identifier_missing_rows"], "explicit_endpoint_pair_rows": sample["explicit_endpoint_pair_rows"]})

    return {
        "schema_version": "real-quality-evaluation-v1",
        "as_of_utc": as_of or None,
        "corpus_state": "private-regression-only",
        "publication_eligibility": "blocked",
        "method": {
            "selection": "all available legacy rows; US strata selected by ascending SHA-256 row fingerprint",
            "coordinate_validation": "numeric latitude/longitude range and zero-pair checks; no geocoder",
            "identity_duplicates": "source-native identifier repetitions within each source file",
            "identity_conflicts": "same source-native identifier mapped to differing nonempty name/city/coordinate-state signatures",
            "privacy_queue": "conservative text indicators for human review, not residential classifications",
            "accuracy": "not measured; no adjudicated truth labels are available",
        },
        "corpus": {
            "available_rows": totals["rows"],
            "country_count": len(files),
            "source_profile_count": len(files),
            "totals": dict(sorted(totals.items())),
            "country_composition": {country: metric["rows"] for country, metric in sorted(zip(files, source_metrics))},
            "category_composition": {"|".join(key): value for key, value in sorted(composition.items())},
            "sources": source_metrics,
        },
        "privacy_review_queue": {
            "rows_flagged_for_human_review": totals["privacy_flagged_rows"],
            "scope": "aggregate counts only; flagged rows and address text remain private",
            "indicators": sorted(PRIVACY_PATTERNS),
        },
        "us_planned_sample": {
            "requested": dict(US_SAMPLE_SIZES),
            "available": {name: sample["available_rows"] for name, sample in sorted(samples.items())},
            "selected_total": sample_totals["selected_rows"],
            "selected": samples,
            "aggregate": dict(sorted(sample_totals.items())),
        },
        "graph_candidate_yield": {
            "source_native_entity_candidate_rows": sample_totals["source_native_identifier_rows"],
            "source_native_entity_candidate_unique_ids": sum(sample["source_native_identifier_unique"] for sample in samples.values()),
            "explicit_endpoint_pair_rows": sample_totals["explicit_endpoint_pair_rows"],
            "cross_source_relationship_candidates": 0,
            "name_or_proximity_matches_attempted": 0,
            "interpretation": "Legacy FSIS, inspection, and APHIS snapshots contain source-native identifiers but no explicit cross-source endpoint pair in the sampled rows. No identity or relationship is inferred.",
        },
        "review_needs": [
            "Coordinate validity is not positional accuracy; adjudicated coordinate labels are required before accuracy estimates.",
            "Privacy indicators are conservative review queues, not factual residential determinations.",
            "Duplicate and conflict rates are within-source diagnostics; they do not establish cross-source identity.",
            "US samples are V1-derived snapshots without raw source artifacts in this checkout; raw-preserving acquisition and terms review remain open.",
            "Graph candidate yield counts exact source-native opportunities only; zero cross-source candidates is an observed schema result, not evidence that no relationship exists.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("static_data"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--as-of", default="")
    args = parser.parse_args()
    report = build_report(args.root, as_of=args.as_of)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "available_rows": report["corpus"]["available_rows"],
        "us_selected_rows": report["us_planned_sample"]["selected_total"],
        "cross_source_relationship_candidates": report["graph_candidate_yield"]["cross_source_relationship_candidates"],
        "publication_eligibility": report["publication_eligibility"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
