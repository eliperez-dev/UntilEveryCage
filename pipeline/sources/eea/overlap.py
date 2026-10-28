"""Bounded cross-source overlap screening, never an automatic facility merge."""
from __future__ import annotations

from collections import Counter, defaultdict
import math
import unicodedata


def name_key(value: str | None) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", value or "").casefold() if c.isalnum())


def distance_m(a, b) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    term = math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 12742000 * math.asin(min(1, math.sqrt(term)))


def screen(incoming, existing, *, radius_m: float = 250) -> dict:
    """Input (country, name, latitude, longitude); return counts only.

    A nearby point or shared company name is not sufficient identity evidence.
    The result identifies review candidates and does not remove or merge rows.
    """
    if not 0 < radius_m <= 1000:
        raise ValueError("overlap screening radius must be between zero and 1000m")
    grid, names, countries = defaultdict(list), set(), set()
    for country, name, lat, lon in existing:
        countries.add(country)
        key = name_key(name)
        if key:
            names.add((country, key))
        if lat is not None and lon is not None:
            grid[(country, math.floor(lat*100), math.floor(lon*100))].append((key, lat, lon))
    shared_name = nearby = shared_name_nearby = mapped = 0
    country_counts = Counter()
    for country, name, lat, lon in incoming:
        country_counts[country] += 1
        key = name_key(name)
        shared_name += bool(key and (country, key) in names)
        if lat is None or lon is None:
            continue
        mapped += 1
        y, x = math.floor(lat*100), math.floor(lon*100)
        # Longitude cells narrow with latitude; never miss the adjacent band.
        dy = math.ceil(radius_m / 1100)
        dx = math.ceil(radius_m / (1100 * max(.01, math.cos(math.radians(lat)))))
        neighbors = [point for oy in range(-dy, dy+1) for ox in range(-dx, dx+1)
                     for point in grid.get((country, y+oy, x+ox), [])
                     if distance_m((lat, lon), (point[1], point[2])) <= radius_m]
        nearby += bool(neighbors)
        shared_name_nearby += bool(key and any(key == point[0] for point in neighbors))
    new_countries = sorted(set(country_counts) - countries)
    return {"screening_radius_m": radius_m, "incoming_records": sum(country_counts.values()),
            "incoming_mapped": mapped, "country_count": len(country_counts),
            "countries_absent_from_comparison_release": new_countries,
            "records_in_absent_countries": sum(country_counts[c] for c in new_countries),
            "shared_normalized_name_in_same_country": shared_name,
            "near_existing_point": nearby, "shared_name_and_near_existing_point": shared_name_nearby,
            "mapped_without_nearby_comparison_point": mapped-nearby,
            "automatic_merges": 0, "unique_physical_site_count": "not_established"}
