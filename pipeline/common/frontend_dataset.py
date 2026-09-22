"""Reproducible V2 frontend development datasets.

This module deliberately has no database or application dependencies.  It
produces row-shaped, synthetic data for local UI work and aggregate-only
metadata for an explicitly supplied private source manifest.  Private source
rows and retained artifacts are never copied into the repository.

The output directory is a launchpad boundary:

* ``locations.jsonl`` contains facility-shaped rows for the selected mode;
* ``graph_edges.jsonl`` contains development graph rows (never a public
  release); and
* ``public_projection.json`` is intentionally empty until a release builder
  explicitly selects eligible rows.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterable, Mapping


SCHEMA_VERSION = "e1-frontend-development-dataset-v1"
SEED = 20260921
ALLOWED_PRIVATE_SOURCES = (
    "dk.smiley",
    "fr.dgal.section-i",
    "fr.dgal.section-ii",
    "it.853-2004",
    "us.fsis",
)
COUNTRY_BY_SOURCE = {
    "dk.smiley": "DK",
    "fr.dgal.section-i": "FR",
    "fr.dgal.section-ii": "FR",
    "it.853-2004": "IT",
    "us.fsis": "US",
}


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> int:
    count = 0
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(_json(dict(row)) + "\n")
            count += 1
    return count


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _stable_id(prefix: str, index: int) -> str:
    return f"{prefix}-{index:07d}"


def _base_row(index: int, *, country: str, source: str, rng: random.Random) -> dict[str, Any]:
    cities = {
        "US": [("Chicago", 41.8781, -87.6298), ("Kansas City", 39.0997, -94.5786), ("Fresno", 36.7378, -119.7871)],
        "FR": [("Paris", 48.8566, 2.3522), ("Lyon", 45.7640, 4.8357), ("Toulouse", 43.6047, 1.4442)],
        "IT": [("Milan", 45.4642, 9.1900), ("Bologna", 44.4949, 11.3426), ("Rome", 41.9028, 12.4964)],
        "DK": [("Copenhagen", 55.6761, 12.5683), ("Aarhus", 56.1629, 10.2039), ("Odense", 55.4038, 10.4024)],
        "CA": [("Toronto", 43.6532, -79.3832), ("Calgary", 51.0447, -114.0719), ("Montreal", 45.5017, -73.5673)],
        "DE": [("Berlin", 52.5200, 13.4050), ("Hamburg", 53.5511, 9.9937), ("Munich", 48.1351, 11.5820)],
        "AU": [("Melbourne", -37.8136, 144.9631), ("Sydney", -33.8688, 151.2093), ("Perth", -31.9505, 115.8605)],
        "BR": [("Sao Paulo", -23.5505, -46.6333), ("Curitiba", -25.4284, -49.2733), ("Goiania", -16.6869, -49.2648)],
    }
    city, city_lat, city_lon = rng.choice(cities[country])
    mode = rng.choices(("exact", "city", "coarse", "unmapped"), weights=(58, 20, 10, 12), k=1)[0]
    cluster = rng.random() < 0.7
    # The coordinate is source-like data, not a geocoding claim.  A city or
    # coarse row deliberately has only a display centroid, never exact source
    # coordinates.
    lat = city_lat + rng.gauss(0, 0.09 if cluster else 1.4)
    lon = city_lon + rng.gauss(0, 0.12 if cluster else 1.8)
    coords = {"latitude": round(lat, 6), "longitude": round(lon, 6)} if mode == "exact" else None
    display = {"latitude": round(lat, 4), "longitude": round(lon, 4)} if mode in {"exact", "city", "coarse"} else None
    if mode == "city":
        display = {"latitude": city_lat, "longitude": city_lon}
    elif mode == "coarse":
        display = {"latitude": round(city_lat + rng.gauss(0, 0.8), 2), "longitude": round(city_lon + rng.gauss(0, 0.8), 2)}
    categories = ("slaughter", "processing", "farm", "laboratory", "breeder", "dealer", "inspection")
    lifecycle = rng.choice(("active", "historical", "unknown", "temporarily_closed"))
    freshness = rng.choice(("current", "current", "stale", "historical", "unknown"))
    access = rng.choices(("eligible", "restricted", "suppressed"), weights=(84, 10, 6), k=1)[0]
    return {
        "facility_id": _stable_id("facility", index),
        "source_id": source,
        "source_record_id": f"{source.replace('.', '-')}-{index:08d}",
        "name": f"{city} {categories[index % len(categories)].title()} {index:05d}",
        "country_code": country,
        "city": city,
        "category": categories[index % len(categories)],
        "species": [rng.choice(("cattle", "pigs", "poultry", "sheep", "laboratory_animals"))],
        "activities": [categories[index % len(categories)]],
        "lifecycle_status": lifecycle,
        "source_freshness": freshness,
        "coordinate_state": mode,
        "coordinate_precision": {"exact": "facility", "city": "city", "coarse": "region", "unmapped": "none"}[mode],
        "coordinates": coords,
        "display_centroid": display,
        "map_render_hint": {"exact": "point", "city": "area", "coarse": "area", "unmapped": "list_only"}[mode],
        "provenance": {"source_origin": "synthetic_development", "source_record_id": f"{source.replace('.', '-')}-{index:08d}", "retrieved_at": "2026-09-21T00:00:00Z"},
        "access_state": access,
        "release_profile": "development_private",
    }


def representative_rows(seed: int = SEED) -> list[dict[str, Any]]:
    """Return a compact deterministic corpus covering every frontend state."""
    rng = random.Random(seed)
    source_countries = (("us.fsis", "US"), ("fr.dgal.section-i", "FR"), ("it.853-2004", "IT"), ("dk.smiley", "DK"), ("ca.demo", "CA"), ("de.demo", "DE"))
    rows: list[dict[str, Any]] = []
    for index in range(96):
        source, country = source_countries[index % len(source_countries)]
        rows.append(_base_row(index, country=country, source=source, rng=rng))
    # Explicit stable controls ensure that a random distribution cannot lose a
    # required UI state in a future edit.
    rows[0]["coordinate_state"], rows[0]["coordinates"] = "exact", {"latitude": 41.8781, "longitude": -87.6298}
    rows[1]["coordinate_state"], rows[1]["coordinates"], rows[1]["display_centroid"] = "city", None, {"latitude": 48.8566, "longitude": 2.3522}
    rows[2]["coordinate_state"], rows[2]["coordinates"], rows[2]["display_centroid"] = "coarse", None, {"latitude": 45.0, "longitude": 9.0}
    rows[3]["coordinate_state"], rows[3]["coordinates"], rows[3]["display_centroid"] = "unmapped", None, None
    rows[4]["access_state"] = "restricted"
    rows[5]["access_state"] = "suppressed"
    rows[6]["source_freshness"] = "stale"
    rows[7]["lifecycle_status"] = "historical"
    return rows


def representative_edges(rows: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    endpoints = [str(row["facility_id"]) for row in rows]
    edges = [
        {"edge_id": "edge-exact-0001", "from_facility_id": endpoints[0], "to_facility_id": endpoints[8], "connection_type": "exact", "confidence": {"level": "high", "score": 1.0}, "signals": ["shared_authoritative_source_id"], "contradictions": [], "disclaimer": "Exact source assertion; not a universal identity merge."},
        {"edge_id": "edge-inferred-high-0001", "from_facility_id": endpoints[1], "to_facility_id": endpoints[9], "connection_type": "inferred", "confidence": {"level": "high", "score": 0.91}, "signals": ["normalized_name", "city", "shared_operator_identifier"], "contradictions": [], "disclaimer": "Algorithmic estimate; inspect the listed evidence before treating it as a fact."},
        {"edge_id": "edge-inferred-medium-0001", "from_facility_id": endpoints[2], "to_facility_id": endpoints[10], "connection_type": "inferred", "confidence": {"level": "medium", "score": 0.62}, "signals": ["normalized_name", "postal_area"], "contradictions": [], "disclaimer": "Algorithmic estimate; medium confidence is not confirmation."},
        {"edge_id": "edge-inferred-low-0001", "from_facility_id": endpoints[3], "to_facility_id": endpoints[11], "connection_type": "inferred", "confidence": {"level": "low", "score": 0.28}, "signals": ["similar_name"], "contradictions": ["different_activity"], "disclaimer": "Low-confidence algorithmic estimate; shown for transparent filtering, not as a fact."},
        {"edge_id": "edge-conflicting-0001", "from_facility_id": endpoints[4], "to_facility_id": endpoints[12], "connection_type": "inferred", "confidence": {"level": "low", "score": 0.19}, "signals": ["name_fragment"], "contradictions": ["conflicting_source_identifier", "different_city"], "disclaimer": "Conflicting evidence is retained and explicitly labeled."},
    ]
    return edges


def ui_states() -> dict[str, Any]:
    return {
        "schema_version": "e1-ui-state-matrix-v1",
        "network": ["loading", "empty", "not_found_404", "rate_limited_429", "unavailable_503", "stale_success"],
        "location": ["exact", "city_approximate", "coarse_region", "unmapped", "restricted", "suppressed"],
        "graph": ["exact_high", "inferred_high", "inferred_medium", "inferred_low", "conflicting", "no_connections", "paginated"],
        "performance": ["dense_urban_cluster", "sparse_rural", "overlapping_points", "large_viewport", "large_table", "cursor_page_boundary"],
        "release": {"profile": "development_private", "public_projection_rows": 0, "public_projection_edges": 0},
    }


def performance_rows(count: int, seed: int = SEED) -> Iterable[dict[str, Any]]:
    if count < 100_000:
        raise ValueError("performance corpus must contain at least 100000 facilities")
    rng = random.Random(seed)
    distributions = (("US", "us.synthetic", 24), ("IT", "it.synthetic", 28), ("FR", "fr.synthetic", 18), ("DK", "dk.synthetic", 8), ("CA", "ca.synthetic", 8), ("BR", "br.synthetic", 6), ("AU", "au.synthetic", 5), ("DE", "de.synthetic", 3))
    buckets = [(country, source) for country, source, weight in distributions for _ in range(weight)]
    for index in range(count):
        country, source = buckets[index % len(buckets)]
        yield _base_row(index, country=country, source=source, rng=rng)


def performance_edges(count: int, facility_count: int, seed: int = SEED) -> Iterable[dict[str, Any]]:
    if count < 100_000:
        raise ValueError("performance graph must contain at least 100000 edges")
    rng = random.Random(seed + 17)
    levels = (("high", 0.86), ("medium", 0.58), ("low", 0.24))
    for index in range(count):
        level, score = levels[index % len(levels)]
        left = rng.randrange(facility_count)
        right = (left + 1 + rng.randrange(max(1, facility_count - 1))) % facility_count
        yield {
            "edge_id": _stable_id("perf-edge", index),
            "from_facility_id": _stable_id("facility", left),
            "to_facility_id": _stable_id("facility", right),
            "connection_type": "exact" if index % 13 == 0 else "inferred",
            "confidence": {"level": "high" if index % 13 == 0 else level, "score": 1.0 if index % 13 == 0 else score},
            "signals": ["shared_source_id"] if index % 13 == 0 else ["normalized_name", "city", "source_identifier_fragment"],
            "contradictions": ["different_activity"] if index % 29 == 0 else [],
            "disclaimer": "Development-only graph row; exact and inferred semantics remain distinct.",
        }


def _manifest(files: Mapping[str, Path], *, mode: str, facility_count: int, edge_count: int, seed: int, source_inventory: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "dataset_id": f"e1-{mode}",
        "mode": mode,
        "deterministic_seed": seed,
        "private_payloads_included": mode == "private",
        "public_projection": {"facility_rows": 0, "graph_edges": 0, "release_id": None, "status": "empty_until_explicit_public_release"},
        "files": {name: {"path": path.name, "sha256": _sha256(path), "bytes": path.stat().st_size} for name, path in sorted(files.items())},
        "counts": {"facilities": facility_count, "graph_edges": edge_count},
        "source_inventory": source_inventory or [],
        "ui_state_matrix": "ui_states.json",
        "guarantees": [
            "rows are synthetic unless mode=private is explicitly requested with an authorized local manifest",
            "source-qualified identifiers are never universal identity merges",
            "coordinate_state distinguishes exact, city, coarse, and unmapped values",
            "inferred graph rows expose confidence, signals, contradictions, and disclaimers",
            "no private paths, raw artifacts, addresses, credentials, or release claims are recorded",
        ],
    }


def _private_inventory(path: Path) -> list[dict[str, Any]]:
    document = json.loads(path.read_text(encoding="utf-8"))
    inventory: list[dict[str, Any]] = []
    for source in document.get("sources", []):
        source_id = source.get("source_id")
        if source_id not in ALLOWED_PRIVATE_SOURCES:
            continue
        inventory.append({
            "source_id": source_id,
            "country_code": COUNTRY_BY_SOURCE[source_id],
            "input_rows": source.get("input_rows", 0),
            "normalized_rows": source.get("normalized_rows", 0),
            "quarantined_rows": source.get("quarantined_rows", 0),
            "status": str(source.get("status", "unknown")).split(";")[0],
            "semantic_use": "private-development-only; source observation semantics preserved",
        })
    return sorted(inventory, key=lambda item: item["source_id"])


def build(output_dir: str | Path, *, mode: str, seed: int = SEED, performance_count: int = 100_000, edge_count: int = 150_000, private_manifest: str | Path | None = None) -> dict[str, Any]:
    """Build a dataset and return its row-free manifest."""
    if mode not in {"representative", "performance", "private"}:
        raise ValueError("mode must be representative, performance, or private")
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    files: dict[str, Path] = {}
    if mode == "representative":
        rows = representative_rows(seed)
        facilities = out / "locations.jsonl"
        edges = out / "graph_edges.jsonl"
        _write_jsonl(facilities, rows)
        _write_jsonl(edges, representative_edges(rows))
        files.update({"locations": facilities, "graph_edges": edges})
        facility_count, edge_count_actual = len(rows), len(representative_edges(rows))
        inventory = [{"source_id": source, "country_code": country, "rows": sum(row["source_id"] == source for row in rows), "status": "synthetic"} for source, country in (("us.fsis", "US"), ("fr.dgal.section-i", "FR"), ("it.853-2004", "IT"), ("dk.smiley", "DK"), ("ca.demo", "CA"), ("de.demo", "DE"))]
    elif mode == "performance":
        facilities = out / "locations.jsonl"
        edges = out / "graph_edges.jsonl"
        _write_jsonl(facilities, performance_rows(performance_count, seed))
        _write_jsonl(edges, performance_edges(edge_count, performance_count, seed))
        files.update({"locations": facilities, "graph_edges": edges})
        facility_count, edge_count_actual, inventory = performance_count, edge_count, [{"source_id": "*.synthetic", "rows": performance_count, "status": "synthetic_performance"}]
    else:
        if private_manifest is None:
            raise ValueError("private mode requires --private-manifest pointing to an authorized local row-free manifest")
        inventory = _private_inventory(Path(private_manifest))
        facilities = out / "locations.jsonl"
        edges = out / "graph_edges.jsonl"
        # The private database is consumed by an explicit launchpad/database
        # handoff.  This mode emits no private rows and cannot accidentally
        # turn retained research data into a checked-in fixture.
        facilities.write_text("", encoding="utf-8")
        edges.write_text("", encoding="utf-8")
        files.update({"locations": facilities, "graph_edges": edges})
        facility_count = sum(int(item.get("normalized_rows", 0)) for item in inventory)
        edge_count_actual = 0
    states = out / "ui_states.json"
    _write_json(states, ui_states())
    files["ui_states"] = states
    public = out / "public_projection.json"
    _write_json(public, {"facilities": [], "graph_edges": [], "status": "empty_until_explicit_public_release"})
    files["public_projection"] = public
    manifest = _manifest(files, mode=mode, facility_count=facility_count, edge_count=edge_count_actual, seed=seed, source_inventory=inventory)
    manifest_path = out / "manifest.json"
    _write_json(manifest_path, manifest)
    return manifest


def validate(output_dir: str | Path, *, require_performance: bool = False) -> dict[str, Any]:
    """Validate a generated dataset without exposing rows in the result."""
    out = Path(output_dir)
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    locations = out / "locations.jsonl"
    edges = out / "graph_edges.jsonl"
    location_rows = [json.loads(line) for line in locations.read_text(encoding="utf-8").splitlines() if line.strip()]
    edge_rows = [json.loads(line) for line in edges.read_text(encoding="utf-8").splitlines() if line.strip()]
    failures: list[str] = []
    required_states = {row.get("coordinate_state") for row in location_rows}
    for state in ("exact", "city", "coarse", "unmapped"):
        if manifest["mode"] != "private" and state not in required_states:
            failures.append(f"missing coordinate state: {state}")
    if require_performance and len(location_rows) < 100_000:
        failures.append("performance corpus has fewer than 100000 facilities")
    if manifest.get("public_projection", {}).get("facility_rows") != 0 or manifest.get("public_projection", {}).get("graph_edges") != 0:
        failures.append("public projection is not empty")
    ids = {row.get("facility_id") for row in location_rows}
    if any(edge.get("from_facility_id") not in ids or edge.get("to_facility_id") not in ids for edge in edge_rows):
        failures.append("graph edge endpoint is not present in locations")
    levels = {edge.get("confidence", {}).get("level") for edge in edge_rows if edge.get("connection_type") == "inferred"}
    if manifest["mode"] != "private" and not {"high", "medium", "low"}.issubset(levels):
        failures.append("inferred graph does not cover high, medium, and low confidence")
    for name, info in manifest.get("files", {}).items():
        path = out / info["path"]
        if not path.is_file() or _sha256(path) != info["sha256"]:
            failures.append(f"digest mismatch: {name}")
    return {"ok": not failures, "dataset_id": manifest.get("dataset_id"), "mode": manifest.get("mode"), "facilities": len(location_rows), "graph_edges": len(edge_rows), "failures": failures}

