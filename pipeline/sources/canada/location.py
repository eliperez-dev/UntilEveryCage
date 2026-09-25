"""Exact-match, local-only Canadian locality reference resolution."""
from __future__ import annotations

import unicodedata


def _normalize(value: object) -> str:
    folded = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return " ".join("".join(ch if ch.isalnum() else " " for ch in folded).split())


def resolve_local_reference(city: object, postal_code: object, references: list[dict]) -> dict | None:
    """Return a unique verified local reference; never estimate a point."""
    city_key = _normalize(city)
    postal_key = "".join(str(postal_code or "").upper().split())
    if not city_key and not postal_key:
        return None
    matches = []
    for row in references:
        if row.get("country_code") != "CA" or not row.get("reference_source") or not row.get("source_reference_id"):
            continue
        ref_postal = "".join(str(row.get("postal_code") or "").upper().split())
        if city_key and _normalize(row.get("city_name")) != city_key:
            continue
        if postal_key and ref_postal != postal_key:
            continue
        if not city_key and not ref_postal:
            continue
        if row.get("reference_latitude") is None or row.get("reference_longitude") is None:
            continue
        matches.append(row)
    if len(matches) != 1:
        return None
    match = matches[0]
    latitude, longitude = match["reference_latitude"], match["reference_longitude"]
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180) or (latitude == 0 and longitude == 0):
        return None
    return {"latitude": latitude, "longitude": longitude,
            "precision": "locality_reference_coarse",
            "source": match["reference_source"],
            "source_reference_id": match["source_reference_id"]}
