#!/usr/bin/env python3
"""Verify and import retained source-scoped rows into the isolated local preview."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import traceback
from datetime import timezone, timedelta
from pathlib import Path
from typing import Any
from datetime import datetime
from urllib.parse import urlsplit

# Direct script execution puts this file's directory, not the repository root,
# at sys.path[0]. Keep the importer usable from strict source-runner subprocesses.
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

import psycopg
from pipeline.taxonomy_crosswalk import (
    PRIMARY_PRECEDENCE, TAXONOMY_VERSION, crosswalk_document,
    persistence_assignments, project_observation,
)
from pipeline.taxonomy.persistence import persist_preview_candidate_assignment_set

POLICY = Path(__file__).parents[2] / "preview-enabled-sources.json"
SNAPSHOT_PROJECTION_VERSION = "real-preview-candidate-projection-v7"
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
    "source-provided", "source-provided-unspecified", "source-precision-unknown",
}
SOURCE_LOCATION_SOURCES = {"ca.ontario.meat-plants", "ca.cfia.federal-meat"}
SOURCE_GROUP_KEY_INDEX = 23
ACTIVITY_DISPLAY_PRECEDENCE = (
    "slaughter", "meat_processing", "poultry_processing", "fish_processing",
    "dairy_processing", "egg_processing", "processing", "cutting",
    "animal_products_adjacent", "logistics_and_storage",
)


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


def count_jsonl_rows(path: Path) -> int:
    count = 0
    with path.open("rb") as stream:
        for line in stream:
            if not line.strip():
                raise ImportFailure("offline_handoff_row_invalid")
            try:
                json.loads(line)
            except (UnicodeDecodeError, json.JSONDecodeError):
                raise ImportFailure("offline_handoff_row_invalid") from None
            count += 1
    return count


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


def safe_preview_text(value: Any, limit: int) -> str | None:
    """Accept a short normalized scalar, never a source_values/raw payload."""
    if not isinstance(value, str):
        return None
    value = " ".join(value.split())
    if not value or len(value) > limit or any(ord(char) < 32 or ord(char) == 127 for char in value):
        return None
    return value


def _text_values(value: Any, limit: int = 240) -> list[str]:
    values = value if isinstance(value, (list, tuple)) else [value]
    result: list[str] = []
    for item in values:
        text = safe_preview_text(item, limit)
        if text and text not in result:
            result.append(text)
    return result


def _normalized_values(normalized: dict[str, Any], names: tuple[str, ...], limit: int) -> list[str]:
    values: list[str] = []
    for name in names:
        for item in _text_values(normalized.get(name), limit):
            if item not in values:
                values.append(item)
    return values


def activity_contract(normalized: dict[str, Any], source: str = "", source_values: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build the versioned source-linked taxonomy projection for one observation."""
    codes = _normalized_values(normalized, (
        "source_classification_codes", "activity_codes", "source_function_codes",
        "source_classification_code", "activity_code", "primary_anzsic_class_code"), 120)
    labels = _normalized_values(normalized, (
        "source_classification_labels", "activity_descriptions", "activity_label",
        "activity_description", "source_activity", "source_classification_label",
        "industry_label", "primary_anzsic_class_name", "source_plant_type", "animal_class",
        "activities", "processing_activities"), 200)
    # Keep this helper's legacy unit-test and utility contract for callers that
    # have no source identity. Real imports always supply the source ID below.
    if not source:
        categories = _text_values(normalized.get("activity_categories"), 80)
        explicit_category = safe_preview_text(normalized.get("classification_category"), 80)
        mapping = str(pick(normalized, "classification_mapping_status", "classification_state") or "").strip().lower()
        if mapping in {"unknown", "unmapped", "unclassified", "unsupported"}:
            categories = []
        if explicit_category and explicit_category.lower() not in {"unknown", "unmapped", "unclassified", "none"}:
            if categories and explicit_category not in categories:
                mapping = "conflicting"
            elif not categories:
                categories = [explicit_category]
        if mapping not in {"conflicting", "ambiguous"}:
            mapping = ("unmapped" if codes or labels else "unclassified") if not categories else (
                "partial" if mapping in {"partial", "partially_mapped", "unresolved"} else "mapped")
        ordered = sorted(set(categories), key=lambda item: (
            ACTIVITY_DISPLAY_PRECEDENCE.index(item) if item in ACTIVITY_DISPLAY_PRECEDENCE else len(ACTIVITY_DISPLAY_PRECEDENCE), item))
        return {"category": ordered[0] if ordered and mapping not in {"conflicting", "ambiguous", "unmapped", "unclassified"} else None,
                "activity_categories": ordered, "taxonomy_assignments": [], "taxonomy_mapping_method": "derived",
                "taxonomy_assignment_rows": [], "crosswalk_document": None,
                "source_activity_codes": codes, "source_activity_labels": labels, "activity_mapping_status": mapping,
                "classification_ruleset_version": safe_preview_text(pick(normalized, "classification_ruleset_version", "ruleset_version", "ruleset_id"), 120)}
    projected = project_observation({"source_id": source, "normalized": normalized,
                                     "source_values": source_values or {}})
    # Adapter activity_categories remain source-facing evidence. Only the
    # versioned crosswalk projection can supply taxonomy primary categories.
    categories = projected["taxonomy_primaries"]
    mapping = projected["taxonomy_mapping_status"]
    display_category = projected["taxonomy_display_category"]
    return {
        "category": display_category,
        "activity_categories": categories,
        "taxonomy_assignments": projected["taxonomy_assignments"],
        "taxonomy_mapping_method": projected["taxonomy_mapping_method"],
        "taxonomy_assignment_rows": persistence_assignments(projected),
        "crosswalk_document": crosswalk_document(source),
        "source_activity_codes": codes,
        "source_activity_labels": labels,
        "activity_mapping_status": mapping,
        "classification_ruleset_version": safe_preview_text(
            pick(normalized, "classification_ruleset_version", "ruleset_version", "ruleset_id"), 120
        ) or TAXONOMY_VERSION,
    }


def merge_activity_contracts(contracts: list[dict[str, Any]], source_id: str | None = None) -> dict[str, Any]:
    """Preserve the union of activity evidence for a source-scoped candidate."""
    if not contracts and source_id:
        projected = project_observation({"source_id": source_id})
        contracts = [{
            "category": projected["taxonomy_display_category"],
            "activity_categories": projected["taxonomy_primaries"],
            "taxonomy_assignments": projected["taxonomy_assignments"],
            "taxonomy_mapping_method": projected["taxonomy_mapping_method"],
            "taxonomy_assignment_rows": persistence_assignments(projected),
            "crosswalk_document": crosswalk_document(source_id),
            "source_activity_codes": [],
            "source_activity_labels": [],
            "activity_mapping_status": projected["taxonomy_mapping_status"],
        }]
    categories = sorted({value for contract in contracts for value in contract["activity_categories"]}, key=lambda item: (
        PRIMARY_PRECEDENCE.index(item) if item in PRIMARY_PRECEDENCE else len(PRIMARY_PRECEDENCE), item))
    assignment_map: dict[tuple[str, str, str], dict[str, Any]] = {}
    for contract in contracts:
        for assignment in contract["taxonomy_assignments"]:
            key = (assignment["leaf_activity"], assignment["primary"], assignment["method"])
            prior = assignment_map.get(key)
            if prior is None or json.dumps(assignment, sort_keys=True) < json.dumps(prior, sort_keys=True):
                assignment_map[key] = assignment
    ordered_assignments = [assignment_map[key] for key in sorted(assignment_map)]
    codes = list(dict.fromkeys(value for contract in contracts for value in contract["source_activity_codes"]))
    labels = list(dict.fromkeys(value for contract in contracts for value in contract["source_activity_labels"]))
    source_rulesets = sorted({contract.get("classification_ruleset_version") for contract in contracts
                              if contract.get("classification_ruleset_version")})
    source_ruleset = ";".join(source_rulesets) if source_rulesets else TAXONOMY_VERSION
    if len(source_ruleset) > 120:
        source_ruleset = TAXONOMY_VERSION
    statuses = {contract["activity_mapping_status"] for contract in contracts}
    methods = {contract["taxonomy_mapping_method"] for contract in contracts}
    if "conflicting" in statuses:
        status = "conflicting"
    elif "ambiguous" in statuses:
        status = "ambiguous"
    elif not categories:
        status = "unmapped" if "unmapped" in statuses else "unclassified"
    elif statuses & {"partial", "unmapped"}:
        status = "partial"
    else:
        status = "mapped"
    return {
        "category": next((item for item in PRIMARY_PRECEDENCE if item in categories), "unclassified"),
        "activity_categories": categories,
        "taxonomy_assignments": ordered_assignments,
        "taxonomy_assignment_rows": persistence_assignments({
            "taxonomy_assignments": ordered_assignments,
            "taxonomy_mapping_status": status,
        }),
        "crosswalk_document": next((contract["crosswalk_document"] for contract in contracts if contract["crosswalk_document"]), None),
        "taxonomy_mapping_method": next(iter(methods)) if len(methods) == 1 else ("candidate" if "candidate" in methods else "derived" if methods else "candidate"),
        "source_activity_codes": codes,
        "source_activity_labels": labels,
        "activity_mapping_status": status,
        "classification_ruleset_version": source_ruleset,
    }


def safe_https_url(value: Any) -> str | None:
    value = safe_preview_text(value, 2048)
    if value is None:
        return None
    try:
        parsed = urlsplit(value)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
                or parsed.query or parsed.fragment or any(ord(char) < 32 for char in value)):
            return None
        return value
    except ValueError:
        return None


SOURCE_NAMES = {
    "au.npi.facilities": "Australian Department of Climate Change, Energy, the Environment and Water — National Pollutant Inventory",
    "au.sa.epa.licensed-activities": "South Australian Environment Protection Authority — Licensed Activities",
    "be.locations": "Belgian Federal Agency for the Safety of the Food Chain — Operator Register",
    "br.sif.registered": "Brazilian Ministry of Agriculture and Livestock — MAPA/DIPOA SIF Registered Establishments",
    "ca.ontario.meat-plants": "Government of Ontario — Provincially Licensed Meat Plants",
    "ca.cfia.federal-meat": "Canadian Food Inspection Agency — Federal Meat Establishments",
    "fsa_approved_establishments": "Food Standards Agency — Approved Food Establishments (England and Wales)",
    "fss_approved_establishments": "Food Standards Scotland — Approved Establishments (Scotland)",
    "es.cat.feed-sandach": "Catalonia — SANDACH Feed Establishments Register",
    "dk.smiley": "Danish Veterinary and Food Administration — Find Smiley",
    "fr.dgal.section-i": "French Ministry of Agriculture — DGAL Section I",
    "fr.dgal.section-ii": "French Ministry of Agriculture — DGAL Section II",
    "it.1069-2009": "Italian Ministry of Health — Regulation 1069/2009",
    "it.853-2004": "Italian Ministry of Health — Regulation 853/2004",
    "us.fsis": "USDA Food Safety and Inspection Service",
}


def parse_observed_at(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        result = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return result if result.utcoffset() is not None else None


def parse_row(source: str, row: Any) -> tuple[Any, ...]:
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
    # The retained Italy-853 handoff predates the normalized-coordinate
    # projection, but its official CSV coordinate columns are explicitly
    # parsed by Italy853Adapter and covered by its adapter contract tests.
    # Recover only those two source-owned fields for this private projection;
    # never apply the fallback to other sources or expose source_values.
    if source == "it.853-2004" and not coordinates:
        source_latitude = source_values.get("latitudine")
        source_longitude = source_values.get("longitudine")
        if source_latitude is not None or source_longitude is not None:
            coordinates = {
                "latitude": source_latitude,
                "longitude": source_longitude,
                "precision": "source-precision-unknown",
            }
    coordinate_method = normalized.get("coordinate_method")
    coordinate_provider = normalized.get("coordinate_provider")
    coordinate_confidence = normalized.get("coordinate_confidence")
    if isinstance(coordinates, dict):
        coordinate_method = coordinate_method or coordinates.get("method")
        coordinate_provider = coordinate_provider or coordinates.get("provider")
        coordinate_confidence = coordinate_confidence or coordinates.get("confidence")
    lat_raw = pick(coordinates, "latitude")
    lon_raw = pick(coordinates, "longitude")
    precision_raw = pick(coordinates, "precision") or pick(normalized, "coordinate_precision", "geography_precision")
    precision = precision_raw.strip().lower() if isinstance(precision_raw, str) else None
    coordinate_method = safe_preview_text(pick(coordinates, "method") or pick(normalized, "coordinate_method"), 80)
    coordinate_provider = safe_preview_text(pick(coordinates, "provider") or pick(normalized, "coordinate_provider"), 160)
    confidence_band = safe_preview_text(pick(coordinates, "confidence_band") or pick(normalized, "coordinate_confidence_band"), 24)
    confidence_score_raw = pick(coordinates, "confidence_score")
    confidence_score = None
    if confidence_score_raw is not None:
        try:
            confidence_score = float(confidence_score_raw)
        except (TypeError, ValueError):
            raise ImportFailure("coordinate_confidence_invalid") from None
        if not math.isfinite(confidence_score) or not 0 <= confidence_score <= 1:
            raise ImportFailure("coordinate_confidence_invalid")
    if confidence_band not in {None, "high", "medium", "low"}:
        raise ImportFailure("coordinate_confidence_invalid")
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
    if source == "au.npi.facilities" and numeric and (
            coordinate_method != "source_coordinates"
            or coordinate_provider != "Australian National Pollutant Inventory"
            or coordinate_confidence != "high_source_reported_location"
            or precision != "source-provided"):
        raise ImportFailure("source_coordinate_provenance_invalid")
    city = pick(normalized, "city", "municipality")
    postal = pick(normalized, "postal_code")
    city = city.strip() if isinstance(city, str) and city.strip() else None
    postal = postal.strip() if isinstance(postal, str) and postal.strip() else None
    country = pick(normalized, "country_code")
    country = country.strip().upper() if isinstance(country, str) and len(country.strip()) == 2 else None
    department = pick(normalized, "department_number")
    department = department.strip() if isinstance(department, str) and department.strip() else None
    observed = parse_observed_at(pick(normalized, "source_observed_at", "observed_at", "observation_date"))
    if numeric:
        location_class = "numeric_source_coordinate"
    elif (city or postal) and precision in {"city", "postal", "city_or_postal", "city-or-postal", "coarse"}:
        location_class = "city_postal"
    elif city or postal:
        location_class = "city_postal"
    else:
        location_class = "unmapped_private_observation"
    group_key = (identifier if source == "fsa_approved_establishments" else
                 pick(normalized, "establishment_id", "recognition_number", "establishment_number"))
    if not isinstance(group_key, (str, int)) or not str(group_key).strip():
        raise ImportFailure("source_group_key_missing")
    if not precision and location_class == "city_postal":
        precision = "city_postal"
    privacy_gate = pick(normalized, "privacy_gate", "privacy_status")
    privacy_allows_name = isinstance(privacy_gate, str) and privacy_gate.strip().lower().replace("_", "-") in {
        "eligible", "privacy-cleared", "passed", "clear", "public-eligible"
    }
    name = None
    if privacy_allows_name:
        name = safe_preview_text(pick(normalized, "canonical_name", "trading_name", "name"), 200)
    contract = activity_contract(normalized, source, row.get("source_values") if isinstance(row, dict) else None)
    activity = safe_preview_text(pick(normalized, "source_activity", "activity_description", "activity_label"), 240)
    if activity is None:
        activity = safe_preview_text("; ".join(contract["source_activity_labels"]), 240)
    if activity is None and contract["category"]:
        activity = contract["category"]
    activity_source = "source" if activity else None
    evidence_summary = safe_preview_text(pick(normalized, "evidence_summary"), 500)
    if evidence_summary is None and source == "au.npi.facilities" and numeric:
        evidence_summary = safe_preview_text(
            "method=" + str(coordinate_method or "source_coordinates")
            + "; provider=" + str(coordinate_provider or SOURCE_NAMES.get(source))
            + "; confidence=" + str(coordinate_confidence or "high_source_reported_location")
            + "; precision=" + str(precision or "source-provided"), 500)
    record_url = safe_https_url(pick(normalized, "source_record_url"))
    default_map_scope = source != "dk.smiley"
    map_scope = (
        False if source == "es.cat.feed-sandach"
        else normalized.get("in_default_map_scope", default_map_scope)
    )
    if not isinstance(map_scope, bool):
        map_scope = default_map_scope
    map_scope_reason = ("list_only_locality_reference" if source == "es.cat.feed-sandach" else
                        safe_preview_text(pick(normalized, "map_scope_reason", "classification_optional_filter"), 160))
    facility_address = (safe_preview_text(pick(normalized, "facility_address", "address"), 500)
                        if source in SOURCE_LOCATION_SOURCES else None)
    # Validate and preserve the source-owned administrative key separately
    # from the display projection; it is used only for offline coarse lookup.
    administrative_code_for_row(source, normalized)
    return (str(identifier), location_class, country, city, postal, lat, lon, precision, observed,
            zero_pair, department, name, activity, activity_source, record_url, evidence_summary,
            map_scope, map_scope_reason, facility_address, coordinate_method, coordinate_provider,
            confidence_score, confidence_band, str(group_key).strip())


def administrative_code_for_row(source: str, normalized: dict[str, Any]) -> str | None:
    """Return only an allowlisted stable code; never infer it from display text."""
    if source != "es.cat.feed-sandach":
        return None
    value = normalized.get("municipality_code")
    # The live register contains both official INE (5-digit) and Idescat
    # (6-digit) municipality codes. Preserve the source value exactly; the
    # reviewed ICGC reference carries both codes, so resolution needs no alias
    # inference or name matching.
    if value is not None and (not isinstance(value, str) or not value.isdigit() or len(value) not in {5, 6}):
        raise ImportFailure("administrative_code_invalid")
    return value


def hash_snapshot(manifests: dict[str, tuple[Path, dict[str, Any]]]) -> str:
    digest = hashlib.sha256()
    digest.update(SNAPSHOT_PROJECTION_VERSION.encode())
    for source in sorted(manifests):
        path, manifest = manifests[source]
        digest.update(source.encode())
        digest.update(bytes.fromhex(manifest["normalized_sha256"]))
    return digest.hexdigest()


def snapshot_identity(manifests: dict[str, tuple[Path, dict[str, Any]]],
                      geometry_fingerprint: str | None = None) -> str:
    snapshot = hash_snapshot(manifests)
    if geometry_fingerprint is not None:
        snapshot = hashlib.sha256(f"{snapshot}:{geometry_fingerprint}".encode("ascii")).hexdigest()
    return snapshot


def manifest_provenance(manifest: dict[str, Any]) -> tuple[str, str, int, str, datetime, str, str]:
    source_hash = manifest.get("checksum_sha256")
    normalized_hash = manifest.get("normalized_sha256")
    url = manifest.get("source_url")
    retrieved = manifest.get("retrieved_at_utc")
    code = manifest.get("code_version")
    config = manifest.get("config_version")
    count = manifest.get("normalized_rows")
    parsed_url = urlsplit(url) if isinstance(url, str) else None
    allowed_query = (manifest.get("source_id") == "ca.cfia.federal-meat" and parsed_url is not None
                     and parsed_url.hostname == "active.inspection.gc.ca"
                     and parsed_url.path == "/scripts/meavia/reglist/download.asp"
                     and parsed_url.query == "lang=e")
    if (not isinstance(source_hash, str) or len(source_hash) != 64 or not isinstance(normalized_hash, str)
        or len(normalized_hash) != 64 or not parsed_url or parsed_url.scheme not in {"http", "https"}
        or not parsed_url.hostname or parsed_url.username or parsed_url.password or (parsed_url.query and not allowed_query) or parsed_url.fragment
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


def map_unmapped_candidate_count(candidate_count: int, map_visible_count: int) -> int:
    """Candidates without a permitted map feature, not observations without location hints."""
    if candidate_count < 0 or map_visible_count < 0 or map_visible_count > candidate_count:
        raise ImportFailure("offline_map_count_inconsistent")
    return candidate_count - map_visible_count


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
    top_level = {"source_id", "source_row", "source_row_id", "source_record_key", "source_values", "source_rows", "normalized"}
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
    parsed_rows: list[tuple[Any, ...]] = []
    administrative_codes: dict[str, str | None] = {}
    activity_contracts_by_group: dict[str, list[dict[str, Any]]] = {}
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
            activity_contracts_by_group.setdefault(parsed[SOURCE_GROUP_KEY_INDEX], []).append(
                activity_contract(record["normalized"], source, record.get("source_values")))
            code = administrative_code_for_row(source, record["normalized"])
            if code is not None:
                administrative_codes[parsed[0]] = code
    representatives: dict[str, tuple[Any, ...]] = {}
    zero_coordinate_groups: set[str] = set()
    usable_coordinate_groups: set[str] = set()
    for parsed in parsed_rows:
        identifier, klass, country, city, postal, lat, lon, precision, observed, zero_pair, department = parsed[:11]
        group_key = parsed[SOURCE_GROUP_KEY_INDEX]
        if zero_pair:
            zero_coordinate_groups.add(group_key)
        if klass == "numeric_source_coordinate":
            usable_coordinate_groups.add(group_key)
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
            source_provided_coordinate_count += chosen[7] in {"source-provided", "source-provided-unspecified"}
    for parsed in parsed_rows:
        identifier, klass, country, city, postal, lat, lon, precision, observed, _, department = parsed[:11]
        group_key = parsed[SOURCE_GROUP_KEY_INDEX]
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
        group_key = parsed[SOURCE_GROUP_KEY_INDEX]
        observations_per_group[group_key] = observations_per_group.get(group_key, 0) + 1
    coarse_placeable = 0
    for group_key, chosen in representatives.items():
        identifier, klass, country, city, postal, lat, lon, precision, observed, _, department = chosen[:11]
        display_name, activity_label, activity_source, source_record_url, evidence_summary = chosen[11:16]
        default_map_scope, map_scope_reason = chosen[16:18]
        facility_address, coordinate_method, coordinate_provider, coordinate_confidence, coordinate_confidence_band = chosen[18:23]
        activity = merge_activity_contracts(activity_contracts_by_group.get(str(group_key), []), source)
        activity_label = safe_preview_text("; ".join(activity["source_activity_labels"]), 240)
        if activity_label is None:
            activity_label = activity["category"]
        activity_source = "source" if activity_label else None
        municipality_code = administrative_codes.get(str(identifier))
        place, place_match = _resolve_municipality(municipality_index or {}, city, municipality_policy or {}, department)
        display_lat = place.get("latitude") if isinstance(place, dict) else None
        display_lon = place.get("longitude") if isinstance(place, dict) else None
        source_coordinate_provenance = None
        if klass == "numeric_source_coordinate" and source == "au.npi.facilities":
            display_lat, display_lon = lat, lon
            source_coordinate_provenance = (
                "Source coordinates; method=source_coordinates; "
                "provider=Australian National Pollutant Inventory; "
                f"confidence=high_source_reported_location; precision={precision or 'source-provided'}"
            )
        if display_lat is not None and display_lon is not None:
            coarse_placeable += klass == "city_postal"
        preview_id = db.execute(
            "SELECT preview_id FROM real_preview.observations WHERE snapshot_sha256=%s AND source_id=%s AND source_identifier=%s",
            (snapshot, source, identifier),
        ).fetchone()[0]
        db.execute(
            """INSERT INTO real_preview.candidates
            (snapshot_sha256,source_id,source_group_key,representative_observation_id,location_class,country_code,city,postal_code,latitude,longitude,coordinate_precision,observation_count,display_latitude,display_longitude,display_geometry_source,display_name,activity_label,activity_source,source_record_url,evidence_summary,source_name,observed_at,default_map_scope,map_scope_reason,facility_address,coordinate_method,coordinate_provider,coordinate_confidence,coordinate_confidence_band,municipality_code,category,activity_categories,source_activity_codes,source_activity_labels,activity_mapping_status,classification_ruleset_version)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (snapshot_sha256,source_id,source_group_key) DO NOTHING""",
            (snapshot, source, group_key, preview_id, klass, country, city, postal, lat, lon, precision, observations_per_group[group_key], display_lat, display_lon,
             source_coordinate_provenance or (f"{(municipality_policy or {}).get('source', 'Administrative commune reference')}; approximate city location, not facility coordinates; name_match={place_match}" if display_lat is not None else None),
             display_name, activity_label, activity_source, source_record_url, evidence_summary, SOURCE_NAMES.get(source), observed,
             default_map_scope, map_scope_reason, facility_address, coordinate_method, coordinate_provider,
             coordinate_confidence, coordinate_confidence_band, municipality_code, activity["category"], activity["activity_categories"],
             activity["source_activity_codes"], activity["source_activity_labels"], activity["activity_mapping_status"],
             activity["classification_ruleset_version"]),
        )
        candidate_id = db.execute(
            "SELECT candidate_id FROM real_preview.candidates WHERE snapshot_sha256=%s AND source_id=%s AND source_group_key=%s",
            (snapshot, source, group_key),
        ).fetchone()[0]
        if activity["crosswalk_document"]:
            persist_preview_candidate_assignment_set(
                db,
                candidate_id=str(candidate_id),
                representative_observation_id=str(preview_id),
                snapshot_sha256=snapshot,
                source_id=source,
                document=activity["crosswalk_document"],
                assignment_rows=activity["taxonomy_assignment_rows"],
            )
        enrichment_state, enrichment_reason = (
            ("source_coordinate", "source_coordinate_present") if klass == "numeric_source_coordinate" else
            ("resolved", "local_coarse_reference_available") if display_lat is not None and display_lon is not None else
            ("coarse_eligible", "city_or_postal_reference_input") if klass == "city_postal" else
            ("insufficient", "no_usable_location_input")
        )
        db.execute(
            """INSERT INTO real_preview.enrichment_state_events
            (candidate_id,snapshot_sha256,source_id,source_record_key,state_code,reason_code)
            SELECT candidate.candidate_id,%s,%s,%s,%s,%s
            FROM real_preview.candidates candidate
            WHERE candidate.snapshot_sha256=%s AND candidate.source_id=%s AND candidate.source_group_key=%s
              AND NOT EXISTS (SELECT 1 FROM real_preview.enrichment_state_events event
                              WHERE event.candidate_id=candidate.candidate_id)""",
            (snapshot, source, group_key, enrichment_state, enrichment_reason,
             snapshot, source, group_key),
        )
    group_keys = set(representatives)
    rejected_zero_coordinates = len(zero_coordinate_groups - usable_coordinate_groups)
    return count, numeric_count, coarse_count, candidate_count, unmapped_count, mapped_non_candidate_count, len(group_keys), len(parsed_rows), rejected_zero_coordinates, precision_unknown_coordinate_count, source_provided_coordinate_count, group_keys, coarse_placeable, len(group_keys) - coarse_placeable


OFFLINE_HANDOFF_SOURCES = ("fr.dgal.section-i", "fr.dgal.section-ii", "it.853-2004", "us.fsis")


def verify_offline_handoff(root: Path, source: str) -> dict[str, Any]:
    """Verify one retained normalized handoff using local files only."""
    if root.is_symlink() or not root.is_dir():
        raise ImportFailure("offline_handoff_root_unavailable")
    if source not in OFFLINE_HANDOFF_SOURCES:
        raise ImportFailure("offline_source_not_supported")
    policy = json_object(POLICY).get("sources", {}).get(source)
    terms_path = Path(__file__).parents[3] / str(policy.get("terms_review", "")) if isinstance(policy, dict) else Path()
    if (not isinstance(policy, dict) or policy.get("enabled") is not True
            or json_object(terms_path).get("decision") != "approved"):
        raise ImportFailure("offline_preview_policy_blocked")
    manifest_path = root / "d6-graph-mvp" / "handoffs" / source / "manifest.json"
    normalized_path = manifest_path.parent / "normalized" / "records.jsonl"
    graph_manifest_path = manifest_path.parent / "graph-candidates" / "manifest.json"
    graph_records_path = graph_manifest_path.parent / "records.jsonl"
    for path in (manifest_path, normalized_path, graph_manifest_path, graph_records_path):
        if not path.is_file() or path.is_symlink():
            raise ImportFailure("offline_handoff_artifact_missing")
    manifest = json_object(manifest_path)
    graph_manifest = json_object(graph_manifest_path)
    if (manifest.get("source_id") != source
            or manifest.get("contract_version") != "candidate-handoff-v1"
            or manifest.get("publication_state") != "private-candidate"
            or manifest.get("release_state") != "not-created"
            or manifest.get("review_state") != "review_required"
            or manifest.get("privacy_gate") != "pending"
            or manifest.get("coordinate_gate") != "review_required"
            or manifest.get("code_version") != policy.get("adapter_version")
            or manifest.get("config_version") != policy.get("schema_version")
            or graph_manifest.get("schema_version") != "private-graph-candidate-set-v1"
            or graph_manifest.get("review_state") != "review_required"
            or graph_manifest.get("privacy_status") != "pending"
            or graph_manifest.get("publication_status") != "not_eligible"
            or graph_manifest.get("storage_state") != "private"
            or graph_manifest.get("auto_merge") is not False):
        raise ImportFailure("offline_handoff_provenance_mismatch")
    source_hash, normalized_hash, expected_rows, source_url, retrieved, code, config = manifest_provenance(manifest)
    normalized_actual, _ = digest_file(normalized_path)
    graph_actual, _ = digest_file(graph_records_path)
    if normalized_actual != normalized_hash:
        raise ImportFailure("offline_normalized_hash_mismatch")
    if graph_actual != graph_manifest.get("records_sha256"):
        raise ImportFailure("offline_graph_hash_mismatch")
    graph_rows = graph_manifest.get("candidate_rows")
    quarantined = graph_manifest.get("quarantined_source_rows")
    if (not isinstance(graph_rows, int) or graph_rows != expected_rows
            or count_jsonl_rows(graph_records_path) != graph_rows
            or not isinstance(quarantined, int) or quarantined < 0):
        raise ImportFailure("offline_handoff_count_mismatch")
    allowed_fields = policy.get("allowed_preview_fields")
    if not isinstance(allowed_fields, list) or not all(isinstance(field, str) for field in allowed_fields):
        raise ImportFailure("preview_policy_invalid")
    validate_preview_fields(normalized_path, set(allowed_fields))
    manifests = {source: (manifest_path, manifest)}
    snapshot = snapshot_identity(manifests)
    return {"source": source, "policy": policy, "manifest_path": manifest_path,
            "normalized_path": normalized_path, "graph_manifest_path": graph_manifest_path,
            "graph_records_path": graph_records_path, "manifest": manifest,
            "graph_manifest": graph_manifest, "source_hash": source_hash,
            "normalized_hash": normalized_hash, "source_url": source_url,
            "retrieved": retrieved, "code": code, "config": config,
            "expected_rows": expected_rows, "quarantined": quarantined,
            "normalized_actual": normalized_actual, "graph_actual": graph_actual,
            "snapshot": snapshot}


def verify_offline_handoffs(root: Path) -> list[dict[str, Any]]:
    """Verify the selected retained handoffs; never discovers or reacquires sources."""
    return [verify_offline_handoff(root, source) for source in OFFLINE_HANDOFF_SOURCES]


def import_offline_handoffs(root: Path, database_url: str) -> dict[str, Any]:
    """Import only verified retained packets without network or live-run claims."""
    verified = verify_offline_handoffs(root)
    snapshot = snapshot_identity({item["source"]: (item["manifest_path"], item["manifest"]) for item in verified})
    run_id = f"offline-handoff-{snapshot[:20]}"
    counts_by_source: dict[str, Any] = {}
    total_observations = total_candidates = total_visible = total_provided = total_numeric = total_city_postal = 0
    total_accepted = total_quarantined = 0
    public_releases = public_projection = 0
    expected_by_source = {item["source"]: item for item in verified}
    with psycopg.connect(database_url) as db:
        public_zero_counts(db)
        run_ids = [f"{run_id}-{source}" for source in OFFLINE_HANDOFF_SOURCES]
        existing = db.execute("""SELECT run_id,source_id,snapshot_sha256,normalized_sha256,input_count,accepted_count,
            quarantined_count,imported_observation_count,facility_count,numeric_coordinate_count,
            coarse_placeable_count,unmapped_count,map_visible_count,public_rows,runtime_details
            FROM real_preview.source_preview_runs WHERE run_id=ANY(%s)""", (run_ids,)).fetchall()
        if len(existing) == len(OFFLINE_HANDOFF_SOURCES):
            existing_by_source = {row[1]: row for row in existing}
            if set(existing_by_source) != set(OFFLINE_HANDOFF_SOURCES):
                raise ImportFailure("offline_existing_import_source_mismatch")
            existing_is_valid = True
            for source, item in expected_by_source.items():
                row = existing_by_source[source]
                details = row[14] if isinstance(row[14], dict) else {}
                if (row[2].strip() != snapshot or row[3].strip() != item["normalized_hash"]
                        or row[5] != item["expected_rows"] or row[6] != item["quarantined"]
                        or row[13] != 0 or details.get("offline_handoff") is not True
                        or details.get("fresh_live_run") is not False):
                    existing_is_valid = False
                    break
            if not existing_is_valid:
                raise ImportFailure("offline_existing_import_mismatch")
            for source, row in existing_by_source.items():
                coarse, provided, exact, unmapped_observations = db.execute("""SELECT
                    count(*) FILTER (WHERE location_class='city_postal'),
                    count(*) FILTER (WHERE source_id='us.fsis' AND coordinate_precision='source-provided'),
                    count(*) FILTER (WHERE coordinate_precision IN ('numeric','exact','source_numeric','source_coordinates','facility_coordinate')),
                    (SELECT count(*) FROM real_preview.observations WHERE snapshot_sha256=%s AND source_id=%s AND location_class='unmapped_private_observation')
                    FROM real_preview.candidates WHERE snapshot_sha256=%s AND source_id=%s""",
                    (snapshot, source, snapshot, source)).fetchone()
                counts_by_source[source] = {"accepted_normalized_rows": int(row[5]), "quarantined_source_rows": int(row[6]),
                    "observations": int(row[7]), "candidates": int(row[8]),
                    "source_provided_unverified": int(provided), "exact": int(exact), "coarse": int(coarse),
                    "coarse_placeable": int(row[10]),
                    # Map-unmapped means no honest point or approved coarse geometry.
                    # It is distinct from observations that lack all location hints.
                    "unmapped_candidates": map_unmapped_candidate_count(int(row[8]), int(row[12])),
                    "unmapped_observations": int(unmapped_observations), "map_visible": int(row[12])}
                total_observations += int(row[7]); total_candidates += int(row[8]); total_visible += int(row[12])
                total_provided += int(provided); total_numeric += int(row[9]); total_city_postal += int(coarse)
                total_accepted += int(row[5]); total_quarantined += int(row[6])
            public_releases, public_projection = public_zero_counts(db)
            return {"status": "imported", "source_id": "offline-retained-handoffs", "run_id": run_id,
                    "offline_handoff": True, "fresh_live_run": False, "source_bundle_bytes_retained": False,
                    "observation_count": total_observations, "source_scoped_candidate_count": total_candidates,
                    "numeric_coordinate_count": total_numeric, "city_postal_count": total_city_postal,
                    "accepted_normalized_rows": total_accepted, "quarantined_source_rows": total_quarantined,
                    "counts": {"observations": total_observations, "candidates": total_candidates,
                               "source_provided_unverified": total_provided, "exact": sum(v["exact"] for v in counts_by_source.values()),
                               "coarse": total_city_postal, "unmapped_candidates": sum(v["unmapped_candidates"] for v in counts_by_source.values()),
                               "map_visible": total_visible, "public_release_count": public_releases,
                               "public_projection_count": public_projection}, "by_source": counts_by_source}
    with psycopg.connect(database_url) as db, db.transaction():
        public_zero_counts(db)
        db.execute("INSERT INTO real_preview.imports(snapshot_sha256,observation_count) VALUES (%s,%s) ON CONFLICT DO NOTHING",
                   (snapshot, sum(item["expected_rows"] for item in verified)))
        for item in verified:
            source, manifest = item["source"], item["manifest"]
            source_hash, normalized_hash = item["source_hash"], item["normalized_hash"]
            source_url, retrieved, code, config = item["source_url"], item["retrieved"], item["code"], item["config"]
            expected_rows, quarantined = item["expected_rows"], item["quarantined"]
            db.execute("""INSERT INTO real_preview.source_manifests
                (snapshot_sha256,source_id,source_artifact_sha256,normalized_sha256,normalized_rows,source_url,retrieved_at,code_version,config_version)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                (snapshot, source, source_hash, normalized_hash, expected_rows, source_url, retrieved, code, config))
            (observations, numeric, coarse, candidates, unmapped, mapped_non_candidates, _, _, rejected_zero,
             precision_unknown, source_provided, _, placeable, unplaceable) = import_rows(
                db, source, item["normalized_path"], expected_rows, snapshot)
            details = {"offline_handoff": True, "fresh_live_run": False, "test_only_simulated_reviews": False,
                       "source_manifest_sha256": hashlib.sha256(item["manifest_path"].read_bytes()).hexdigest(),
                       "graph_manifest_sha256": hashlib.sha256(item["graph_manifest_path"].read_bytes()).hexdigest(),
                       "graph_records_sha256": item["graph_actual"],
                       "accepted_normalized_rows": expected_rows, "quarantined_source_rows": quarantined,
                       "classification_note": "Pending records remain unapproved; only source-provided unverified coordinates are rendered in the local private rehearsal."}
            db.execute("""INSERT INTO real_preview.source_preview_runs
                (run_id,source_id,snapshot_sha256,source_url,retrieved_at,source_artifact_sha256,normalized_sha256,
                 adapter_version,schema_version,input_count,accepted_count,quarantined_count,out_of_scope_count,
                 imported_observation_count,facility_count,numeric_coordinate_count,coarse_placeable_count,unmapped_count,
                 api_listable_count,map_visible_count,idempotent_replay,public_rows,runtime_details)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,0,%s,%s,%s,%s,%s,%s,%s,false,0,%s)
                ON CONFLICT (run_id) DO NOTHING""",
                (f"{run_id}-{source}", source, snapshot, source_url, retrieved, source_hash, normalized_hash, code, config,
                 expected_rows + quarantined, expected_rows, quarantined, observations, candidates, numeric, placeable,
                 unplaceable, candidates, numeric + placeable, psycopg.types.json.Jsonb(details)))
            counts_by_source[source] = {"accepted_normalized_rows": expected_rows, "quarantined_source_rows": quarantined,
                "observations": observations, "candidates": candidates,
                "source_provided_unverified": source_provided if source == "us.fsis" else 0,
                "exact": 0, "coarse": coarse, "coarse_placeable": placeable,
                "unmapped_candidates": map_unmapped_candidate_count(candidates, numeric + placeable),
                "unmapped_observations": unmapped, "map_visible": numeric + placeable,
                "rejected_zero_coordinates": rejected_zero, "precision_unknown": precision_unknown}
            total_observations += observations
            total_candidates += candidates
            total_visible += numeric + placeable
            total_numeric += numeric
            total_city_postal += coarse
            total_provided += source_provided if source == "us.fsis" else 0
            total_accepted += expected_rows
            total_quarantined += quarantined
        public_releases, public_projection = public_zero_counts(db)
    return {"status": "imported", "source_id": "offline-retained-handoffs", "run_id": run_id,
            "offline_handoff": True, "fresh_live_run": False,
            "observation_count": total_observations,
            "source_scoped_candidate_count": total_candidates,
            "numeric_coordinate_count": total_numeric, "city_postal_count": total_city_postal,
            "source_bundle_bytes_retained": False,
            "accepted_normalized_rows": total_accepted, "quarantined_source_rows": total_quarantined,
            "counts": {"observations": total_observations, "candidates": total_candidates,
                       "source_provided_unverified": total_provided, "exact": 0,
                       "coarse": sum(item["coarse"] for item in counts_by_source.values()),
                       "unmapped_candidates": sum(item["unmapped_candidates"] for item in counts_by_source.values()),
                       "map_visible": total_visible, "public_release_count": public_releases,
                       "public_projection_count": public_projection},
            "by_source": counts_by_source}


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
        elif source_id == "dk.smiley":
            acquisition_path = root / "acquisition" / source_id / run_id / "acquisition-metadata.json"
            if not acquisition_path.is_file() or acquisition_path.is_symlink():
                raise ImportFailure("acquisition_provenance_missing")
            acquisition_evidence = json_object(acquisition_path)
            acquisition_artifact = acquisition_path.parent / "Smileydata.xml"
            if not acquisition_artifact.is_file() or acquisition_artifact.is_symlink():
                raise ImportFailure("acquisition_artifact_missing")
            artifact_hash, artifact_size = digest_file(acquisition_artifact)
            if (acquisition_evidence.get("source_id") != source_id
                    or acquisition_evidence.get("run_id") != run_id
                    or acquisition_evidence.get("sha256") != source_hash
                    or artifact_hash != source_hash
                    or artifact_size != acquisition_evidence.get("byte_size")
                    or acquisition_evidence.get("final_url") != manifest.get("source_url")
                    or acquisition_evidence.get("retrieved_at_utc") != manifest.get("retrieved_at_utc")
                    or not isinstance(acquisition_evidence.get("terms_review"), dict)
                    or acquisition_evidence["terms_review"].get("decision") != "approved"):
                raise ImportFailure("acquisition_provenance_invalid")
            acquisition_time = acquisition_evidence.get("retrieved_at_utc")
            try:
                acquisition_timestamp = datetime.fromisoformat(str(acquisition_time).replace("Z", "+00:00"))
            except ValueError:
                raise ImportFailure("acquisition_timestamp_invalid") from None
            if acquisition_timestamp.utcoffset() is None or acquisition_timestamp > datetime.now(timezone.utc) + timedelta(minutes=5):
                raise ImportFailure("acquisition_timestamp_invalid")
            if datetime.now(timezone.utc) - acquisition_timestamp > timedelta(days=policy["freshness_max_days"]):
                raise ImportFailure("source_artifact_stale")
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
        elif source_id == "it.1069-2009":
            acquisition_path = root / "acquisition" / source_id / run_id / "acquisition-metadata.json"
            if not acquisition_path.is_file() or acquisition_path.is_symlink():
                raise ImportFailure("acquisition_provenance_missing")
            acquisition_evidence = json_object(acquisition_path)
            artifact_value = acquisition_evidence.get("artifact_path")
            if not isinstance(artifact_value, str):
                raise ImportFailure("acquisition_artifact_path_missing")
            acquired_file = Path(artifact_value)
            if not acquired_file.is_file() or acquired_file.is_symlink() or acquired_file.resolve() != (root / "acquisition" / source_id / run_id / "source.csv").resolve():
                raise ImportFailure("acquisition_artifact_path_invalid")
            artifact_hash, artifact_size = digest_file(acquired_file)
            if (acquisition_evidence.get("source_id") != source_id
                    or acquisition_evidence.get("run_id") != run_id
                    or acquisition_evidence.get("sha256") != source_hash
                    or artifact_hash != source_hash or artifact_size != acquisition_evidence.get("byte_size")
                    or acquisition_evidence.get("final_url") != manifest.get("source_url")
                    or acquisition_evidence.get("retrieved_at_utc") != manifest.get("retrieved_at_utc")
                    or not isinstance(acquisition_evidence.get("terms_review"), dict)
                    or acquisition_evidence["terms_review"].get("decision") != "approved"):
                raise ImportFailure("acquisition_provenance_mismatch")
        elif source_id == "es.cat.feed-sandach":
            acquisition_path = root / "acquisition" / source_id / run_id / "acquisition-metadata.json"
            if not acquisition_path.is_file() or acquisition_path.is_symlink():
                raise ImportFailure("acquisition_provenance_missing")
            acquisition_evidence = json_object(acquisition_path)
            artifact_value = acquisition_evidence.get("artifact_path")
            if not isinstance(artifact_value, str):
                raise ImportFailure("acquisition_artifact_path_missing")
            acquired_file = Path(artifact_value)
            if not acquired_file.is_file() or acquired_file.is_symlink() or acquired_file.resolve() != (root / "acquisition" / source_id / run_id / "source.csv").resolve():
                raise ImportFailure("acquisition_artifact_path_invalid")
            artifact_hash, artifact_size = digest_file(acquired_file)
            if (acquisition_evidence.get("source_id") != source_id
                    or acquisition_evidence.get("run_id") != run_id
                    or acquisition_evidence.get("sha256") != source_hash
                    or artifact_hash != source_hash or artifact_size != acquisition_evidence.get("byte_size")
                    or acquisition_evidence.get("provenance_url") != manifest.get("source_url")
                    or acquisition_evidence.get("retrieved_at_utc") != manifest.get("retrieved_at_utc")
                    or not isinstance(acquisition_evidence.get("terms_review"), dict)
                    or acquisition_evidence["terms_review"].get("decision") != "approved"):
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
        elif source_id == "au.sa.epa.licensed-activities":
            acquisition_path = root / "acquisition" / source_id / run_id / "acquisition-metadata.json"
            expected_artifact = root / "acquisition" / source_id / run_id / "source.geojson"
            if not acquisition_path.is_file() or acquisition_path.is_symlink():
                raise ImportFailure("acquisition_provenance_missing")
            acquisition_evidence = json_object(acquisition_path)
            artifact_value = acquisition_evidence.get("artifact_path")
            if (not isinstance(artifact_value, str) or Path(artifact_value).resolve() != expected_artifact.resolve()
                    or not expected_artifact.is_file() or expected_artifact.is_symlink()):
                raise ImportFailure("acquisition_artifact_mismatch")
            artifact_hash, artifact_size = digest_file(expected_artifact)
            try:
                acquired_at = datetime.fromisoformat(str(acquisition_evidence.get("retrieved_at_utc")).replace("Z", "+00:00"))
            except ValueError:
                raise ImportFailure("acquisition_timestamp_invalid") from None
            terms_evidence = acquisition_evidence.get("terms_review")
            if (acquisition_evidence.get("source_id") != source_id
                    or acquisition_evidence.get("source_title") != "EPA Licensed Activities"
                    or acquisition_evidence.get("run_id") != run_id
                    or acquisition_evidence.get("canonical_url") != manifest.get("source_url")
                    or acquisition_evidence.get("final_url") != manifest.get("source_url")
                    or acquisition_evidence.get("sha256") != source_hash
                    or artifact_hash != source_hash
                    or acquisition_evidence.get("byte_size") != artifact_size
                    or acquisition_evidence.get("license") != "Creative Commons Attribution 3.0 Australia"
                    or acquisition_evidence.get("license_url") != "http://creativecommons.org/licenses/by/3.0/au/"
                    or not acquisition_evidence.get("catalog_resource_updated_at")
                    or acquisition_evidence.get("effective_date") != source_summary.get("source_as_of")
                    or acquisition_evidence.get("retrieved_at_utc") != manifest.get("retrieved_at_utc")
                    or not isinstance(terms_evidence, dict)
                    or terms_evidence.get("source_id") != source_id
                    or terms_evidence.get("decision") != "approved"
                    or terms_evidence.get("private_preview_only") is not True
                    or acquired_at.utcoffset() is None
                    or acquired_at > datetime.now(timezone.utc) + timedelta(minutes=5)
                    or datetime.now(timezone.utc) - acquired_at > timedelta(days=max_age)):
                raise ImportFailure("acquisition_provenance_mismatch")
        elif source_id == "au.npi.facilities":
            acquisition_path = root / "acquisition" / source_id / run_id / "acquisition-metadata.json"
            expected_artifact = root / "acquisition" / source_id / run_id / "source.csv"
            if not acquisition_path.is_file() or acquisition_path.is_symlink():
                raise ImportFailure("acquisition_provenance_missing")
            acquisition_evidence = json_object(acquisition_path)
            artifact_value = acquisition_evidence.get("artifact_path")
            if (not isinstance(artifact_value, str) or Path(artifact_value).resolve() != expected_artifact.resolve()
                    or not expected_artifact.is_file() or expected_artifact.is_symlink()):
                raise ImportFailure("acquisition_artifact_mismatch")
            artifact_hash, artifact_size = digest_file(expected_artifact)
            try:
                acquired_at = datetime.fromisoformat(str(acquisition_evidence.get("retrieved_at_utc")).replace("Z", "+00:00"))
            except ValueError:
                raise ImportFailure("acquisition_timestamp_invalid") from None
            terms_evidence = acquisition_evidence.get("terms_review")
            if (acquisition_evidence.get("source_id") != source_id
                    or acquisition_evidence.get("source_title") != "National Pollutant Inventory"
                    or acquisition_evidence.get("run_id") != run_id
                    or acquisition_evidence.get("catalog_url") != "https://data.gov.au/data/api/3/action/package_show?id=043f58e0-a188-4458-b61c-04e5b540aea4"
                    or acquisition_evidence.get("catalog_resource_updated_at") != acquisition_evidence.get("effective_date")
                    or acquisition_evidence.get("requested_url") != "https://data.gov.au/data/dataset/043f58e0-a188-4458-b61c-04e5b540aea4/resource/f83cdee9-ebcb-4f24-941b-34bb2f0996cf/download/facilities.csv"
                    or acquisition_evidence.get("final_url") != acquisition_evidence.get("requested_url")
                    or acquisition_evidence.get("canonical_url") != manifest.get("source_url")
                    or acquisition_evidence.get("sha256") != source_hash or artifact_hash != source_hash
                    or acquisition_evidence.get("byte_size") != artifact_size
                    or acquisition_evidence.get("license") != "Creative Commons Attribution 4.0 International"
                    or acquisition_evidence.get("license_url") != "http://creativecommons.org/licenses/by/4.0"
                    or acquisition_evidence.get("retrieved_at_utc") != manifest.get("retrieved_at_utc")
                    or not isinstance(terms_evidence, dict)
                    or terms_evidence.get("source_id") != source_id
                    or terms_evidence.get("decision") != "approved"
                    or terms_evidence.get("private_preview_only") is not True
                    or acquired_at.utcoffset() is None
                    or acquired_at > datetime.now(timezone.utc) + timedelta(minutes=5)
                    or datetime.now(timezone.utc) - acquired_at > timedelta(days=max_age)):
                raise ImportFailure("acquisition_provenance_mismatch")
        elif source_id == "us.fsis":
            source_artifacts = manifest.get("source_artifacts")
            bundle = manifest.get("bundle_artifact")
            if not isinstance(source_artifacts, dict) or not isinstance(bundle, dict):
                raise ImportFailure("fsis_bundle_provenance_missing")
            fsis_evidence: dict[str, dict[str, Any]] = {}
            for role, source in (("directory", "us.fsis.directory"), ("demographics", "us.fsis.demographics")):
                evidence_path = root / "acquisition" / source / run_id / "acquisition-metadata.json"
                if not evidence_path.is_file() or evidence_path.is_symlink():
                    raise ImportFailure("fsis_acquisition_provenance_missing")
                evidence = json_object(evidence_path)
                if (evidence.get("source_id") != source or evidence.get("run_id") != run_id
                        or evidence.get("acquisition_method") != "firefox_browser_download"
                        or not isinstance(evidence.get("terms_review"), dict)
                        or evidence["terms_review"].get("decision") != "approved"
                        or not isinstance(evidence.get("acquisition_authorization"), dict)
                        or evidence["acquisition_authorization"].get("status") != "authorized"):
                    raise ImportFailure("fsis_acquisition_provenance_mismatch")
                artifact_path = evidence.get("artifact_path")
                if not isinstance(artifact_path, str):
                    raise ImportFailure("fsis_acquisition_artifact_mismatch")
                artifact_file = Path(artifact_path)
                if not artifact_file.is_file() or artifact_file.is_symlink():
                    raise ImportFailure("fsis_acquisition_artifact_mismatch")
                actual_hash, actual_size = digest_file(artifact_file)
                if actual_hash != evidence.get("sha256") or actual_size != evidence.get("byte_size"):
                    raise ImportFailure("fsis_acquisition_artifact_mismatch")
                if source_artifacts.get(role, {}).get("sha256") != actual_hash:
                    raise ImportFailure("fsis_handoff_artifact_mismatch")
                try:
                    acquired_at = datetime.fromisoformat(str(evidence.get("retrieved_at_utc")).replace("Z", "+00:00"))
                except ValueError:
                    raise ImportFailure("fsis_acquisition_timestamp_invalid") from None
                if acquired_at.utcoffset() is None or acquired_at > datetime.now(timezone.utc) + timedelta(minutes=5):
                    raise ImportFailure("fsis_acquisition_timestamp_invalid")
                if datetime.now(timezone.utc) - acquired_at > timedelta(days=max_age):
                    raise ImportFailure("fsis_acquisition_artifact_stale")
                fsis_evidence[role] = evidence
            if fsis_evidence["directory"].get("sha256") != source_hash:
                raise ImportFailure("fsis_directory_checksum_mismatch")
            bundle_digest = hashlib.sha256("".join(
                f"{role}:{fsis_evidence[role]['sha256']}\n" for role in sorted(fsis_evidence)
            ).encode()).hexdigest()
            if bundle.get("sha256") != bundle_digest:
                raise ImportFailure("fsis_bundle_checksum_mismatch")
            acquisition_evidence = {role: {
                key: evidence.get(key) for key in (
                    "source_id", "run_id", "requested_url", "final_url", "retrieved_at_utc",
                    "effective_date", "sha256", "byte_size", "terms_review", "browser", "attempts")
            } for role, evidence in fsis_evidence.items()}
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
            expected_file_url = geometry_policy.get("source_file_url") or geometry_policy.get("source_url")
            if index_payload.get("source_url") != expected_file_url:
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
    snapshot = snapshot_identity(manifests)
    if source_id is not None:
        allowed_fields = policy.get("allowed_preview_fields")
        if not isinstance(allowed_fields, list) or not all(isinstance(field, str) for field in allowed_fields):
            raise ImportFailure("preview_policy_invalid")
        validate_preview_fields(artifacts[source_id], set(allowed_fields))
        if municipality_index is not None:
            # Retrieval timestamps change on each official refresh; only geography and
            # the approved resolution policy belong in the idempotency identity.
            geometry_fingerprint = hashlib.sha256(json.dumps({
                "resolver_version": policy.get("display_policy", {}).get("version"),
                "municipalities": municipality_index,
            }, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()
            snapshot = snapshot_identity(manifests, geometry_fingerprint)
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
                               "source_specific_counts": {key: source_summary.get(key) for key in (
                                   "source_title", "source_feature_count", "accepted_rows", "rejected_rows",
                                   "out_of_scope_rows", "quarantined_coordinate_claims", "coordinate_quarantine_reasons",
                                   "activity_counts", "observed_activity_categories", "source_license",
                                   "source_canonical_url", "source_as_of", "graph_relationships_emitted")},
                               "geometry_reference": ({**{key: index_payload.get(key) for key in ("source", "source_url", "license", "reference_date", "retrieved_at_utc", "source_last_modified", "source_sha256", "source_byte_size", "method", "version")}, "derived_index_sha256": digest_file(municipality_index_path)[0]} if municipality_index is not None else None),
                               "fresh_live_run": True, "preview_policy_version": json_object(POLICY).get("contract_version"),
                               "preview_candidate_projection_version": SNAPSHOT_PROJECTION_VERSION}
            if source_id == "au.npi.facilities":
                runtime_details["source_specific_counts"].update({
                    key: source_summary.get(key) for key in (
                        "coordinate_counts", "industry_relevance_counts", "primary_anzsic_code_counts",
                        "address_review_signal_counts")
                })
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
    parser.add_argument("--offline-handoff", action="store_true", help="import only the hash-verified retained FSIS private handoff; never reacquire")
    args = parser.parse_args()
    result: dict[str, Any]
    try:
        database_url = os.environ.get(args.database_url_env)
        if not database_url:
            raise ImportFailure("database_configuration_missing")
        if args.offline_handoff:
            if args.source_id not in (None, "us.fsis"):
                raise ImportFailure("offline_source_not_supported")
            result = import_offline_handoffs(args.root, database_url)
        else:
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
        frames = traceback.extract_tb(sys.exc_info()[2])
        last_frame = frames[-1] if frames else None
        result = {"status": "failed", "error_code": "import_failed", "observation_count": 0,
                  "facility_candidate_count": 0, "numeric_coordinate_count": 0, "city_postal_count": 0,
                  "unmapped_observation_count": 0, "mapped_non_candidate_observation_count": 0,
                  "error_type": type(sys.exc_info()[1]).__name__,
                  "error_location": ({"file": Path(last_frame.filename).name, "line": last_frame.lineno}
                                     if last_frame else None),
                  "public_release_count": 0, "public_projection_count": 0}
        print(json.dumps(result, separators=(",", ":")))
        return 2
    print(json.dumps(result, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
