#!/usr/bin/env python3
"""Build private, release-scoped MVT artifacts before public promotion."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import sys

import psycopg

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from pipeline.scripts.maintenance import build_public_discovery_read_model as discovery
from pipeline.common.source_rights import require_cleared


MIN_ZOOM = 0
MAX_ZOOM = 14
SOURCE_LAYER = "uec_map"
FEATURE_SCHEMA_VERSION = "uec-map-feature-v2"
FEATURE_PROPERTIES = ["feature_key", "kind", "count", "exact_count", "coarse_count", "next_zoom", "record_id", "category_key", "category_keys_compact"]
TAXONOMY_KEYS = ("animal_keeping_and_production", "slaughter", "processing_and_preparation", "research_and_animal_use", "other_regulated_premises", "unclassified")


def compact_category_keys(keys: list[str] | tuple[str, ...] | None) -> str:
    """Encode validated whole taxonomy keys for MVT string-only properties."""
    selected = sorted({key for key in (keys or ()) if key in TAXONOMY_KEYS})
    if not selected:
        selected = ["unclassified"]
    return "|" + "|".join(selected) + "|"


def compact_category_keys_match(encoded: str | None, key: str) -> bool:
    """Match complete delimiter-bounded keys; never use substring matching."""
    return key in TAXONOMY_KEYS and f"|{key}|" in (encoded or "")
TILE_BUCKET = 512
POINT_RE = re.compile(r"^POINT\s*\(\s*(-?[0-9.]+)\s+(-?[0-9.]+)\s*\)$", re.I)


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _mercator_y(latitude: float) -> float:
    latitude = min(85.05112878, max(-85.05112878, latitude))
    radians = math.radians(latitude)
    return (1.0 - math.asinh(math.tan(radians)) / math.pi) / 2.0


def tile_xy(longitude: float, latitude: float, zoom: int) -> tuple[int, int]:
    count = 1 << zoom
    x = min(count - 1, max(0, int((longitude + 180.0) / 360.0 * count)))
    y = min(count - 1, max(0, int(_mercator_y(latitude) * count)))
    return x, y


def _point(wkt: str | None) -> tuple[float, float] | None:
    if not wkt:
        return None
    match = POINT_RE.match(wkt.strip())
    if not match:
        raise ValueError("public map projection contains an unsupported geometry")
    longitude, latitude = map(float, match.groups())
    if not math.isfinite(longitude) or not math.isfinite(latitude):
        raise ValueError("public map projection contains a non-finite coordinate")
    if not (-180 <= longitude <= 180 and -90 <= latitude <= 90):
        raise ValueError("public map projection contains an invalid coordinate")
    if longitude == 0 and latitude == 0:
        raise ValueError("public map projection contains an unusable zero coordinate")
    return longitude, latitude


def _feature_key(release_id: str, profile: str, zoom: int, bucket_x: int, bucket_y: int, kind: str, identity: str = "") -> str:
    value = f"{release_id}\0{profile}\0{zoom}\0{bucket_x}\0{bucket_y}\0{kind}\0{identity}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]


def hierarchy_features(release_id: str, profile: str, facilities: list[dict[str, Any]], max_zoom: int = MAX_ZOOM) -> dict[tuple[int, int, int], list[dict[str, Any]]]:
    """Return deterministic tile features, keeping exact and coarse groups separate."""
    tiles: dict[tuple[int, int, int], list[dict[str, Any]]] = {}
    for zoom in range(MIN_ZOOM, max_zoom + 1):
        groups: dict[tuple[int, int, str, str], list[dict[str, Any]]] = {}
        count = 1 << zoom
        for facility in facilities:
            lon, lat, kind = facility["longitude"], facility["latitude"], facility["kind"]
            if kind not in ("exact", "coarse"):
                raise ValueError("map feature kind must be exact or coarse")
            gx = int((lon + 180.0) / 360.0 * count * 4096)
            gy = int(_mercator_y(lat) * count * 4096)
            bx, by = (gx // TILE_BUCKET, gy // TILE_BUCKET) if zoom < max_zoom else (gx, gy)
            identity = facility["record_id"] if zoom == max_zoom and kind == "exact" else ""
            groups.setdefault((bx, by, kind, identity), []).append(facility)
        for (bx, by, kind, identity), members in groups.items():
            zoom_bucket = TILE_BUCKET if zoom < max_zoom else 1
            gx, gy = (bx + 0.5) * zoom_bucket, (by + 0.5) * zoom_bucket
            lon = gx / (count * 4096) * 360.0 - 180.0
            mercator = math.pi * (1.0 - 2.0 * gy / (count * 4096))
            lat = math.degrees(math.atan(math.sinh(mercator)))
            if zoom == max_zoom and kind == "exact":
                lon, lat = members[0]["longitude"], members[0]["latitude"]
            x, y = tile_xy(lon, lat, zoom)
            clustered = len(members) > 1 and zoom < max_zoom
            feature = {
                "longitude": lon,
                "latitude": lat,
                "feature_key": _feature_key(release_id, profile, zoom, bx, by, kind, identity),
                "kind": "cluster" if clustered else kind,
                "count": len(members),
                "exact_count": len(members) if kind == "exact" else 0,
                "coarse_count": len(members) if kind == "coarse" else 0,
                "next_zoom": zoom + 1 if clustered else None,
                "record_id": members[0]["record_id"] if kind == "exact" and not clustered else None,
                # Coarse locations, density clusters, and grouped exact records
                # are geographic context, not category-filtered counts.
                "category_key": members[0]["category_key"] if kind == "exact" and not clustered else None,
                "category_keys_compact": members[0].get("category_keys_compact", compact_category_keys([members[0].get("category_key")])) if kind == "exact" and not clustered else None,
            }
            tiles.setdefault((zoom, x, y), []).append(feature)
    return tiles


def build(database_url: str, release_id: str, output_root: Path) -> dict[str, Any]:
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,160}", release_id) or release_id in (".", ".."):
        raise ValueError("release ID is not a safe artifact path component")
    output_root.mkdir(parents=True, exist_ok=True)
    final_release_dir = output_root / release_id
    if final_release_dir.exists():
        raise ValueError("release map artifact directory already exists")
    staging_dir = Path(tempfile.mkdtemp(prefix=".uec-map-staging-", dir=output_root))
    staged_release_dir = staging_dir / release_id
    with psycopg.connect(database_url) as connection, connection.transaction():
        release = connection.execute(
            "SELECT status, test_only, profile FROM uec.releases WHERE release_id=%s FOR SHARE",
            (release_id,),
        ).fetchone()
        if not release or release[0] != "validated" or release[1]:
            raise ValueError("map artifacts require a validated non-test prepromotion release")
        profile = release[2]
        require_cleared(connection, release_id)
        generation = connection.execute(
            "SELECT generation FROM uec.public_suppression_generation"
        ).fetchone()[0]

        # The projection's normal query remains the single source of precision,
        # review, profile, source-rights, and suppression semantics. During this
        # private build only, validated releases are admitted to its CTE.
        query = discovery.SELECT_ROWS.replace(
            "release.status = 'promoted'", "release.status IN ('validated', 'promoted')"
        )
        rows = connection.execute(query, (release_id,)).fetchall()

        eligible_observation_ids = sorted({row[1] for row in rows})
        taxonomy_by_observation: dict[str, tuple[str, str]] = {}
        if eligible_observation_ids:
            taxonomy_rows = connection.execute(
                """WITH current_sets AS (
                     SELECT DISTINCT ON (s.observation_id) s.observation_id,s.assignment_set_id,s.display_category
                     FROM uec.observation_taxonomy_assignment_sets s
                     WHERE s.observation_id = ANY(%s) AND s.taxonomy_version='uec-taxonomy-v1'
                     ORDER BY s.observation_id,s.created_at DESC,s.assignment_set_id DESC
                   )
                   SELECT s.observation_id, s.display_category,
                          array_agg(DISTINCT primary_key ORDER BY primary_key)
                            FILTER (WHERE mapping_method IN ('direct','derived') AND mapping_status IN ('mapped','partial') AND primary_key <> 'unclassified') AS confirmed_keys,
                          bool_or(primary_key='unclassified' OR mapping_method='candidate' OR mapping_status IN ('unmapped','unclassified','conflicting','ambiguous')) AS has_unresolved
                   FROM current_sets s JOIN uec.observation_taxonomy_assignments a USING (assignment_set_id)
                   GROUP BY s.observation_id,s.display_category""",
                (eligible_observation_ids,),
            ).fetchall()
            for observation_id, display_category, confirmed_keys, has_unresolved in taxonomy_rows:
                keys = list(confirmed_keys or [])
                if has_unresolved or not keys:
                    keys.append("unclassified")
                taxonomy_by_observation[str(observation_id)] = (display_category, compact_category_keys(keys))

        # One map feature represents one facility. Choose the first eligible
        # observation in deterministic order, while preserving its category.
        facilities: dict[str, dict[str, Any]] = {}
        for row in rows:
            point = _point(row[7])
            if point is None or row[8] == "unmapped":
                continue
            if row[8] not in ("exact", "city"):
                raise ValueError("public map projection has an unsupported precision")
            facility_id = str(row[0])
            facilities.setdefault(facility_id, {
                "record_id": facility_id,
                "longitude": point[0],
                "latitude": point[1],
                "kind": "exact" if row[8] == "exact" else "coarse",
                "category_key": taxonomy_by_observation.get(str(row[1]), ("unclassified", compact_category_keys(None)))[0],
                "category_keys_compact": taxonomy_by_observation.get(str(row[1]), ("unclassified", compact_category_keys(None)))[1],
            })

        source_ids = sorted({row[17] for row in rows if row[17]})
        attribution_rows = connection.execute(
            "SELECT source_id, attribution FROM uec.sources WHERE source_id = ANY(%s) ORDER BY source_id",
            (source_ids,),
        ).fetchall() if source_ids else []
        attribution = [
            {"source_id": source_id, "text": text}
            for source_id, text in attribution_rows if text and text.strip()
        ]

        tiles: dict[tuple[int, int, int], list[dict[str, Any]]]
        bounds = None
        for facility in facilities.values():
            lon, lat = facility["longitude"], facility["latitude"]
            bounds = [lon, lat, lon, lat] if bounds is None else [
                min(bounds[0], lon), min(bounds[1], lat), max(bounds[2], lon), max(bounds[3], lat)
            ]
        tiles = hierarchy_features(release_id, profile, list(facilities.values()))

        artifact_dir = staged_release_dir / profile
        artifact_dir.mkdir(parents=True, exist_ok=True)
        tile_inventory = []
        for zoom in range(MIN_ZOOM, MAX_ZOOM + 1):
            zoom_features = [
                {"x": x, "y": y, **feature}
                for (tile_zoom, x, y), features in sorted(tiles.items())
                if tile_zoom == zoom
                for feature in features
            ]
            if not zoom_features:
                continue
            tile_json = json.dumps(zoom_features, sort_keys=True, separators=(",", ":"))
            sql = """
                WITH input AS (
                  SELECT *, ST_SetSRID(ST_Point(longitude,latitude),4326) AS location
                  FROM jsonb_to_recordset(%s::jsonb) AS f(
                    x integer, y integer, longitude double precision, latitude double precision,
                    feature_key text, kind text, count integer, exact_count integer,
                    coarse_count integer, next_zoom integer, record_id text, category_key text, category_keys_compact text)
                ), features AS (
                  SELECT x,y,feature_key,kind,count,exact_count,coarse_count,next_zoom,
                         record_id,category_key,category_keys_compact,
                         ST_AsMVTGeom(ST_Transform(location,3857),
                           ST_TileEnvelope(%s::integer,x,y),4096,128,true) AS geom
                  FROM input
                ), tile_coords AS (SELECT DISTINCT x,y FROM features)
                SELECT tile_coords.x,tile_coords.y,
                       (SELECT ST_AsMVT(tile_data,%s,4096,'geom')
                        FROM (SELECT feature_key,kind,count,exact_count,coarse_count,
                                     next_zoom,record_id,category_key,category_keys_compact,geom
                              FROM features WHERE x=tile_coords.x AND y=tile_coords.y) tile_data)
                FROM tile_coords ORDER BY tile_coords.x,tile_coords.y
            """
            with connection.cursor(name=f"uec_public_mvt_z{zoom}") as cursor:
                cursor.execute(sql, (tile_json, zoom, SOURCE_LAYER))
                for x, y, tile_bytes in cursor:
                    if not tile_bytes:
                        continue
                    tile_path = artifact_dir / str(zoom) / str(x) / f"{y}.mvt"
                    tile_path.parent.mkdir(parents=True, exist_ok=True)
                    tile_path.write_bytes(tile_bytes)
                    tile_digest = hashlib.sha256(tile_bytes).hexdigest()
                    tile_inventory.append({"z": zoom, "x": x, "y": y, "sha256": tile_digest, "etag": f'"{tile_digest}"', "byte_size": len(tile_bytes)})

        generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        manifest = {
            "schema_version": "uec-public-map-artifact-v1",
            "release_id": release_id,
            "profile": profile,
            "generated_at": generated_at,
            "suppression_generation": generation,
            "attribution": attribution,
            "bounds": bounds,
            "min_zoom": MIN_ZOOM,
            "max_zoom": MAX_ZOOM,
            "tile_url_template": f"/api/v2/releases/{release_id}/map/tiles/{{z}}/{{x}}/{{y}}.mvt?profile={profile}",
            "source_layer": SOURCE_LAYER,
            "feature_schema_version": FEATURE_SCHEMA_VERSION,
            "feature_properties": FEATURE_PROPERTIES,
            "count_semantics": "count is all-activity public facility leaves; exact_count and coarse_count partition it; clusters keep precision classes separate and category-neutral",
            "feature_key_semantics": "stable SHA-256 prefix of release, profile, zoom, global grid cell, and precision; exact leaves include record_id",
            "next_zoom_semantics": "cluster expansion targets the immediate child zoom; exact and coarse leaves have no expansion zoom",
            "tiles": tile_inventory,
            "cache_policy": {"cache_control": "public, max-age=0, must-revalidate", "max_age_seconds": 0},
        }
        manifest_path = artifact_dir / "map-artifact.json"
        manifest_path.write_text(canonical_json(manifest), encoding="utf-8")
        os.replace(staged_release_dir, final_release_dir)
        shutil.rmtree(staging_dir)
        return {"status": "built", "release_id": release_id, "profile": profile, "tile_count": len(tile_inventory), "suppression_generation": generation, "map_artifact_manifest": str(final_release_dir / profile / "map-artifact.json")}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("release_id")
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--database-url", default=os.environ.get("UEC_DATABASE_URL", "postgresql://uec:uec-local-development-only@localhost:5433/uec"))
    args = parser.parse_args()
    try:
        print(json.dumps(build(args.database_url, args.release_id, args.output_root), sort_keys=True))
    except Exception as error:
        print(json.dumps({"status": "blocked", "error": str(error)}, sort_keys=True))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
