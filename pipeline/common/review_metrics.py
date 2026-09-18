"""Row-free aggregate metrics shared by private source review packets."""
from __future__ import annotations

from collections import Counter
from typing import Any, Iterable


def _record(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    nested = value.get("record")
    return nested if isinstance(nested, dict) else value


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _normalized(row: dict[str, Any]) -> dict[str, Any]:
    value = row.get("normalized")
    return value if isinstance(value, dict) else row


def _facility_key(row: dict[str, Any]) -> str | None:
    normalized = _normalized(row)
    for field in ("facility_key", "facility_id", "recognition_number", "establishment_id"):
        value = _text(normalized.get(field))
        if value:
            return value
    # A source row key is a safe fallback for sources whose rows are already
    # facility observations; this does not assert a cross-source identity.
    return _text(row.get("source_record_key")) or _text(row.get("source_row_id"))


def _observation_key(row: dict[str, Any]) -> str | None:
    return _text(row.get("source_record_key")) or _text(row.get("source_row_id"))


def _coordinate_state(row: dict[str, Any]) -> str:
    normalized = _normalized(row)
    coordinates = normalized.get("coordinates")
    if isinstance(coordinates, (list, tuple)) and len(coordinates) == 2:
        try:
            lon, lat = float(coordinates[0]), float(coordinates[1])
            if -180 <= lon <= 180 and -90 <= lat <= 90 and not (lon == 0 and lat == 0):
                return "valid_point"
        except (TypeError, ValueError):
            pass
        return "invalid_point"
    if isinstance(coordinates, dict):
        latitude = coordinates.get("latitude")
        longitude = coordinates.get("longitude")
        if latitude not in (None, "") and longitude not in (None, ""):
            try:
                lat, lon = float(latitude), float(longitude)
                if -90 <= lat <= 90 and -180 <= lon <= 180 and not (lat == 0 and lon == 0):
                    method = _text(coordinates.get("method")) or "unknown"
                    return f"{method}_point"
            except (TypeError, ValueError):
                return "invalid_point"
        review_status = _text(coordinates.get("review_status"))
        if review_status:
            return review_status
    state = _text(normalized.get("coordinate_state"))
    if state:
        return state
    coordinate_gate = _text(normalized.get("coordinate_gate"))
    if coordinate_gate:
        return coordinate_gate
    return "missing"


def _classification_state(row: dict[str, Any]) -> tuple[str, str]:
    normalized = _normalized(row)
    classification = normalized.get("classification")
    if isinstance(classification, dict):
        return (
            _text(classification.get("review_status")) or "unknown",
            "present",
        )
    return (_text(normalized.get("classification_state")) or "unknown", "absent")


def _group_counts(rows: Iterable[dict[str, Any]], key_fn) -> tuple[int, int, int]:
    keys = [key_fn(row) for row in rows]
    present = [key for key in keys if key is not None]
    counts = Counter(present)
    return len(set(present)), sum(count > 1 for count in counts.values()), max(counts.values(), default=0)


def build_private_review_metrics(
    normalized_rows: Iterable[dict[str, Any]],
    quarantined_rows: Iterable[dict[str, Any]] = (),
) -> dict[str, Any]:
    """Summarize private rows without copying names, identifiers, or values.

    The metrics intentionally describe source-row observations separately from
    provisional facility grouping.  They are not identity resolution or
    publication approval.
    """
    accepted = [record for row in normalized_rows if (record := _record(row)) is not None]
    quarantined = [record for row in quarantined_rows if (record := _record(row)) is not None]
    all_rows = accepted + quarantined

    facility_count, repeated_facilities, max_rows_per_facility = _group_counts(all_rows, _facility_key)
    accepted_facilities, _, _ = _group_counts(accepted, _facility_key)
    observation_count, repeated_observations, _ = _group_counts(all_rows, _observation_key)

    classifications = Counter()
    classification_presence = Counter()
    coordinate_states = Counter()
    coordinate_precision = Counter()
    coordinate_gates = Counter()
    status_states = Counter()
    for row in all_rows:
        normalized = _normalized(row)
        classification_state, presence = _classification_state(row)
        classifications[classification_state] += 1
        classification_presence[presence] += 1
        coordinate_states[_coordinate_state(row)] += 1
        precision = _text(normalized.get("geography_precision")) or _text(normalized.get("coordinate_precision"))
        coordinate_precision[precision or ("point-precision-unknown" if _coordinate_state(row) == "valid_point" else "unresolved")] += 1
        coordinate_gates[_text(normalized.get("coordinate_gate")) or "not-specified"] += 1
        status_states[_text(normalized.get("status_state")) or "not-specified"] += 1

    return {
        "schema_version": "private-review-metrics-v1",
        "facility_observation": {
            "source_row_unit": "source observation",
            "input_observations": len(all_rows),
            "accepted_observations": len(accepted),
            "quarantined_observations": len(quarantined),
            "distinct_provisional_facility_keys": facility_count,
            "accepted_distinct_provisional_facility_keys": accepted_facilities,
            "distinct_observation_keys": observation_count,
            "repeated_provisional_facility_groups": repeated_facilities,
            "repeated_observation_keys": repeated_observations,
            "max_observations_per_provisional_facility": max_rows_per_facility,
            "identity_semantics": "source-scoped provisional grouping only; no canonical merge",
            "disappearance_semantics": "not-observed; never inferred as closure",
        },
        "classification": {
            "rows": len(all_rows),
            "review_state_counts": dict(sorted(classifications.items())),
            "field_presence": dict(sorted(classification_presence.items())),
            "status_state_counts": dict(sorted(status_states.items())),
            "interpretation": "source classifications remain separate from project approval",
        },
        "geospatial": {
            "coordinate_state_counts": dict(sorted(coordinate_states.items())),
            "precision_counts": dict(sorted(coordinate_precision.items())),
            "coordinate_gate_counts": dict(sorted(coordinate_gates.items())),
            "interpretation": "coordinate presence and precision do not establish privacy eligibility or publication approval",
        },
    }
