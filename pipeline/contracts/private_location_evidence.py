"""Private, allow-listed location evidence shared by adapters and handoffs.

Only facility-location fields enter this projection. Contact details and named
people are deliberately outside the contract. The resulting object is stored
in the private preview evidence layer and is never a publication projection.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


LOCATION_ALIASES: dict[str, tuple[str, ...]] = {
    "address": ("address", "street_address", "street", "address_line", "address_line_1", "address_line_2", "address_line_3", "address_line_4", "address1", "address2", "address3", "address4", "physical_address", "establishment_address", "logradouro", "adre_a", "adresse"),
    "city": ("city", "municipality", "locality", "town", "suburb", "municipi", "localidad", "ort", "plaats", "commune"),
    "postal_code": ("postal_code", "postcode", "post_code", "zip", "zip_code", "postal", "codi_postal", "cep", "post_code"),
    "region": ("region", "province", "state", "department", "county", "autonomous_community", "comarca", "uf", "prov_ncia", "provincia"),
    "country_code": ("country_code", "country", "nation"),
}


def _nonempty(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (tuple, list)):
        return any(_nonempty(item) for item in value)
    return value is not None


def _first(mapping: Mapping[str, Any], aliases: tuple[str, ...]) -> Any:
    normalized_keys = {str(key).strip().lower().replace("-", "_").replace(" ", "_"): key for key in mapping}
    for alias in aliases:
        key = normalized_keys.get(alias)
        if key is not None and _nonempty(mapping[key]):
            return mapping[key]
    return None


def project_private_location_evidence(record: Mapping[str, Any]) -> dict[str, Any]:
    """Project source/normalized location fields, excluding all contact fields."""
    normalized = record.get("normalized")
    normalized = normalized if isinstance(normalized, Mapping) else {}
    explicit_private = normalized.get("private_location_evidence")
    explicit_private = explicit_private if isinstance(explicit_private, Mapping) else {}
    withheld = (str(_first(normalized, ("address_withheld",)) or "").strip().lower()
                in {"yes", "true", "1", "withheld"}
                or normalized.get("privacy_gate") == "restricted-withheld-address"
                or normalized.get("coordinate_gate") == "restricted-withheld-address")
    # Source semantics belong in normalized fields or the explicit private
    # projection; arbitrary raw columns may describe contact/correspondence.
    result: dict[str, Any] = {}
    for canonical, aliases in LOCATION_ALIASES.items():
        if withheld and canonical in {"address", "city", "postal_code", "region"}:
            continue
        value = _first(normalized, aliases)
        if value is None:
            value = explicit_private.get(canonical)
        if value is not None:
            result[canonical] = value
    for key in ("address", "address_lines", "city", "postal_code", "region", "country_code", "municipality_code", "comarca_code", "department_number", "region_code"):
        value = explicit_private.get(key)
        if key not in result and _nonempty(value) and not (
            withheld and key in {"address", "address_lines", "city", "postal_code", "region"}
        ):
            result[key] = value
    lines = result.get("address_lines")
    if isinstance(lines, (list, tuple)):
        normalized_lines = [" ".join(str(line).split()) for line in lines if _nonempty(line)]
        if normalized_lines:
            result["address_lines"] = normalized_lines
            if not isinstance(result.get("address"), str) or not result["address"].strip():
                result["address"] = ", ".join(normalized_lines)

    coordinates = normalized.get("coordinates")
    private_coordinates = explicit_private.get("coordinates")
    # Preserve source-reported axes as evidence only. They are not WGS84
    # coordinates and must never be projected into display geometry here.
    if (not withheld and isinstance(private_coordinates, Mapping)
            and _nonempty(private_coordinates.get("x")) and _nonempty(private_coordinates.get("y"))):
        result["coordinates"] = {
            "x": private_coordinates["x"], "y": private_coordinates["y"],
            "axis_labels": private_coordinates.get("axis_labels"),
            "coordinate_reference_system": private_coordinates.get("coordinate_reference_system", "unverified"),
            "precision": private_coordinates.get("precision", "unverified-source-semantics"),
        }
    if (not withheld and isinstance(private_coordinates, Mapping)
            and _nonempty(private_coordinates.get("latitude")) and _nonempty(private_coordinates.get("longitude"))):
        result["coordinates"] = {"latitude": private_coordinates["latitude"],
                                  "longitude": private_coordinates["longitude"],
                                  "precision": private_coordinates.get("precision")}
    if ("coordinates" not in result and not withheld and isinstance(coordinates, Mapping)
            and _nonempty(coordinates.get("latitude")) and _nonempty(coordinates.get("longitude"))):
        result["coordinates"] = {
            "latitude": coordinates["latitude"],
            "longitude": coordinates["longitude"],
            "precision": coordinates.get("precision") or normalized.get("coordinate_precision"),
        }
    elif "coordinates" not in result and not withheld:
        latitude = _first(normalized, ("latitude", "lat", "latitudine"))
        longitude = _first(normalized, ("longitude", "lon", "lng", "longitudine"))
        if latitude is not None or longitude is not None:
            result["coordinates"] = {
                **({"latitude": latitude} if latitude is not None else {}),
                **({"longitude": longitude} if longitude is not None else {}),
                "precision": normalized.get("coordinate_precision"),
            }
    for key in ("municipality_code", "comarca_code", "department_number", "region_code"):
        value = normalized.get(key)
        if _nonempty(value):
            result[key] = value
    return result


def attach_private_location_evidence(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach the location-only projection before any raw values are minimized."""
    projected_rows: list[dict[str, Any]] = []
    for row in rows:
        copied = dict(row)
        normalized = row.get("normalized")
        if not isinstance(normalized, Mapping):
            raise ValueError("candidate row normalized data must be an object")
        normalized_copy = dict(normalized)
        location = project_private_location_evidence(row)
        if location:
            normalized_copy["private_location_evidence"] = location
        copied["normalized"] = normalized_copy
        projected_rows.append(copied)
    return projected_rows
