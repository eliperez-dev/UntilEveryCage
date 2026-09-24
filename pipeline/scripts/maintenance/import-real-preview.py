#!/usr/bin/env python3
"""Verify and import retained source-scoped rows into the isolated local preview."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
from datetime import timezone, timedelta
from pathlib import Path
from typing import Any
from datetime import datetime
from urllib.parse import urlsplit

import psycopg

POLICY = Path(__file__).parents[2] / "preview-enabled-sources.json"
LEGACY_ALLOWED = {"fr.dgal.section-i", "fr.dgal.section-ii", "us.fsis"}
PREVIEW_ENABLED = set(json.loads(POLICY.read_text(encoding="utf-8"))["sources"])
ALLOWED = LEGACY_ALLOWED | PREVIEW_ENABLED
EXPECTED_OBSERVATIONS = {
    "fr.dgal.section-i": 1449,
    "fr.dgal.section-ii": 1068,
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
    for source in sorted(LEGACY_ALLOWED):
        path = handoffs / source / "manifest.json"
        if not path.is_file() or path.is_symlink():
            raise ImportFailure("handoff_missing")
        manifest = json_object(path)
        if manifest.get("source_id") != source or not isinstance(manifest.get("normalized_sha256"), str):
            raise ImportFailure("manifest_source_mismatch")
        selected[source] = path, manifest
    # Duplicate detection is limited to the retained legacy packet. The live
    # source path is explicitly selected by its exact handoff manifest.
    for path in handoffs.glob("*/manifest.json"):
        if path in {item[0] for item in selected.values()}:
            continue
        try:
            alternate = json_object(path)
        except ImportFailure:
            continue
        source = alternate.get("source_id")
        normalized = path.parent / "normalized" / "records.jsonl"
        if source in LEGACY_ALLOWED and normalized.is_file() and not normalized.is_symlink():
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
    selected = {handoffs / source / "manifest.json" for source in LEGACY_ALLOWED}
    ignored: set[str] = set()
    for path in handoffs.glob("*/manifest.json"):
        if path in selected:
            continue
        try:
            source = json_object(path).get("source_id")
        except ImportFailure:
            continue
        if isinstance(source, str) and source in LEGACY_ALLOWED and not (path.parent / "normalized" / "records.jsonl").is_file():
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


def parse_row(source: str, row: Any) -> tuple[str, str, str | None, str | None, str | None, float | None, float | None, str | None, Any, str | None, bool, str | None]:
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
    precision_raw = pick(coordinates, "precision") or pick(normalized, "coordinate_precision", "geography_precision")
    precision = precision_raw.strip().lower() if isinstance(precision_raw, str) else None
    lat = lon = None
    numeric = False
    zero_pair = False
    has_lat = lat_raw is not None and not (isinstance(lat_raw, str) and not lat_raw.strip())
    has_lon = lon_raw is not None and not (isinstance(lon_raw, str) and not lon_raw.strip())
    if has_lat != has_lon:
        raise ImportFailure("coordinate_pair_invalid")
    if lat_raw is not None and lon_raw is not None:
        try:
            lat, lon = float(lat_raw), float(lon_raw)
        except (TypeError, ValueError):
            lat = lon = None
        if lat is not None and lon is not None and math.isfinite(lat) and math.isfinite(lon):
            zero_pair = lat == 0 and lon == 0
        if (lat is not None and lon is not None and math.isfinite(lat) and math.isfinite(lon)
                and (-90 <= lat <= 90 and -180 <= lon <= 180) and not zero_pair
                and precision in NUMERIC_PRECISIONS):
            numeric = True
        else:
            lat = lon = None
    city = pick(normalized, "city", "municipality")
    postal = pick(normalized, "postal_code")
    city = city.strip() if isinstance(city, str) and city.strip() else None
    postal = postal.strip() if isinstance(postal, str) and postal.strip() else None
    country = pick(normalized, "country_code")
    country = country.strip().upper() if isinstance(country, str) and len(country.strip()) == 2 else None
    department = pick(normalized, "department_number")
    department = department.strip() if isinstance(department, str) and department.strip() else None
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
    return str(identifier), location_class, country, city, postal, lat, lon, precision, observed, zero_pair, department, str(group_key).strip()


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


def _place_key(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    import unicodedata
    import re
    value = re.sub(r"['’ʼ`´]", "", value)
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().casefold()
    return " ".join("".join(char if char.isalnum() else " " for char in normalized).split()) or None


def _resolve_municipality(index: dict[str, Any], value: Any, alias_policy: dict[str, Any], department: str | None = None) -> tuple[dict[str, Any] | None, str | None]:
    if not isinstance(value, str) or not value.strip():
        return None, None
    import re
    aliases = alias_policy.get("official_subdivision_aliases", {})
    explicit = aliases.get(value) if isinstance(aliases, dict) else None
    if isinstance(explicit, dict):
        alias_key = _place_key(explicit.get("municipality"))
        place = index.get(alias_key or "")
        if isinstance(place, dict):
            return place, "official_subdivision_alias"
    variants = [value]
    # FASFC may provide its official bilingual municipality name as a slash-
    # separated pair. Each component is independently matched to Statbel.
    variants.extend(part.strip() for part in value.split("/") if part.strip())
    # The feed may append a province abbreviation; this is not part of the
    # municipality's name and is removed only as a final exact-name variant.
    variants.extend(re.sub(r"\s+\([^()]*\)\s*$", "", item).strip() for item in tuple(variants))
    for variant in variants:
        place_key = _place_key(variant) or ""
        department_field = alias_policy.get("department_field")
        lookup_key = f"{place_key}|{_place_key(department) or ''}" if department_field else place_key
        place = index.get(lookup_key)
        if not isinstance(place, dict) and department_field:
            continue
        if not department_field:
            place = index.get(place_key)
        if isinstance(place, dict):
            return place, "exact_name" if variant == value else "bilingual_or_province_qualified_name"
    return None, None


def validate_preview_fields(path: Path, allowed_fields: set[str]) -> None:
    top_level = {"source_id", "source_row", "source_row_id", "source_record_key", "source_values", "normalized"}
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            raise ImportFailure("row_schema_invalid") from None
        if not isinstance(row, dict) or set(row) - top_level:
            raise ImportFailure("preview_field_not_allowed")
        normalized = row.get("normalized")
        source_values = row.get("source_values")
        if not isinstance(normalized, dict) or set(normalized) - allowed_fields:
            raise ImportFailure("preview_field_not_allowed")
        if not isinstance(source_values, dict):
            raise ImportFailure("row_schema_invalid")


def import_rows(db: psycopg.Connection, source: str, path: Path, expected_rows: int, snapshot: str,
                municipality_index: dict[str, Any] | None = None,
                municipality_policy: dict[str, Any] | None = None) -> tuple[int, int, int, int, int, int, int, int, int, int, int, set[str], int, int]:
    count = unmapped_count = mapped_non_candidate_count = candidate_count = 0
    parsed_rows: list[tuple[str, str, str | None, str | None, str | None, float | None, float | None, str | None, Any, str | None, bool, str | None]] = []
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
    representatives: dict[str, tuple[str, str, str | None, str | None, str | None, float | None, float | None, str | None, Any, str | None, bool, str | None]] = {}
    zero_coordinate_groups: set[str] = set()
    usable_coordinate_groups: set[str] = set()
    for parsed in parsed_rows:
        identifier, klass, country, city, postal, lat, lon, precision, observed, zero_pair, department, group_key = parsed
        if zero_pair:
            zero_coordinate_groups.add(group_key)
        if klass == "numeric_source_coordinate":
            usable_coordinate_groups.add(group_key)
        if klass == "unmapped_private_observation":
            continue
        current = representatives.get(group_key)
        rank = (0 if klass == "numeric_source_coordinate" else 1, identifier)
        current_rank = ((0 if current[1] == "numeric_source_coordinate" else 1), current[0]) if current else None
        if current is None or rank < current_rank:
            representatives[group_key] = parsed
    numeric_count = coarse_count = 0
    precision_unknown_coordinate_count = source_provided_coordinate_count = 0
    for group_key, chosen in representatives.items():
        numeric_count += chosen[1] == "numeric_source_coordinate"
        coarse_count += chosen[1] == "city_postal"
        if chosen[1] == "numeric_source_coordinate":
            precision_unknown_coordinate_count += chosen[7] == "source-precision-unknown"
            source_provided_coordinate_count += chosen[7] == "source-provided"
    for parsed in parsed_rows:
        identifier, klass, country, city, postal, lat, lon, precision, observed, _, department, group_key = parsed
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
    coarse_placeable = 0
    for group_key, chosen in representatives.items():
        identifier, klass, country, city, postal, lat, lon, precision, _, _, department, _ = chosen
        place, place_match = _resolve_municipality(municipality_index or {}, city, municipality_policy or {}, department)
        display_lat = place.get("latitude") if isinstance(place, dict) else None
        display_lon = place.get("longitude") if isinstance(place, dict) else None
        if display_lat is not None and display_lon is not None:
            coarse_placeable += klass == "city_postal"
        preview_id = db.execute(
            "SELECT preview_id FROM real_preview.observations WHERE snapshot_sha256=%s AND source_id=%s AND source_identifier=%s",
            (snapshot, source, identifier),
        ).fetchone()[0]
        db.execute(
            """INSERT INTO real_preview.candidates
            (snapshot_sha256,source_id,source_group_key,representative_observation_id,location_class,country_code,city,postal_code,latitude,longitude,coordinate_precision,observation_count,display_latitude,display_longitude,display_geometry_source)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (snapshot_sha256,source_id,source_group_key) DO NOTHING""",
            (snapshot, source, group_key, preview_id, klass, country, city, postal, lat, lon, precision, observations_per_group[group_key], display_lat, display_lon,
             f"{(municipality_policy or {}).get('source', 'Administrative commune reference')}; approximate city location, not facility coordinates; name_match={place_match}" if display_lat is not None else None),
        )
    group_keys = set(representatives)
    rejected_zero_coordinates = len(zero_coordinate_groups - usable_coordinate_groups)
    return count, numeric_count, coarse_count, candidate_count, unmapped_count, mapped_non_candidate_count, len(group_keys), len(parsed_rows), rejected_zero_coordinates, precision_unknown_coordinate_count, source_provided_coordinate_count, group_keys, coarse_placeable, len(group_keys) - coarse_placeable


def run(root: Path, database_url: str, *, source_id: str | None = None,
        manifest_path: Path | None = None, municipality_index_path: Path | None = None,
        run_id: str | None = None, run_manifest_path: Path | None = None) -> dict[str, Any]:
    if not root.is_dir() or root.is_symlink():
        raise ImportFailure("handoff_root_unavailable")
    if source_id is not None:
        policy = json_object(POLICY).get("sources", {}).get(source_id)
        if not isinstance(policy, dict) or policy.get("enabled") is not True:
            raise ImportFailure("preview_policy_blocked")
        terms_path = Path(__file__).parents[3] / str(policy.get("terms_review", ""))
        terms = json_object(terms_path)
        if terms.get("decision") != "approved":
            raise ImportFailure("preview_terms_blocked")
        selected_manifest = manifest_path or (root / "candidate-handoff" / "manifest.json")
        if not selected_manifest.is_file() or selected_manifest.is_symlink():
            raise ImportFailure("handoff_missing")
        manifest = json_object(selected_manifest)
        if manifest.get("source_id") != source_id:
            raise ImportFailure("manifest_source_mismatch")
        source_hash, normalized_hash, retrieved_count, _, retrieved_at, code_version, config_version = manifest_provenance(manifest)
        if retrieved_at > datetime.now(timezone.utc) + timedelta(minutes=5):
            raise ImportFailure("manifest_timestamp_invalid")
        max_age = policy.get("freshness_max_days")
        if not isinstance(max_age, int) or max_age < 1 or datetime.now(timezone.utc) - retrieved_at > timedelta(days=max_age):
            raise ImportFailure("source_artifact_stale")
        if code_version != policy.get("adapter_version") or config_version != policy.get("schema_version"):
            raise ImportFailure("preview_version_mismatch")
        if not isinstance(run_id, str) or not run_id or run_manifest_path is None or not run_manifest_path.is_file():
            raise ImportFailure("runtime_run_manifest_missing")
        runtime_manifest = json_object(run_manifest_path)
        source_runs = runtime_manifest.get("results")
        source_result = next((item for item in source_runs if isinstance(item, dict) and item.get("source_id") == source_id), None) if isinstance(source_runs, list) else None
        source_summary = source_result.get("summary") if isinstance(source_result, dict) else None
        if not isinstance(source_summary, dict) or source_result.get("status") != "succeeded" or source_result.get("acquisition_classification") != "live":
            raise ImportFailure("runtime_source_run_not_live")
        if run_manifest_path.parent.name != runtime_manifest.get("run_id"):
            raise ImportFailure("runtime_handoff_run_mismatch")
        acquisition_evidence = None
        if source_id == "be.locations":
            pair_path = root / "acquisition" / source_id / run_id / "pair-metadata.json"
            if not pair_path.is_file() or pair_path.is_symlink():
                raise ImportFailure("paired_acquisition_provenance_missing")
            acquisition_evidence = json_object(pair_path)
            if acquisition_evidence.get("source_id") != source_id or not isinstance(acquisition_evidence.get("operator"), dict) or not isinstance(acquisition_evidence.get("activity_codes"), dict):
                raise ImportFailure("paired_acquisition_provenance_invalid")
            if acquisition_evidence["operator"].get("sha256") != source_hash:
                raise ImportFailure("paired_acquisition_manifest_mismatch")
            if acquisition_evidence["activity_codes"].get("sha256") != source_summary.get("activity_code_sha256"):
                raise ImportFailure("paired_codebook_run_mismatch")
            if acquisition_evidence["activity_codes"].get("run_id") != run_id or acquisition_evidence["operator"].get("run_id") != run_id:
                raise ImportFailure("paired_acquisition_run_mismatch")
            for artifact in (acquisition_evidence["operator"], acquisition_evidence["activity_codes"]):
                try:
                    artifact_time = datetime.fromisoformat(str(artifact.get("retrieved_at_utc")).replace("Z", "+00:00"))
                except ValueError:
                    raise ImportFailure("paired_acquisition_timestamp_invalid") from None
                if artifact_time.utcoffset() is None or artifact_time > datetime.now(timezone.utc) + timedelta(minutes=5):
                    raise ImportFailure("paired_acquisition_timestamp_invalid")
                if datetime.now(timezone.utc) - artifact_time > timedelta(days=policy["freshness_max_days"]):
                    raise ImportFailure("paired_acquisition_artifact_stale")
        elif source_id == "it.853-2004":
            acquisition_path = root / "acquisition" / source_id / run_id / "acquisition-metadata.json"
            if not acquisition_path.is_file() or acquisition_path.is_symlink():
                raise ImportFailure("acquisition_provenance_missing")
            acquisition_evidence = json_object(acquisition_path)
            if (acquisition_evidence.get("source_id") != source_id
                    or acquisition_evidence.get("run_id") != run_id
                    or acquisition_evidence.get("sha256") != source_hash
                    or acquisition_evidence.get("final_url") != manifest.get("source_url")
                    or acquisition_evidence.get("retrieved_at_utc") != manifest.get("retrieved_at_utc")):
                raise ImportFailure("acquisition_provenance_mismatch")
        elif source_id in {"fr.dgal.section-i", "fr.dgal.section-ii"}:
            acquisition_path = root / "acquisition" / source_id / run_id / "acquisition-metadata.json"
            if not acquisition_path.is_file() or acquisition_path.is_symlink():
                raise ImportFailure("acquisition_provenance_missing")
            acquisition_evidence = json_object(acquisition_path)
            if (acquisition_evidence.get("source_id") != source_id
                    or acquisition_evidence.get("run_id") != run_id
                    or acquisition_evidence.get("sha256") != source_hash
                    or acquisition_evidence.get("final_url") != manifest.get("source_url")
                    or acquisition_evidence.get("retrieved_at_utc") != manifest.get("retrieved_at_utc")):
                raise ImportFailure("acquisition_provenance_mismatch")
        municipality_index = None
        geometry_policy = policy.get("display_policy", {})
        if geometry_policy.get("kind") in {"administrative_municipality_centroid", "administrative_commune_centre"}:
            if municipality_index_path is None or not municipality_index_path.is_file() or municipality_index_path.is_symlink():
                raise ImportFailure("approved_coarse_geometry_missing")
            index_payload = json_object(municipality_index_path)
            if (index_payload.get("source") != geometry_policy.get("source")
                    or index_payload.get("license") != geometry_policy.get("license")
                    or index_payload.get("version") != geometry_policy.get("version")):
                raise ImportFailure("approved_coarse_geometry_provenance_invalid")
            if index_payload.get("source_url") != geometry_policy.get("source_url"):
                raise ImportFailure("approved_coarse_geometry_source_mismatch")
            if (geometry_policy.get("source_reference_url")
                    and index_payload.get("source_reference_url") != geometry_policy.get("source_reference_url")):
                raise ImportFailure("approved_coarse_geometry_source_mismatch")
            if not isinstance(index_payload.get("source_sha256"), str) or len(index_payload["source_sha256"]) != 64:
                raise ImportFailure("approved_coarse_geometry_hash_missing")
            geometry_time = index_payload.get("retrieved_at_utc")
            try:
                geometry_retrieved = datetime.fromisoformat(str(geometry_time).replace("Z", "+00:00"))
            except ValueError:
                raise ImportFailure("approved_coarse_geometry_timestamp_invalid") from None
            if geometry_retrieved.utcoffset() is None or datetime.now(timezone.utc) - geometry_retrieved > timedelta(days=14):
                raise ImportFailure("approved_coarse_geometry_stale")
            municipality_index = index_payload.get("municipalities")
            if not isinstance(municipality_index, dict):
                raise ImportFailure("approved_coarse_geometry_invalid")
        manifests = {source_id: (selected_manifest, manifest)}
    else:
        manifests = find_manifests(root)
    excluded_sources = excluded_sibling_sources(root)
    ignored_alternates = ignored_alternate_handoffs(root)
    artifacts = resolve_artifacts(root, manifests)
    if source_id is not None:
        allowed_fields = policy.get("allowed_preview_fields")
        if not isinstance(allowed_fields, list) or not all(isinstance(field, str) for field in allowed_fields):
            raise ImportFailure("preview_policy_invalid")
        validate_preview_fields(artifacts[source_id], set(allowed_fields))
        snapshot = hash_snapshot(manifests)
        if municipality_index is not None:
            # Retrieval timestamps change on each official refresh; only geography and
            # the approved resolution policy belong in the idempotency identity.
            geometry_fingerprint = hashlib.sha256(json.dumps({
                "resolver_version": policy.get("display_policy", {}).get("version"),
                "municipalities": municipality_index,
            }, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()
            snapshot = hashlib.sha256(f"{snapshot}:{geometry_fingerprint}".encode("ascii")).hexdigest()
    readiness = json_object(REPORT) if source_id is None else {}
    observations = readiness.get("observations", {})
    expected = {
        "fr.dgal.section-i": observations.get("france", {}).get("section_i"),
        "fr.dgal.section-ii": observations.get("france", {}).get("section_ii"),
        "us.fsis": observations.get("fsis", {}).get("count"),
    }
    if source_id is not None:
        expected = {source_id: source_summary.get("candidate_observation_rows")}
    total = 0
    numeric = coarse = 0
    candidates = unmapped = mapped_non_candidates = 0
    zero_zero_coordinates = precision_unknown_coordinates = source_provided_coordinates = 0
    public_release_count = public_projection_count = 0
    numeric_by_source: dict[str, int] = {}
    coarse_by_source: dict[str, int] = {}
    candidate_by_source: dict[str, int] = {}
    rejected_zero_by_source: dict[str, int] = {}
    group_keys_by_source: dict[str, set[str]] = {}
    with psycopg.connect(database_url) as db, db.transaction():
        total_expected = sum(value for value in expected.values() if isinstance(value, int))
        import_insert = db.execute("INSERT INTO real_preview.imports(snapshot_sha256,observation_count) VALUES (%s,%s) ON CONFLICT DO NOTHING", (snapshot, total_expected))
        idempotent_replay = import_insert.rowcount == 0
        for source, (_, manifest) in manifests.items():
            source_hash, normalized_hash, row_count, source_url, retrieved, code, config = manifest_provenance(manifest)
            db.execute("""INSERT INTO real_preview.source_manifests
                (snapshot_sha256,source_id,source_artifact_sha256,normalized_sha256,normalized_rows,source_url,retrieved_at,code_version,config_version)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                (snapshot, source, source_hash, normalized_hash, row_count, source_url, retrieved, code, config))
        for source in sorted(manifests):
            _, manifest = manifests[source]
            if not isinstance(manifest.get("normalized_rows"), int) or manifest["normalized_rows"] < 0:
                raise ImportFailure("manifest_row_count_missing")
            if manifest["normalized_rows"] != expected.get(source) or (source_id is None and EXPECTED_OBSERVATIONS[source] != expected.get(source)):
                raise ImportFailure("readiness_observation_mismatch")
            rows, exact, coarse_rows, candidate_rows, unmapped_rows, mapped_non_candidate_rows, _, _, zero_zero_rows, precision_unknown_rows, source_provided_rows, group_keys, placeable_rows, unplaceable_rows = import_rows(db, source, artifacts[source], expected[source], snapshot, municipality_index if source_id == source else None, policy.get("display_policy", {}) if source_id == source else None)
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
            rejected_zero_by_source[source] = zero_zero_rows
            group_keys_by_source[source] = group_keys
        expected_coordinates = readiness.get("coordinate_states", {})
        expected_numeric_by_source = expected_coordinates.get("numeric_coordinate", {}).get("by_source", {})
        expected_coarse_by_source = expected_coordinates.get("city_or_postal_geocode", {}).get("by_source", {})
        expected_numeric = expected_coordinates.get("numeric_coordinate", {}).get("total")
        expected_coarse = expected_coordinates.get("city_or_postal_geocode", {}).get("total")
        expected_rejected_zero = expected_coordinates.get("rejected_zero_coordinates", {})
        expected_candidate_by_source = readiness.get("candidates", {}).get("by_source", {})
        derived_by_readiness_source = {
            "fr.dgal.union": ("fr.dgal.section-i", "fr.dgal.section-ii"),
            "us.fsis": ("us.fsis",),
        }
        if source_id is not None:
            france_overlap = 0
            france_source_groups = 0
            union_candidates = candidates
            union_numeric = numeric
            union_coarse = coarse
            public_release_count, public_projection_count = public_zero_counts(db)
            if public_release_count + public_projection_count:
                raise ImportFailure("public_rows_present")
            source_hash, normalized_hash, row_count, source_url, retrieved, adapter_version, schema_version = manifest_provenance(manifests[source_id][1])
            input_count = source_summary.get("input_rows", 0)
            accepted_count = source_summary.get("valid_source_activity_rows", row_count)
            quarantined_count = source_summary.get("quarantined_rows", 0)
            out_of_scope_count = source_summary.get("out_of_scope_rows", 0)
            if any(not isinstance(value, int) or value < 0 for value in (input_count, accepted_count, quarantined_count, out_of_scope_count)):
                raise ImportFailure("runtime_counts_invalid")
            candidate_observation_count = source_summary.get("candidate_observation_rows")
            if (not isinstance(candidate_observation_count, int) or candidate_observation_count < 0
                    or candidate_observation_count != row_count or candidate_observation_count > accepted_count
                    or input_count != accepted_count + quarantined_count):
                raise ImportFailure("runtime_counts_do_not_reconcile")
            map_visible_count = numeric + placeable_rows
            unmapped_map_candidate_count = candidates - numeric - coarse
            if unmapped_map_candidate_count < 0:
                raise ImportFailure("runtime_location_classes_do_not_reconcile")
            runtime_details = {"quarantine_reasons": source_summary.get("quarantine_reasons", {}),
                               "source_artifacts": acquisition_evidence,
                               "geometry_reference": ({**{key: index_payload.get(key) for key in ("source", "source_url", "license", "reference_date", "retrieved_at_utc", "source_last_modified", "source_sha256", "source_byte_size", "method", "version")}, "derived_index_sha256": digest_file(municipality_index_path)[0]} if municipality_index is not None else None),
                               "fresh_live_run": True, "preview_policy_version": json_object(POLICY).get("contract_version")}
            db.execute("""INSERT INTO real_preview.source_preview_runs
                (run_id,source_id,snapshot_sha256,source_url,retrieved_at,source_artifact_sha256,normalized_sha256,
                 adapter_version,schema_version,input_count,accepted_count,quarantined_count,out_of_scope_count,
                 imported_observation_count,facility_count,numeric_coordinate_count,coarse_placeable_count,unmapped_count,
                 api_listable_count,map_visible_count,idempotent_replay,public_rows,runtime_details)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (run_id) DO NOTHING""",
                (run_id, source_id, snapshot, source_url, retrieved, source_hash, normalized_hash, adapter_version,
                 schema_version, input_count, accepted_count, quarantined_count, out_of_scope_count, total, candidates,
                 numeric, placeable_rows, unplaceable_rows, candidates, map_visible_count, idempotent_replay, 0,
                 psycopg.types.json.Jsonb(runtime_details)))
            return {"status": "imported", "source_id": source_id, "run_id": run_id,
                    "observation_count": total, "facility_candidate_count": candidates,
                    "source_scoped_candidate_count": candidates, "numeric_coordinate_count": numeric,
                    "approximate_coordinate_group_count": numeric,
                    "source_precision_unknown_group_count": precision_unknown_coordinates,
                    "source_provided_coordinate_group_count": source_provided_coordinates,
                    "rejected_zero_coordinates": zero_zero_coordinates,
                    "unmapped_map_candidate_count": unmapped_map_candidate_count,
                    "city_postal_count": coarse, "unmapped_observation_count": unmapped,
                    "coarse_placeable_facility_count": placeable_rows,
                    "unmapped_facility_count": unplaceable_rows,
                    "mapped_non_candidate_observation_count": mapped_non_candidates,
                    "public_release_count": public_release_count, "public_projection_count": public_projection_count,
                    "map_visible_count": map_visible_count, "api_listable_count": candidates,
                    "idempotent_replay": idempotent_replay, "idempotent": True,
                    "normalized_sha256": manifests[source_id][1].get("normalized_sha256")}
        france_overlap = len(group_keys_by_source["fr.dgal.section-i"] & group_keys_by_source["fr.dgal.section-ii"])
        france_source_groups = candidate_by_source["fr.dgal.section-i"] + candidate_by_source["fr.dgal.section-ii"]
        union_candidates = candidates - france_overlap
        union_numeric = numeric
        union_coarse = coarse - france_overlap
        source_aggregates_match = (
            numeric_by_source["fr.dgal.section-i"] + numeric_by_source["fr.dgal.section-ii"] == expected_numeric_by_source.get("fr.dgal.union", 0)
            and coarse_by_source["fr.dgal.section-i"] + coarse_by_source["fr.dgal.section-ii"] - france_overlap == expected_coarse_by_source.get("fr.dgal.union", 0)
            and france_source_groups - france_overlap == expected_candidate_by_source.get("fr.dgal.union", 0)
            and numeric_by_source["us.fsis"] == expected_numeric_by_source.get("us.fsis", 0)
            and coarse_by_source["us.fsis"] == expected_coarse_by_source.get("us.fsis", 0)
            and candidate_by_source["us.fsis"] == expected_candidate_by_source.get("us.fsis", 0)
        )
        if (union_numeric, union_coarse) != (expected_numeric, expected_coarse) or union_candidates != readiness.get("candidates", {}).get("total") or not source_aggregates_match:
            raise ImportFailure("readiness_location_mismatch")
        if (zero_zero_coordinates != expected_rejected_zero.get("total")
                or {source: count for source, count in rejected_zero_by_source.items() if count}
                != expected_rejected_zero.get("by_source", {})):
            raise ImportFailure("readiness_zero_coordinate_mismatch")
        public_release_count, public_projection_count = public_zero_counts(db)
    return {"status": "imported", "observation_count": total, "facility_candidate_count": candidates,
            "source_scoped_candidate_count": candidates, "france_source_scoped_group_count": france_source_groups,
            "france_overlap_signal_count": france_overlap, "union_candidate_count": union_candidates,
            "numeric_coordinate_count": numeric, "city_postal_count": coarse,
            "approximate_coordinate_group_count": numeric,
            "source_precision_unknown_group_count": precision_unknown_coordinates,
            "source_provided_coordinate_group_count": source_provided_coordinates,
            "rejected_zero_coordinates": zero_zero_coordinates,
            "rejected_zero_coordinates_by_source": rejected_zero_by_source,
            "coordinate_groups": numeric,
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
    parser.add_argument("--source-id", help="import exactly one explicitly preview-enabled source handoff")
    parser.add_argument("--manifest", type=Path, help="exact run manifest to import")
    parser.add_argument("--municipality-index", type=Path, help="provenanced Statbel municipality centroid index")
    parser.add_argument("--run-id", help="unique live acquisition/run identifier")
    parser.add_argument("--run-manifest", type=Path, help="exact shared refresh-run manifest")
    args = parser.parse_args()
    result: dict[str, Any]
    try:
        database_url = os.environ.get(args.database_url_env)
        if not database_url:
            raise ImportFailure("database_configuration_missing")
        result = run(args.root, database_url, source_id=args.source_id, manifest_path=args.manifest,
                     municipality_index_path=args.municipality_index, run_id=args.run_id,
                     run_manifest_path=args.run_manifest)
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
