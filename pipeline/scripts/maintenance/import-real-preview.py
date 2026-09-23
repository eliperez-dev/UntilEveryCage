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
    "fr.dgal.section-ii": 1068,
    "it.853-2004": 41849,
    "us.fsis": 7241,
}
REPORT = Path(__file__).parents[3] / "data" / "manifests" / "d1-data-readiness-report.json"
CHUNK = 1024 * 1024
NUMERIC_PRECISIONS = {
    "numeric", "exact", "source_numeric", "source_coordinates", "facility_coordinate",
    "source-provided", "source-precision-unknown",
}


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
    # The handoff contract names one layout. Historical rehearsals and sibling
    # source packets may coexist in the private root; neither is a candidate.
    handoffs = root / "d6-graph-mvp" / "handoffs"
    selected: dict[str, tuple[Path, dict[str, Any]]] = {}
    for source in sorted(ALLOWED):
        path = handoffs / source / "manifest.json"
        if not path.is_file() or path.is_symlink():
            raise ImportFailure("handoff_missing")
        manifest = json_object(path)
        if manifest.get("source_id") != source or not isinstance(manifest.get("normalized_sha256"), str):
            raise ImportFailure("manifest_source_mismatch")
        selected[source] = path, manifest
    for path in handoffs.glob("*/manifest.json"):
        if path in {item[0] for item in selected.values()}:
            continue
        try:
            alternate = json_object(path)
        except ImportFailure:
            continue
        source = alternate.get("source_id")
        normalized = path.parent / "normalized" / "records.jsonl"
        if source in ALLOWED and normalized.is_file() and not normalized.is_symlink():
            alternate_hash = alternate.get("normalized_sha256")
            actual_hash, _ = digest_file(normalized)
            if isinstance(alternate_hash, str) and actual_hash == alternate_hash:
                raise ImportFailure("duplicate_handoff")
    return selected


def excluded_sibling_sources(root: Path) -> list[str]:
    handoffs = root / "d6-graph-mvp" / "handoffs"
    excluded: set[str] = set()
    if not handoffs.is_dir():
        return []
    for path in handoffs.glob("*/manifest.json"):
        try:
            source = json_object(path).get("source_id")
        except ImportFailure:
            continue
        if isinstance(source, str) and source not in ALLOWED:
            excluded.add(source)
    return sorted(excluded)


def ignored_alternate_handoffs(root: Path) -> list[str]:
    handoffs = root / "d6-graph-mvp" / "handoffs"
    if not handoffs.is_dir():
        return []
    selected = {handoffs / source / "manifest.json" for source in ALLOWED}
    ignored: set[str] = set()
    for path in handoffs.glob("*/manifest.json"):
        if path in selected:
            continue
        try:
            source = json_object(path).get("source_id")
        except ImportFailure:
            continue
        if isinstance(source, str) and source in ALLOWED and not (path.parent / "normalized" / "records.jsonl").is_file():
            ignored.add(source)
    return sorted(ignored)


def resolve_artifacts(root: Path, manifests: dict[str, tuple[Path, dict[str, Any]]]) -> dict[str, Path]:
    artifacts: dict[str, Path] = {}
    for source, (_, manifest) in manifests.items():
        normalized_hash = manifest.get("normalized_sha256")
        source_hash = manifest.get("checksum_sha256")
        if any(not isinstance(value, str) or len(value) != 64 for value in (normalized_hash, source_hash)):
            raise ImportFailure("manifest_hash_missing")
        path = manifests[source][0].parent / "normalized" / "records.jsonl"
        if not path.is_file() or path.is_symlink():
            raise ImportFailure("normalized_artifact_missing")
        actual, _ = digest_file(path)
        if actual != normalized_hash:
            raise ImportFailure("normalized_artifact_hash_mismatch")
        artifacts[source] = path
    return artifacts


def pick(row: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in row:
            return row[name]
    return None


def parse_row(source: str, row: Any) -> tuple[str, str, str | None, str | None, str | None, float | None, float | None, str | None, Any, str | None]:
    if not isinstance(row, dict):
        raise ImportFailure("row_schema_invalid")
    if row.get("source_id") != source or not isinstance(row.get("normalized"), dict):
        raise ImportFailure("row_source_mismatch")
    normalized = row["normalized"]
    source_values = row.get("source_values") if isinstance(row.get("source_values"), dict) else {}
    identifier = pick(row, "source_record_key", "source_row_id")
    if not isinstance(identifier, (str, int)) or not str(identifier):
        raise ImportFailure("row_schema_invalid")
    coordinates = normalized.get("coordinates")
    if not isinstance(coordinates, dict):
        coordinates = {}
    lat_raw = pick(coordinates, "latitude")
    lon_raw = pick(coordinates, "longitude")
    if lat_raw is None and source == "it.853-2004":
        lat_raw = source_values.get("latitudine")
        lon_raw = source_values.get("longitudine")
    precision_raw = pick(coordinates, "precision") or pick(normalized, "coordinate_precision", "geography_precision")
    precision = precision_raw.strip().lower() if isinstance(precision_raw, str) else None
    lat = lon = None
    numeric = False
    has_lat = lat_raw is not None and not (isinstance(lat_raw, str) and not lat_raw.strip())
    has_lon = lon_raw is not None and not (isinstance(lon_raw, str) and not lon_raw.strip())
    if has_lat != has_lon:
        raise ImportFailure("coordinate_pair_invalid")
    if lat_raw is not None and lon_raw is not None:
        try:
            lat, lon = float(lat_raw), float(lon_raw)
        except (TypeError, ValueError):
            lat = lon = None
        if (lat is not None and lon is not None and math.isfinite(lat) and math.isfinite(lon)
                and (-90 <= lat <= 90 and -180 <= lon <= 180) and precision in NUMERIC_PRECISIONS):
            numeric = True
        else:
            lat = lon = None
    city = pick(normalized, "city", "municipality")
    postal = pick(normalized, "postal_code")
    city = city.strip() if isinstance(city, str) and city.strip() else None
    postal = postal.strip() if isinstance(postal, str) and postal.strip() else None
    country = pick(normalized, "country_code")
    country = country.strip().upper() if isinstance(country, str) and len(country.strip()) == 2 else None
    observed = pick(normalized, "source_observed_at", "observed_at", "observation_date")
    if numeric:
        location_class = "numeric_source_coordinate"
    elif (city or postal) and precision in {"city", "postal", "city_or_postal", "city-or-postal", "coarse"}:
        location_class = "city_postal"
    elif city or postal:
        location_class = "city_postal"
    else:
        location_class = "unmapped_private_observation"
    group_key = pick(normalized, "establishment_id", "recognition_number", "establishment_number")
    if not isinstance(group_key, (str, int)) or not str(group_key).strip():
        raise ImportFailure("source_group_key_missing")
    if not precision and location_class == "city_postal":
        precision = "city_postal"
    return str(identifier), location_class, country, city, postal, lat, lon, precision, observed, str(group_key).strip()


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


def import_rows(db: psycopg.Connection, source: str, path: Path, expected_rows: int, snapshot: str) -> tuple[int, int, int, int, int, int, int, int, int, int, int, set[str]]:
    count = unmapped_count = mapped_non_candidate_count = candidate_count = 0
    parsed_rows: list[tuple[str, str, str | None, str | None, str | None, float | None, float | None, str | None, Any, str | None]] = []
    with path.open("r", encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                raise ImportFailure("row_schema_invalid")
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                raise ImportFailure("row_schema_invalid") from None
            parsed = parse_row(source, record)
            parsed_rows.append(parsed)
    representatives: dict[str, tuple[str, str, str | None, str | None, str | None, float | None, float | None, str | None, Any, str | None]] = {}
    for parsed in parsed_rows:
        identifier, klass, country, city, postal, lat, lon, precision, observed, group_key = parsed
        if klass == "unmapped_private_observation":
            continue
        current = representatives.get(group_key)
        rank = (0 if klass == "numeric_source_coordinate" else 1, identifier)
        current_rank = ((0 if current[1] == "numeric_source_coordinate" else 1), current[0]) if current else None
        if current is None or rank < current_rank:
            representatives[group_key] = parsed
    numeric_count = coarse_count = 0
    zero_zero_coordinate_count = precision_unknown_coordinate_count = source_provided_coordinate_count = 0
    for group_key, chosen in representatives.items():
        numeric_count += chosen[1] == "numeric_source_coordinate"
        coarse_count += chosen[1] == "city_postal"
        if chosen[1] == "numeric_source_coordinate":
            zero_zero_coordinate_count += chosen[5] == 0 and chosen[6] == 0
            precision_unknown_coordinate_count += chosen[7] == "source-precision-unknown"
            source_provided_coordinate_count += chosen[7] == "source-provided"
    for parsed in parsed_rows:
        identifier, klass, country, city, postal, lat, lon, precision, observed, group_key = parsed
        candidate = group_key in representatives and representatives[group_key][0] == identifier
        db.execute(
                """INSERT INTO real_preview.observations
                (snapshot_sha256,source_id,source_identifier,location_class,facility_candidate,country_code,city,postal_code,latitude,longitude,coordinate_precision,source_observed_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (snapshot_sha256,source_id,source_identifier) DO NOTHING""",
                (snapshot, source, identifier, klass, candidate, country, city, postal, lat, lon, precision, observed),
            )
        count += 1
        candidate_count += candidate
        unmapped_count += klass == "unmapped_private_observation"
        mapped_non_candidate_count += not candidate and klass != "unmapped_private_observation"
    if count != expected_rows:
        raise ImportFailure("manifest_row_count_mismatch")
    observations_per_group: dict[str, int] = {}
    for parsed in parsed_rows:
        observations_per_group[parsed[-1]] = observations_per_group.get(parsed[-1], 0) + 1
    for group_key, chosen in representatives.items():
        identifier, klass, country, city, postal, lat, lon, precision, _, _ = chosen
        preview_id = db.execute(
            "SELECT preview_id FROM real_preview.observations WHERE snapshot_sha256=%s AND source_id=%s AND source_identifier=%s",
            (snapshot, source, identifier),
        ).fetchone()[0]
        db.execute(
            """INSERT INTO real_preview.candidates
            (snapshot_sha256,source_id,source_group_key,representative_observation_id,location_class,country_code,city,postal_code,latitude,longitude,coordinate_precision,observation_count)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (snapshot_sha256,source_id,source_group_key) DO NOTHING""",
            (snapshot, source, group_key, preview_id, klass, country, city, postal, lat, lon, precision, observations_per_group[group_key]),
        )
    group_keys = set(representatives)
    return count, numeric_count, coarse_count, candidate_count, unmapped_count, mapped_non_candidate_count, len(group_keys), len(parsed_rows), zero_zero_coordinate_count, precision_unknown_coordinate_count, source_provided_coordinate_count, group_keys


def run(root: Path, database_url: str) -> dict[str, Any]:
    if not root.is_dir() or root.is_symlink():
        raise ImportFailure("handoff_root_unavailable")
    manifests = find_manifests(root)
    excluded_sources = excluded_sibling_sources(root)
    ignored_alternates = ignored_alternate_handoffs(root)
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
    zero_zero_coordinates = precision_unknown_coordinates = source_provided_coordinates = 0
    public_release_count = public_projection_count = 0
    numeric_by_source: dict[str, int] = {}
    coarse_by_source: dict[str, int] = {}
    candidate_by_source: dict[str, int] = {}
    group_keys_by_source: dict[str, set[str]] = {}
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
            rows, exact, coarse_rows, candidate_rows, unmapped_rows, mapped_non_candidate_rows, _, _, zero_zero_rows, precision_unknown_rows, source_provided_rows, group_keys = import_rows(db, source, artifacts[source], expected[source], snapshot)
            total += rows
            numeric += exact
            coarse += coarse_rows
            candidates += candidate_rows
            unmapped += unmapped_rows
            mapped_non_candidates += mapped_non_candidate_rows
            zero_zero_coordinates += zero_zero_rows
            precision_unknown_coordinates += precision_unknown_rows
            source_provided_coordinates += source_provided_rows
            numeric_by_source[source] = exact
            coarse_by_source[source] = coarse_rows
            candidate_by_source[source] = candidate_rows
            group_keys_by_source[source] = group_keys
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
        france_overlap = len(group_keys_by_source["fr.dgal.section-i"] & group_keys_by_source["fr.dgal.section-ii"])
        france_source_groups = candidate_by_source["fr.dgal.section-i"] + candidate_by_source["fr.dgal.section-ii"]
        union_candidates = candidates - france_overlap
        union_numeric = numeric
        union_coarse = coarse - france_overlap
        source_aggregates_match = (
            numeric_by_source["fr.dgal.section-i"] + numeric_by_source["fr.dgal.section-ii"] == expected_numeric_by_source.get("fr.dgal.union", 0)
            and coarse_by_source["fr.dgal.section-i"] + coarse_by_source["fr.dgal.section-ii"] - france_overlap == expected_coarse_by_source.get("fr.dgal.union", 0)
            and france_source_groups - france_overlap == expected_candidate_by_source.get("fr.dgal.union", 0)
            and numeric_by_source["it.853-2004"] == expected_numeric_by_source.get("it.853-2004", 0)
            and coarse_by_source["it.853-2004"] == expected_coarse_by_source.get("it.853-2004", 0)
            and candidate_by_source["it.853-2004"] == expected_candidate_by_source.get("it.853-2004", 0)
            and numeric_by_source["us.fsis"] == expected_numeric_by_source.get("us.fsis", 0)
            and coarse_by_source["us.fsis"] == expected_coarse_by_source.get("us.fsis", 0)
            and candidate_by_source["us.fsis"] == expected_candidate_by_source.get("us.fsis", 0)
        )
        if (union_numeric, union_coarse) != (expected_numeric, expected_coarse) or union_candidates != readiness.get("candidates", {}).get("total") or not source_aggregates_match:
            raise ImportFailure("readiness_location_mismatch")
        public_release_count, public_projection_count = public_zero_counts(db)
    return {"status": "imported", "observation_count": total, "facility_candidate_count": candidates,
            "source_scoped_candidate_count": candidates, "france_source_scoped_group_count": france_source_groups,
            "france_overlap_signal_count": france_overlap, "union_candidate_count": union_candidates,
            "numeric_coordinate_count": numeric, "city_postal_count": coarse,
            "approximate_coordinate_group_count": numeric,
            "source_precision_unknown_group_count": precision_unknown_coordinates,
            "source_provided_coordinate_group_count": source_provided_coordinates,
            "zero_zero_coordinate_group_count": zero_zero_coordinates,
            "union_numeric_coordinate_count": union_numeric, "union_city_postal_count": union_coarse,
            "unmapped_observation_count": unmapped, "mapped_non_candidate_observation_count": mapped_non_candidates,
            "source_artifact_hash_verification": "unavailable_private_artifact_not_retained",
            "excluded_sibling_sources": excluded_sources,
            "ignored_alternate_handoff_sources": ignored_alternates,
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
