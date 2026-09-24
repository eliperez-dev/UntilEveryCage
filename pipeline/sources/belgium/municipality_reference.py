"""Acquire and derive coarse Belgian municipality centroids from Statbel."""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
import urllib.request
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from pyproj import Transformer

from pipeline.common.acquisition import archive_stream, utc_now

URL = "https://statbel.fgov.be/sites/default/files/files/opendata/Statistische%20sectoren/sh_statbel_statistical_sectors_3812_20250101.geojson.zip"
LICENSE = "CC BY 4.0"
VERSION = "statbel-municipality-centroids-2025-v2"
MEMBER = "sh_statbel_statistical_sectors_3812_20250101.geojson/sh_statbel_statistical_sectors_3812_20250101.geojson"


def _norm(value: str) -> str:
    # Treat orthographic apostrophes as non-semantic for the bilingual
    # FASFC/Statbel locality join (e.g. Braine-l'Alleud).
    value = re.sub(r"['’ʼ`´]", "", value)
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().casefold()
    return re.sub(r"[^a-z0-9]+", " ", ascii_value).strip()


def _ring_area_centroid(ring: list[list[float]]) -> tuple[float, float, float]:
    twice_area = cx = cy = 0.0
    for left, right in zip(ring, ring[1:]):
        cross = left[0] * right[1] - right[0] * left[1]
        twice_area += cross
        cx += (left[0] + right[0]) * cross
        cy += (left[1] + right[1]) * cross
    if abs(twice_area) < 1e-7:
        return 0.0, 0.0, 0.0
    return abs(twice_area) / 2, cx / (3 * twice_area), cy / (3 * twice_area)


def _polygon_area_centroid(rings: list[list[list[float]]]) -> tuple[float, float, float]:
    weighted_area = weighted_x = weighted_y = 0.0
    for index, ring in enumerate(rings):
        area, x, y = _ring_area_centroid(ring)
        sign = 1 if index == 0 else -1
        weighted_area += sign * area
        weighted_x += sign * area * x
        weighted_y += sign * area * y
    return weighted_area, weighted_x / weighted_area, weighted_y / weighted_area


def acquire_centroids(*, output_root: Path, run_id: str, timeout_seconds: int = 180) -> dict:
    target = output_root / "statbel-municipalities-2025.geojson.zip"
    request = urllib.request.Request(URL, headers={"User-Agent": "UntilEveryCage/controlled-acquisition", "Accept": "application/zip"})
    retrieved_at = utc_now()
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        digest, size = archive_stream(response, target, max_bytes=128 * 1024 * 1024)
        final_url = response.geturl()
        last_modified = response.headers.get("Last-Modified")
    areas: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])
    names: dict[str, set[str]] = defaultdict(set)
    with zipfile.ZipFile(target) as archive:
        with archive.open(MEMBER) as stream:
            collection = json.load(stream)
            for feature in collection.get("features", []):
                props = feature.get("properties") or {}
                code = str(props.get("cd_munty_refnis") or "").strip()
                if not code:
                    continue
                geometry = feature.get("geometry") or {}
                polygons = geometry.get("coordinates", [])
                if geometry.get("type") == "Polygon":
                    polygons = [polygons]
                if geometry.get("type") not in {"Polygon", "MultiPolygon"}:
                    continue
                for polygon in polygons:
                    area, x, y = _polygon_area_centroid(polygon)
                    areas[code][0] += area
                    areas[code][1] += area * x
                    areas[code][2] += area * y
                for field in ("tx_munty_descr_nl", "tx_munty_descr_fr", "tx_munty_descr_de"):
                    if isinstance(props.get(field), str) and props[field].strip():
                        names[code].add(props[field].strip())
    transformer = Transformer.from_crs("EPSG:3812", "EPSG:4326", always_xy=True)
    by_name: dict[str, dict] = {}
    for code, (area, weighted_x, weighted_y) in areas.items():
        if area <= 0:
            continue
        lon, lat = transformer.transform(weighted_x / area, weighted_y / area)
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            continue
        for name in names[code]:
            normalized = _norm(name)
            if normalized:
                by_name[normalized] = {"municipality": name, "refnis": code, "latitude": lat, "longitude": lon}
    output = output_root / "municipality-centroids.json"
    payload = json.dumps({"source": "Statbel", "source_url": final_url, "license": LICENSE,
                          "reference_date": "2025-01-01", "retrieved_at_utc": retrieved_at,
                          "source_last_modified": last_modified, "source_sha256": digest,
                          "source_byte_size": size, "crs": "EPSG:3812 transformed to EPSG:4326",
                          "method": "area-weighted centroid of disjoint statistical-sector polygons grouped by official municipality REFNIS",
                          "version": VERSION, "municipalities": by_name}, ensure_ascii=False,
                         sort_keys=True, separators=(",", ":")).encode("utf-8")
    output.write_bytes(payload)
    return {"path": str(output), "sha256": hashlib.sha256(payload).hexdigest(), "byte_size": len(payload),
            "source_sha256": digest, "source_byte_size": size, "source_url": final_url,
            "retrieved_at_utc": retrieved_at, "source_last_modified": last_modified,
            "reference_date": "2025-01-01", "municipality_name_count": len(by_name),
            "run_id": run_id, "license": LICENSE, "version": VERSION}
