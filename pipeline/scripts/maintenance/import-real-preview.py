#!/usr/bin/env python3
"""Verify and import retained source-scoped rows into the isolated local preview."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
from pathlib import Path
from typing import Any
from datetime import datetime
from urllib.parse import urlsplit

import psycopg

ALLOWED = {"fr.dgal.section-i", "fr.dgal.section-ii", "it.853-2004", "us.fsis"}
EXPECTED_OBSERVATIONS = {
    "fr.dgal.section-i": 1449,
    "fr.dgal.section-ii": 1067,
    "it.853-2004": 41849,
    "us.fsis": 7241,
}
REPORT = Path(__file__).parents[3] / "data" / "manifests" / "d1-data-readiness-report.json"
CHUNK = 1024 * 1024


class ImportFailure(Exception):
    def __init__(self, code: str):
        self.code = code


def digest_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(CHUNK), b""):
            digest.update(block)
            size += len(block)
    return digest.hexdigest(), size


def json_object(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as stream:
            value = json.load(stream)
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise ImportFailure("invalid_manifest") from None
    if not isinstance(value, dict):
        raise ImportFailure("invalid_manifest")
    return value


def find_manifests(root: Path) -> dict[str, tuple[Path, dict[str, Any]]]:
    found: dict[str, list[tuple[Path, dict[str, Any]]]] = {source: [] for source in ALLOWED}
    forbidden = False
    for path in root.rglob("*.json"):
        if not path.is_file() or path.is_symlink():
            continue
        try:
            with path.open("r", encoding="utf-8") as stream:
                value = json.load(stream)
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if not isinstance(value, dict) or "source_id" not in value:
            continue
        if value.get("source_id") == "us.aphis":
            forbidden = True
        if value.get("source_id") in found and "normalized_sha256" in value:
            found[value["source_id"]].append((path, value))
    if forbidden:
        raise ImportFailure("forbidden_source_present")
    if any(len(found[source]) > 1 for source in ALLOWED):
        raise ImportFailure("duplicate_handoff")
    if any(len(found[source]) != 1 for source in ALLOWED):
        raise ImportFailure("handoff_missing")
    return {source: found[source][0] for source in ALLOWED}


def resolve_artifacts(root: Path, manifests: dict[str, tuple[Path, dict[str, Any]]]) -> dict[str, Path]:
    normalized_hashes: dict[str, str] = {}
    wanted: set[str] = set()
    for source, (_, manifest) in manifests.items():
        normalized_hash = manifest.get("normalized_sha256")
        source_hash = manifest.get("checksum_sha256")
        if any(not isinstance(value, str) or len(value) != 64 for value in (normalized_hash, source_hash)):
            raise ImportFailure("manifest_hash_missing")
        normalized_hashes[source] = normalized_hash
        wanted.update((normalized_hash, source_hash))
        bundle = manifest.get("bundle_artifact")
        if isinstance(bundle, dict):
            bundle_hash = bundle.get("sha256")
            if not isinstance(bundle_hash, str) or len(bundle_hash) != 64:
                raise ImportFailure("manifest_hash_missing")
            wanted.add(bundle_hash)
    matches: dict[str, list[Path]] = {value: [] for value in wanted}
    # Hash every retained artifact as a stream; a matching manifest alone is insufficient.
    for path in root.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        try:
            actual, _ = digest_file(path)
        except OSError:
            continue
        if actual in matches:
            matches[actual].append(path)
    if any(len(paths) != 1 for paths in matches.values()):
        raise ImportFailure("artifact_hash_mismatch")
    return {source: matches[normalized_hashes[source]][0] for source in manifests}


def pick(row: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in row:
            return row[name]
    return None


def parse_row(source: str, row: Any) -> tuple[str, str, str | None, str | None, str | None, float | None, float | None, str | None, Any, bool]:
    if not isinstance(row, dict):
        raise ImportFailure("row_schema_invalid")
    identifier = pick(row, "source_identifier", "source_record_id", "record_id", "id")
    if not isinstance(identifier, (str, int)) or not str(identifier):
        raise ImportFailure("row_schema_invalid")
    lat_raw = pick(row, "latitude", "lat")
    lon_raw = pick(row, "longitude", "lon", "lng")
    precision_raw = pick(row, "coordinate_precision", "location_precision", "display_precision")
    precision = precision_raw.strip().lower() if isinstance(precision_raw, str) else None
    lat = lon = None
    numeric = False
    if lat_raw is not None or lon_raw is not None:
        if lat_raw is None or lon_raw is None:
            raise ImportFailure("coordinate_pair_invalid")
        try:
            lat, lon = float(lat_raw), float(lon_raw)
        except (TypeError, ValueError):
            raise ImportFailure("coordinate_value_invalid") from None
        if not math.isfinite(lat) or not math.isfinite(lon) or not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ImportFailure("coordinate_value_invalid")
        if precision not in {"numeric", "exact", "source_numeric", "source_coordinates", "facility_coordinate"}:
            raise ImportFailure("coordinate_precision_undocumented")
        numeric = True
    city = pick(row, "city", "locality")
    postal = pick(row, "postal_code", "postcode", "zip")
    city = city.strip() if isinstance(city, str) and city.strip() else None
    postal = postal.strip() if isinstance(postal, str) and postal.strip() else None
    country = pick(row, "country_code", "country")
    country = country.strip().upper() if isinstance(country, str) and len(country.strip()) == 2 else None
    observed = pick(row, "source_observed_at", "observed_at", "observation_date")
    if numeric:
        location_class = "numeric_source_coordinate"
    elif (city or postal) and precision in {"city", "postal", "city_or_postal", "city-or-postal", "coarse"}:
        location_class = "city_postal"
    else:
        location_class = "unmapped_private_observation"
    return str(identifier), location_class, country, city, postal, lat, lon, precision, observed, row.get("facility_candidate") is True


def hash_snapshot(manifests: dict[str, tuple[Path, dict[str, Any]]]) -> str:
    digest = hashlib.sha256()
    for source in sorted(manifests):
        path, manifest = manifests[source]
        digest.update(source.encode())
        digest.update(bytes.fromhex(manifest["normalized_sha256"]))
    return digest.hexdigest()


def manifest_provenance(manifest: dict[str, Any]) -> tuple[str, str, int, str, datetime, str, str]:
    source_hash = manifest.get("checksum_sha256")
    normalized_hash = manifest.get("normalized_sha256")
    url = manifest.get("source_url")
    retrieved = manifest.get("retrieved_at_utc")
    code = manifest.get("code_version")
    config = manifest.get("config_version")
    count = manifest.get("normalized_rows")
    parsed_url = urlsplit(url) if isinstance(url, str) else None
    if (not isinstance(source_hash, str) or len(source_hash) != 64 or not isinstance(normalized_hash, str)
        or len(normalized_hash) != 64 or not parsed_url or parsed_url.scheme not in {"http", "https"}
        or not parsed_url.hostname or parsed_url.username or parsed_url.password or parsed_url.query or parsed_url.fragment
        or not isinstance(retrieved, str) or not isinstance(code, str) or not code
        or not isinstance(config, str) or not config or not isinstance(count, int) or count < 0):
        raise ImportFailure("manifest_provenance_invalid")
    try:
        timestamp = datetime.fromisoformat(retrieved.replace("Z", "+00:00"))
    except ValueError:
        raise ImportFailure("manifest_provenance_invalid") from None
    if timestamp.utcoffset() is None:
        raise ImportFailure("manifest_provenance_invalid")
    return source_hash, normalized_hash, count, url, timestamp, code, config


def public_zero_counts(db: psycopg.Connection) -> tuple[int, int]:
    release_count = 0
    projection_count = 0
    for relation in (
        "uec.release_members",
        "uec.map_facilities_public_discovery",
        "uec.map_facilities_public_discovery_read_model",
        "uec.graph_public_relationships",
        "uec.graph_public_claims",
    ):
        if db.execute("SELECT to_regclass(%s)", (relation,)).fetchone()[0] is None:
            continue
        count = db.execute(f"SELECT count(*) FROM {relation}").fetchone()[0]
        if relation == "uec.release_members":
            release_count = count
        else:
            projection_count += count
    if release_count or projection_count:
        raise ImportFailure("public_rows_present")
    return release_count, projection_count


def import_rows(db: psycopg.Connection, source: str, path: Path, expected_rows: int, snapshot: str) -> tuple[int, int, int, int, int, int]:
    count = numeric_count = coarse_count = candidate_count = unmapped_count = mapped_non_candidate_count = 0
    with path.open("r", encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                raise ImportFailure("row_schema_invalid")
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                raise ImportFailure("row_schema_invalid") from None
            parsed = parse_row(source, record)
            identifier, klass, country, city, postal, lat, lon, precision, observed, candidate = parsed
            db.execute(
                """INSERT INTO real_preview.observations
                (snapshot_sha256,source_id,source_identifier,location_class,facility_candidate,country_code,city,postal_code,latitude,longitude,coordinate_precision,source_observed_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (snapshot_sha256,source_id,source_identifier) DO NOTHING""",
                (snapshot, source, identifier, klass, candidate, country, city, postal, lat, lon, precision, observed),
            )
            count += 1
            numeric_count += candidate and klass == "numeric_source_coordinate"
            coarse_count += candidate and klass == "city_postal"
            candidate_count += candidate and klass != "unmapped_private_observation"
            unmapped_count += klass == "unmapped_private_observation"
            mapped_non_candidate_count += not candidate and klass != "unmapped_private_observation"
    if count != expected_rows:
        raise ImportFailure("manifest_row_count_mismatch")
    return count, numeric_count, coarse_count


def run(root: Path, database_url: str) -> dict[str, Any]:
    if not root.is_dir() or root.is_symlink():
        raise ImportFailure("handoff_root_unavailable")
    manifests = find_manifests(root)
    artifacts = resolve_artifacts(root, manifests)
    snapshot = hash_snapshot(manifests)
    readiness = json_object(REPORT)
    observations = readiness.get("observations", {})
    expected = {
        "fr.dgal.section-i": observations.get("france", {}).get("section_i"),
        "fr.dgal.section-ii": observations.get("france", {}).get("section_ii"),
        "it.853-2004": observations.get("italy", {}).get("count"),
        "us.fsis": observations.get("fsis", {}).get("count"),
    }
    total = 0
    numeric = coarse = 0
    candidates = unmapped = mapped_non_candidates = 0
    public_release_count = public_projection_count = 0
    numeric_by_source: dict[str, int] = {}
    coarse_by_source: dict[str, int] = {}
    candidate_by_source: dict[str, int] = {}
    with psycopg.connect(database_url) as db, db.transaction():
        total_expected = sum(value for value in expected.values() if isinstance(value, int))
        db.execute("INSERT INTO real_preview.imports(snapshot_sha256,observation_count) VALUES (%s,%s) ON CONFLICT DO NOTHING", (snapshot, total_expected))
        for source, (_, manifest) in manifests.items():
            source_hash, normalized_hash, row_count, source_url, retrieved, code, config = manifest_provenance(manifest)
            db.execute("""INSERT INTO real_preview.source_manifests
                (snapshot_sha256,source_id,source_artifact_sha256,normalized_sha256,normalized_rows,source_url,retrieved_at,code_version,config_version)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                (snapshot, source, source_hash, normalized_hash, row_count, source_url, retrieved, code, config))
        for source in sorted(ALLOWED):
            _, manifest = manifests[source]
            if not isinstance(manifest.get("normalized_rows"), int) or manifest["normalized_rows"] < 0:
                raise ImportFailure("manifest_row_count_missing")
            if manifest["normalized_rows"] != expected.get(source) or EXPECTED_OBSERVATIONS[source] != expected.get(source):
                raise ImportFailure("readiness_observation_mismatch")
            rows, exact, coarse_rows, candidate_rows, unmapped_rows, mapped_non_candidate_rows = import_rows(db, source, artifacts[source], expected[source], snapshot)
            total += rows
            numeric += exact
            coarse += coarse_rows
            candidates += candidate_rows
            unmapped += unmapped_rows
            mapped_non_candidates += mapped_non_candidate_rows
            numeric_by_source[source] = exact
            coarse_by_source[source] = coarse_rows
            candidate_by_source[source] = candidate_rows
        expected_coordinates = readiness.get("coordinate_states", {})
        expected_numeric_by_source = expected_coordinates.get("numeric_coordinate", {}).get("by_source", {})
        expected_coarse_by_source = expected_coordinates.get("city_or_postal_geocode", {}).get("by_source", {})
        expected_numeric = expected_coordinates.get("numeric_coordinate", {}).get("total")
        expected_coarse = expected_coordinates.get("city_or_postal_geocode", {}).get("total")
        expected_candidate_by_source = readiness.get("candidates", {}).get("by_source", {})
        derived_by_readiness_source = {
            "fr.dgal.union": ("fr.dgal.section-i", "fr.dgal.section-ii"),
            "it.853-2004": ("it.853-2004",),
            "us.fsis": ("us.fsis",),
        }
        source_aggregates_match = all(
            sum(numeric_by_source.get(source, 0) for source in members) == expected_numeric_by_source.get(readiness_source, 0)
            and sum(coarse_by_source.get(source, 0) for source in members) == expected_coarse_by_source.get(readiness_source, 0)
            and sum(candidate_by_source.get(source, 0) for source in members) == expected_candidate_by_source.get(readiness_source, 0)
            for readiness_source, members in derived_by_readiness_source.items()
        )
        if (numeric, coarse) != (expected_numeric, expected_coarse) or not source_aggregates_match:
            raise ImportFailure("readiness_location_mismatch")
        public_release_count, public_projection_count = public_zero_counts(db)
    return {"status": "imported", "observation_count": total, "facility_candidate_count": candidates,
            "numeric_coordinate_count": numeric, "city_postal_count": coarse,
            "unmapped_observation_count": unmapped, "mapped_non_candidate_observation_count": mapped_non_candidates,
            "public_release_count": public_release_count, "public_projection_count": public_projection_count, "idempotent": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--database-url-env", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result: dict[str, Any]
    try:
        database_url = os.environ.get(args.database_url_env)
        if not database_url:
            raise ImportFailure("database_configuration_missing")
        result = run(args.root, database_url)
    except ImportFailure as error:
        result = {"status": "failed", "error_code": error.code, "observation_count": 0,
                  "facility_candidate_count": 0, "numeric_coordinate_count": 0, "city_postal_count": 0,
                  "unmapped_observation_count": 0, "mapped_non_candidate_observation_count": 0,
                  "public_release_count": 0, "public_projection_count": 0}
        print(json.dumps(result, separators=(",", ":")))
        return 2
    except Exception:
        result = {"status": "failed", "error_code": "import_failed", "observation_count": 0,
                  "facility_candidate_count": 0, "numeric_coordinate_count": 0, "city_postal_count": 0,
                  "unmapped_observation_count": 0, "mapped_non_candidate_observation_count": 0,
                  "public_release_count": 0, "public_projection_count": 0}
        print(json.dumps(result, separators=(",", ":")))
        return 2
    print(json.dumps(result, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
