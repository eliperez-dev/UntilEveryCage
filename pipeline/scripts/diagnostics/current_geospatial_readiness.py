#!/usr/bin/env python3
"""Audit current private candidate handoffs without emitting record data.

The candidate handoff is deliberately the input boundary here.  Raw source
artifacts, addresses, identifiers, geocoder queries, and responses stay in
the operator's restricted staging area.  The output contains only source
metadata and aggregate counts, so it is safe to commit as a diagnostic
contract or attach to a review packet.

The audit is intentionally conservative:

* source coordinates are counted separately from geocoder results;
* invalid values are not repaired or converted into an approximate point;
* a city label is a coarse location, never an inferred coordinate;
* coordinate/privacy review queues are not treated as approval;
* an absent private handoff is reported as unavailable, not as zero rows;
* malformed rows increment an explicit parse-error counter instead of being
  silently skipped.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any


REPORT_VERSION = "current-geospatial-readiness-v1"
DISPLAY_STATES = ("exact", "city", "unmapped", "restricted")
EVIDENCE_STATES = (
    "source_coordinate_valid",
    "source_coordinate_invalid",
    "source_coordinate_pending_review",
    "accepted_geocode_exact",
    "accepted_geocode_coarse",
    "geocode_unresolved",
    "coarse_city_location",
    "unresolved",
)

_EXACT_PRECISIONS = frozenset({"exact", "rooftop", "parcel", "building", "address", "address_point"})
_COARSE_PRECISIONS = frozenset({"city", "coarse", "approximate", "region", "postal_code"})
_PRIVACY_REVIEW_VALUES = frozenset({"pending", "review_required", "required", "pending-review", "restricted-withheld-address"})
_WHOLE_RECORD_RESTRICTION_VALUES = frozenset({"restricted", "failed", "suppressed", "blocked"})
_REVIEW_REASONS = frozenset({
    "address_privacy_risk",
    "privacy_review_required",
    "residential_or_private_term",
    "care_of_or_mailbox",
    "unit_or_apartment",
    "mixed_use_or_unclear_location",
})


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _first(mapping: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value is not None and value != "":
            return value
    return None


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _point(value: Any) -> tuple[float | None, float | None, bool]:
    """Return latitude, longitude, and whether a coordinate value was present."""
    if isinstance(value, dict):
        present = any(key in value for key in ("latitude", "lat", "longitude", "lon", "lng", "x", "y"))
        latitude = _number(_first(value, "latitude", "lat", "y"))
        longitude = _number(_first(value, "longitude", "lon", "lng", "x"))
        return latitude, longitude, present
    if isinstance(value, (list, tuple)) and len(value) == 2:
        # GeoJSON/source arrays are longitude, latitude.
        return _number(value[1]), _number(value[0]), True
    return None, None, value is not None


def _valid_point(latitude: float | None, longitude: float | None) -> bool:
    return (
        latitude is not None
        and longitude is not None
        and -90 <= latitude <= 90
        and -180 <= longitude <= 180
        and not (latitude == 0 and longitude == 0)
    )


def _coordinate_from(normalized: dict[str, Any], row: dict[str, Any], *, source: bool) -> tuple[float | None, float | None, bool]:
    nested = _first(normalized, "coordinates", "coordinate", "location")
    latitude, longitude, present = _point(nested)
    if present:
        return latitude, longitude, True
    fields = ("source_latitude", "source_longitude") if source else ("latitude", "longitude")
    source_values = _mapping(row.get("source_values"))
    coordinate_fields = ("latitude", "lat", "Geo_Lat", "latitudine") if source else ("latitude", "lat")
    longitude_fields = ("longitude", "lon", "lng", "Geo_Lng", "longitudine") if source else ("longitude", "lon", "lng")
    latitude = _number(_first(normalized, *fields, *coordinate_fields))
    longitude = _number(_first(normalized, fields[1], *longitude_fields))
    if source and (latitude is None and longitude is None):
        latitude = _number(_first(source_values, *coordinate_fields))
        longitude = _number(_first(source_values, *longitude_fields))
    if latitude is not None or longitude is not None:
        return latitude, longitude, True
    # A few source adapters keep the coordinate object on the envelope.
    return _point(_first(row, "coordinates", "coordinate"))


def _geocode(normalized: dict[str, Any], row: dict[str, Any]) -> tuple[str | None, str | None, bool]:
    result = _mapping(_first(normalized, "geocode", "geocoding", "geocode_result"))
    status = _first(result, "status") or _first(normalized, "geocode_status", "geocoding_status")
    precision = _first(result, "precision") or _first(normalized, "coordinate_precision", "geocode_precision")
    point_value = _first(result, "result", "coordinates", "location")
    if point_value is None:
        point_value = _first(row, "geocode", "geocoding")
    latitude, longitude, present = _point(point_value)
    return (str(status).lower() if status is not None else None,
            str(precision).lower() if precision is not None else None,
            _valid_point(latitude, longitude) if present else False)


def _city_present(normalized: dict[str, Any]) -> bool:
    return bool(_first(normalized, "city", "municipality", "town", "commune", "postal_code", "postcode"))


def _whole_record_suppressed(normalized: dict[str, Any], row: dict[str, Any]) -> bool:
    if any(_first(mapping, "suppressed", "is_suppressed") is True for mapping in (normalized, row)):
        return True
    values = (
        _first(normalized, "privacy_status", "publication_status", "suppression_status"),
        _first(row, "privacy_status", "publication_status", "suppression_status"),
    )
    return any(str(value).lower() in _WHOLE_RECORD_RESTRICTION_VALUES for value in values if value is not None)


def _privacy_reasons(normalized: dict[str, Any], row: dict[str, Any]) -> tuple[str, ...]:
    reasons: set[str] = set()
    for mapping in (normalized, row):
        value = _first(mapping, "privacy_gate", "privacy_status", "privacy_review_status")
        if value is not None and str(value).lower() in _PRIVACY_REVIEW_VALUES:
            reasons.add(str(value).lower())
        flags = _first(mapping, "privacy_review_reasons", "privacy_flags", "review_reasons", "reasons")
        if isinstance(flags, str):
            flags = (flags,)
        if isinstance(flags, (list, tuple, set)):
            reasons.update(str(flag) for flag in flags if str(flag) in _REVIEW_REASONS)
    return tuple(sorted(reasons))


def _coordinate_review_reasons(normalized: dict[str, Any], row: dict[str, Any]) -> tuple[str, ...]:
    reasons: set[str] = set()
    for mapping in (normalized, row):
        gate = _first(mapping, "coordinate_gate", "coordinate_review_status", "coordinate_state")
        if gate is not None and str(gate).lower() in {"review_required", "pending", "withheld", "restricted-withheld-address", "unresolved", "not-supplied-by-source"}:
            reasons.add(str(gate).lower())
    return tuple(sorted(reasons))


def classify_record(row: dict[str, Any]) -> dict[str, Any]:
    """Classify one candidate row without retaining any row value."""
    normalized = _mapping(row.get("normalized")) or row
    suppressed = _whole_record_suppressed(normalized, row)
    privacy_reasons = _privacy_reasons(normalized, row)
    coordinate_review_reasons = _coordinate_review_reasons(normalized, row)

    source_latitude, source_longitude, source_present = _coordinate_from(normalized, row, source=True)
    source_valid = _valid_point(source_latitude, source_longitude)
    source_state = str(_first(normalized, "coordinate_state", "coordinate_gate") or "").lower()
    source_pending = source_present and not source_valid and "pending" in source_state
    source_invalid = source_present and not source_valid and not source_pending
    geocode_status, geocode_precision, geocode_valid = _geocode(normalized, row)
    accepted_geocode = geocode_status == "accepted" and geocode_valid
    geocode_exact = accepted_geocode and geocode_precision in _EXACT_PRECISIONS
    geocode_coarse = accepted_geocode and geocode_precision in _COARSE_PRECISIONS
    coarse_signal = (
        str(_first(normalized, "display_precision", "coordinate_precision", "coordinate_state") or "").lower() in _COARSE_PRECISIONS
        or str(_first(normalized, "display_precision", "coordinate_precision", "coordinate_state") or "").lower() in {"city", "coarse", "approximate"}
    )

    if suppressed:
        display_state = "restricted"
    elif source_valid or geocode_exact:
        display_state = "exact"
    elif geocode_coarse or coarse_signal or _city_present(normalized):
        display_state = "city"
    else:
        display_state = "unmapped"

    evidence = Counter()
    if source_valid:
        evidence["source_coordinate_valid"] += 1
    if source_invalid:
        evidence["source_coordinate_invalid"] += 1
    if source_pending:
        evidence["source_coordinate_pending_review"] += 1
    if geocode_exact:
        evidence["accepted_geocode_exact"] += 1
    elif geocode_coarse:
        evidence["accepted_geocode_coarse"] += 1
    elif geocode_status in {"unresolved", "failed", "review_required"} or not (source_valid or accepted_geocode):
        evidence["geocode_unresolved"] += 1
    if geocode_coarse or coarse_signal or (not source_valid and not accepted_geocode and _city_present(normalized)):
        evidence["coarse_city_location"] += 1
    if display_state == "unmapped":
        evidence["unresolved"] += 1

    identifier = _first(normalized, "establishment_id", "source_record_key", "source_id")
    return {
        "display_state": display_state,
        "suppressed": suppressed,
        "evidence": dict(evidence),
        "privacy_reasons": privacy_reasons,
        "coordinate_review_reasons": coordinate_review_reasons,
        "has_source_identifier": bool(identifier),
    }


def _resolve(path_value: str | None, root: Path) -> Path | None:
    if not path_value:
        return None
    path = Path(path_value)
    return path if path.is_absolute() else root / path


def _candidate_manifest_path(entry: dict[str, Any], root: Path) -> Path | None:
    for key in ("candidate_handoff_manifest", "private_manifest", "manifest"):
        resolved = _resolve(entry.get(key), root)
        if resolved and resolved.is_file():
            return resolved
    return None


def _normalized_path(entry: dict[str, Any], root: Path) -> tuple[Path | None, Path | None]:
    manifest_path = _candidate_manifest_path(entry, root)
    if manifest_path is None:
        return None, None
    manifest = _mapping(json.loads(manifest_path.read_text(encoding="utf-8")))
    explicit = _resolve(manifest.get("normalized_path"), root)
    candidates = [
        explicit,
        manifest_path.parent / "normalized" / "records.jsonl",
        manifest_path.parent / "normalized" / "normalized-records.jsonl",
    ]
    return next((candidate for candidate in candidates if candidate and candidate.is_file()), None), manifest_path


def _audit_file(path: Path) -> dict[str, Any]:
    evidence = Counter()
    display = Counter()
    privacy = Counter()
    coordinate_review = Counter()
    privacy_rows = 0
    coordinate_review_rows = 0
    suppressed_rows = 0
    records = identifiers = parse_errors = 0
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                parse_errors += 1
                continue
            if not isinstance(row, dict):
                parse_errors += 1
                continue
            records += 1
            result = classify_record(row)
            display[result["display_state"]] += 1
            suppressed_rows += int(result["suppressed"])
            evidence.update(result["evidence"])
            privacy.update(result["privacy_reasons"])
            coordinate_review.update(result["coordinate_review_reasons"])
            privacy_rows += bool(result["privacy_reasons"])
            coordinate_review_rows += bool(result["coordinate_review_reasons"])
            identifiers += int(result["has_source_identifier"])
    return {
        "available": True,
        "records": records,
        "parse_errors": parse_errors,
        "source_local_identifier_rows": identifiers,
        "suppressed_rows": suppressed_rows,
        "display_states": {state: display[state] for state in DISPLAY_STATES},
        "evidence_states": {state: evidence[state] for state in EVIDENCE_STATES},
        "privacy_review_queue": {"rows": privacy_rows, "by_reason": dict(sorted(privacy.items()))},
        "coordinate_review_queue": {"rows": coordinate_review_rows, "by_reason": dict(sorted(coordinate_review.items()))},
        "normalized_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "normalized_bytes": path.stat().st_size,
        "audit_status": "complete" if parse_errors == 0 else "incomplete_parse_errors",
    }


def _empty_unavailable(entry: dict[str, Any], declared_manifest: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "available": False,
        "records": None,
        "declared_normalized_rows": declared_manifest.get("normalized_rows") if declared_manifest else entry.get("normalized_rows"),
        "parse_errors": 0,
        "source_local_identifier_rows": None,
        "suppressed_rows": None,
        "display_states": None,
        "evidence_states": None,
        "privacy_review_queue": None,
        "coordinate_review_queue": None,
        "audit_status": "unavailable_private_handoff",
    }


def audit_current(manifest_path: Path, root: Path = Path("."), as_of: str | None = None) -> dict[str, Any]:
    """Audit every source listed by a current private-candidate manifest."""
    manifest = _mapping(json.loads(manifest_path.read_text(encoding="utf-8")))
    entries = manifest.get("sources")
    if not isinstance(entries, list):
        raise ValueError("current candidate manifest must contain a sources list")

    sources: list[dict[str, Any]] = []
    totals = Counter()
    unavailable = 0
    incomplete = 0
    for entry in sorted((item for item in entries if isinstance(item, dict)), key=lambda item: str(item.get("source_id", ""))):
        source_id = str(entry.get("source_id") or "unknown")
        normalized_path, handoff_manifest = _normalized_path(entry, root)
        if normalized_path is None:
            declared = None
            if handoff_manifest and handoff_manifest.is_file():
                declared = _mapping(json.loads(handoff_manifest.read_text(encoding="utf-8")))
            metrics = _empty_unavailable(entry, declared)
            unavailable += 1
        else:
            metrics = _audit_file(normalized_path)
            totals["records"] += metrics["records"]
            totals["parse_errors"] += metrics["parse_errors"]
            totals["source_local_identifier_rows"] += metrics["source_local_identifier_rows"]
            totals["suppressed_rows"] += metrics["suppressed_rows"]
            for key, value in metrics["display_states"].items():
                totals[f"display_{key}"] += value
            for key, value in metrics["evidence_states"].items():
                totals[f"evidence_{key}"] += value
            totals["privacy_review_rows"] += metrics["privacy_review_queue"]["rows"]
            totals["coordinate_review_rows"] += metrics["coordinate_review_queue"]["rows"]
            incomplete += metrics["audit_status"] != "complete"
        sources.append({
            "source_id": source_id,
            "country_code": entry.get("country_code"),
            "declared_input_rows": entry.get("input_rows"),
            "declared_normalized_rows": entry.get("normalized_rows"),
            "declared_quarantined_rows": entry.get("quarantined_rows"),
            "acquisition_state": entry.get("status") or entry.get("acquisition"),
            "publication_state": entry.get("publication_state") or "private-candidate",
            "metrics": metrics,
        })

    return {
        "report_version": REPORT_VERSION,
        "as_of_utc": as_of,
        "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "candidate_state": "private-only; no publication decision implied",
        "privacy_boundary": "aggregate-only; normalized rows, raw artifacts, addresses, coordinates, identifiers, and geocoder payloads are excluded",
        "sources_listed": len(sources),
        "sources_available": len(sources) - unavailable,
        "sources_unavailable": unavailable,
        "sources_with_parse_errors": incomplete,
        "totals_available_rows_only": dict(sorted(totals.items())),
        "sources": sources,
        "semantics": {
            "display_states": "Mutually exclusive current candidate display states; restricted takes precedence. Exact means a valid source point or accepted exact geocode, city means a declared city/coarse signal without an exact point, and unmapped means no displayable location evidence.",
            "evidence_states": "Overlapping evidence counters. A row may have source coordinates and a geocoder result; these counters intentionally preserve both facts.",
            "privacy_review_queue": "Conservative human-review indicators, not a residential determination or publication approval.",
            "coordinate_review_queue": "Rows needing coordinate/privacy review or explicitly unresolved coordinate handling; geocoding success alone never grants release eligibility.",
            "unavailable_sources": "A missing private handoff is not counted as zero and does not establish no coverage.",
        },
        "publication": {
            "release_created": False,
            "release_promoted": False,
            "public_api_rows": 0,
            "project_approval": "not-approved",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True, help="row-free current candidate manifest")
    parser.add_argument("--root", type=Path, default=Path("."), help="root used to resolve private staging paths")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--as-of", default=None)
    args = parser.parse_args()
    report = audit_current(args.manifest, args.root, args.as_of)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "sources_listed": report["sources_listed"],
        "sources_available": report["sources_available"],
        "available_rows": report["totals_available_rows_only"].get("records", 0),
        "privacy_review_rows": report["totals_available_rows_only"].get("privacy_review_rows", 0),
        "publication": report["publication"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
