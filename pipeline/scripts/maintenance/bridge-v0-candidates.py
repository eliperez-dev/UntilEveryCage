#!/usr/bin/env python3
"""Bridge an explicitly frozen private preview pool into candidate-only UEC rows.

This is not an acquisition, approval, validation, or publication command. It
requires a separate loopback review database, a frozen source selection, and
an explicit candidate-only acknowledgement. It stores no raw payloads and
never creates review events, rights decisions, or public projections.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import psycopg
from psycopg.types.json import Jsonb
from pipeline.taxonomy.contract import crosswalk_sha256

ROOT = Path(__file__).resolve().parents[3]
IMPORTER_PATH = ROOT / "pipeline" / "scripts" / "maintenance" / "import-real-preview.py"
SPEC = importlib.util.spec_from_file_location("uec_real_preview_importer", IMPORTER_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("private preview parser unavailable")
IMPORTER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(IMPORTER)

SCHEMA = "v0-candidate-freeze-v1"
PROFILE = "official"
PUBLIC_PROJECTION_RELATIONS = (
    "uec.map_facilities_public_discovery",
    "uec.map_facilities_public_discovery_read_model",
    "uec.graph_public_relationships",
    "uec.graph_public_claims",
)
_HASH = re.compile(r"^[0-9a-f]{64}$")
_SAFE_RELEASE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{2,95}$")
_SAFE_REASON = re.compile(r"^[a-z][a-z0-9_:-]{0,63}$")
_FORBIDDEN_KEYS = {"name", "canonical_name", "operator_name", "trading_name", "contact",
                   "email", "phone", "telephone", "fax", "raw", "source_values", "payload"}
_NORMALIZED_KEYS = {
    "activity_categories", "activity_code", "activity_codes", "activity_descriptions",
    "activity_description", "activities", "animal_class", "classification_category",
    "classification_mapping_status", "classification_optional_filter",
    "classification_review_status", "classification_ruleset_version", "coordinate_method",
    "coordinate_precision", "coordinate_provider", "coordinate_confidence",
    "coordinate_confidence_band", "coordinates", "country_code", "county", "department_number",
    "establishment_id", "establishment_number", "facility_grouping_key", "facility_identity_state",
    "in_default_map_scope", "jurisdiction", "jurisdiction_level", "municipality", "municipality_code",
    "nation", "observation_date", "observation_identity_state", "occurrence_state",
    "postal_code", "postcode", "privacy_gate", "privacy_status", "processing_activities",
    "region", "region_code", "recognition_number", "registered_at", "source_activity",
    "source_activity_category", "source_activity_codes", "source_activity_labels",
    "source_classification_code", "source_classification_label", "source_observed_at",
    "source_record_key", "source_record_url", "source_registration_date", "source_reservation_date",
    "source_scope", "source_status", "source_type", "species_slaughtered", "state",
    "status_state", "activity_mapping_status", "activity_label",
    "private_geocode_scope", "private_geocode_scope_policy_id", "source_address_eligible",
    "source_address_restricted", "evidence_summary", "city",
}
_PRIVATE_LOCATION_KEYS = {"address", "address_lines", "city", "postal_code", "region", "country_code",
                          "coordinates", "municipality_code", "comarca_code", "department_number", "region_code"}


class BridgeError(ValueError):
    """Safe, non-payload-bearing bridge failure."""


def _digest(path: Path) -> tuple[str, int]:
    hasher = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(block)
            size += len(block)
    return hasher.hexdigest(), size


def _read_json(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise BridgeError("handoff_file_unavailable")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise BridgeError("handoff_json_invalid") from None
    if not isinstance(value, dict):
        raise BridgeError("handoff_json_invalid")
    return value


def _read_approved_terms(path: Path, source: str) -> tuple[dict[str, Any], str]:
    """Read an approved source decision and bind its exact bytes into provenance."""
    if path.is_symlink() or not path.is_file():
        raise BridgeError("source_terms_review_unavailable")
    try:
        raw = path.read_bytes()
        terms = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise BridgeError("source_terms_review_unavailable") from None
    if (not isinstance(terms, dict) or terms.get("decision") != "approved"
            or ("source_id" in terms and terms.get("source_id") != source)):
        raise BridgeError("source_terms_review_not_approved")
    return terms, hashlib.sha256(raw).hexdigest()


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if path.is_symlink() or not path.is_file():
        raise BridgeError("handoff_file_unavailable")
    rows = []
    try:
        with path.open("r", encoding="utf-8") as stream:
            for line in stream:
                if not line.strip():
                    raise BridgeError("handoff_row_invalid")
                row = json.loads(line)
                if not isinstance(row, dict):
                    raise BridgeError("handoff_row_invalid")
                rows.append(row)
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise BridgeError("handoff_row_invalid") from None
    return rows


def _utc(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise BridgeError(f"{field}_invalid")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise BridgeError(f"{field}_invalid") from None
    if result.utcoffset() is None:
        raise BridgeError(f"{field}_invalid")
    return result.astimezone(timezone.utc)


def _source_paths(entry: dict[str, Any]) -> tuple[Path, Path, Path, Path]:
    manifest_path = Path(str(entry.get("handoff_manifest_path", "")))
    if not manifest_path.is_absolute():
        raise BridgeError("handoff_manifest_path_invalid")
    if manifest_path.is_symlink():
        raise BridgeError("handoff_manifest_path_invalid")
    manifest_path = manifest_path.resolve(strict=True)
    if manifest_path.name != "manifest.json":
        raise BridgeError("handoff_manifest_path_invalid")
    folder = manifest_path.parent
    return (manifest_path, folder / "normalized" / "records.jsonl",
            folder / "graph-candidates" / "manifest.json",
            folder / "graph-candidates" / "records.jsonl")


def _frozen_inventory_matches(path: Path, expected_hash: str, expected_sources: set[str]) -> dict[str, Any]:
    try:
        inventory = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise BridgeError("frozen_inventory_invalid") from None
    if not isinstance(inventory, dict) or inventory.get("status") != "measured":
        raise BridgeError("frozen_inventory_not_measured")
    claimed = inventory.get("inventory_sha256")
    unhashed = dict(inventory)
    unhashed.pop("inventory_sha256", None)
    unhashed.pop("read_at_utc", None)
    actual = hashlib.sha256((json.dumps(unhashed, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()).hexdigest()
    if not _HASH.fullmatch(str(expected_hash)) or claimed != expected_hash or actual != expected_hash:
        raise BridgeError("frozen_inventory_hash_mismatch")
    sources = inventory.get("source_scope", {}).get("sources", [])
    source_ids = {str(item.get("source_id")) for item in sources if isinstance(item, dict)}
    if source_ids != expected_sources:
        raise BridgeError("frozen_inventory_source_set_mismatch")
    for item in sources:
        rec = item.get("snapshot", {}).get("manifest_reconciliation", {})
        physical = item.get("physical_reconciliation", {})
        if (not isinstance(rec, dict) or not all(value is True for value in rec.values())
                or not isinstance(physical, dict) or not all(value is True for value in physical.values())):
            raise BridgeError("frozen_inventory_reconciliation_failed")
    return inventory


def load_freeze(path: Path, inventory_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    freeze = _read_json(path)
    if freeze.get("schema_version") != SCHEMA:
        raise BridgeError("freeze_schema_invalid")
    release_id = freeze.get("release_id")
    if (not isinstance(release_id, str) or not _SAFE_RELEASE_ID.fullmatch(release_id)
            or not release_id.startswith("v0-candidate-")):
        raise BridgeError("release_id_invalid")
    inventory_hash = freeze.get("inventory_sha256")
    selected = freeze.get("selected_sources")
    excluded = freeze.get("excluded_sources")
    if not isinstance(selected, list) or not selected or not isinstance(excluded, list):
        raise BridgeError("freeze_selection_invalid")
    selected_ids = [item.get("source_id") for item in selected if isinstance(item, dict)]
    excluded_ids = [item.get("source_id") for item in excluded if isinstance(item, dict)]
    if len(selected_ids) != len(selected) or len(set(selected_ids)) != len(selected_ids):
        raise BridgeError("freeze_selection_invalid")
    if len(excluded_ids) != len(excluded) or len(set(excluded_ids)) != len(excluded_ids):
        raise BridgeError("freeze_exclusions_invalid")
    for item in excluded:
        if not isinstance(item.get("reason_code"), str) or not _SAFE_REASON.fullmatch(item["reason_code"]):
            raise BridgeError("freeze_exclusion_reason_invalid")
    if set(selected_ids) & set(excluded_ids):
        raise BridgeError("freeze_selection_overlaps_exclusions")
    inventory = _frozen_inventory_matches(inventory_path, str(inventory_hash), set(selected_ids) | set(excluded_ids))
    by_id = {row["source_id"]: row for row in inventory["source_scope"]["sources"]}
    for item in selected:
        expected = by_id.get(item["source_id"])
        snapshot = expected.get("snapshot", {}) if expected else {}
        for field in ("snapshot_sha256", "source_artifact_sha256", "normalized_sha256"):
            if item.get(field) != snapshot.get(field):
                raise BridgeError("freeze_source_provenance_mismatch")
        for field in ("accepted_count", "quarantined_count", "imported_observation_count", "facility_count"):
            if item.get(field) != expected.get("counts", {}).get(field):
                raise BridgeError("freeze_source_count_mismatch")
        if item.get("source_bytes_state") not in {"retained", "not_retained"}:
            raise BridgeError("freeze_artifact_retention_state_invalid")
        if item.get("source_bytes_state") == "retained":
            locator = item.get("source_artifact_path")
            if not isinstance(locator, str) or not Path(locator).is_absolute():
                raise BridgeError("retained_artifact_locator_missing")
            if Path(locator).is_symlink():
                raise BridgeError("retained_artifact_locator_invalid")
            digest, size = _digest(Path(locator))
            if digest != item.get("source_artifact_sha256") or item.get("source_artifact_byte_size") != size:
                raise BridgeError("retained_artifact_verification_failed")
        elif item.get("source_artifact_path") is not None or item.get("source_artifact_byte_size") is not None:
            raise BridgeError("not_retained_artifact_metadata_must_be_null")
    return freeze, inventory


def verify_handoff(entry: dict[str, Any], inventory_source: dict[str, Any]) -> dict[str, Any]:
    source = str(entry["source_id"])
    manifest_path, normalized_path, graph_manifest_path, graph_records_path = _source_paths(entry)
    manifest = _read_json(manifest_path)
    graph_manifest = _read_json(graph_manifest_path)
    if (manifest.get("source_id") != source
            or manifest.get("contract_version") != "candidate-handoff-v1"
            or manifest.get("publication_state") != "private-candidate"
            or manifest.get("release_state") != "not-created"
            or manifest.get("review_state") != "review_required"
            or manifest.get("privacy_gate") != "pending"
            or manifest.get("coordinate_gate") != "review_required"):
        raise BridgeError("handoff_policy_state_invalid")
    if (graph_manifest.get("schema_version") != "private-graph-candidate-set-v1"
            or graph_manifest.get("review_state") != "review_required"
            or graph_manifest.get("privacy_status") != "pending"
            or graph_manifest.get("publication_status") != "not_eligible"
            or graph_manifest.get("storage_state") != "private"
            or graph_manifest.get("auto_merge") is not False):
        raise BridgeError("graph_handoff_policy_state_invalid")
    expected = inventory_source["snapshot"]
    try:
        source_hash, manifest_normalized, manifest_count, source_url, retrieved, code, config = IMPORTER.manifest_provenance(manifest)
    except IMPORTER.ImportFailure:
        raise BridgeError("handoff_manifest_provenance_invalid") from None
    if (source_hash != expected["source_artifact_sha256"]
            or manifest_normalized != expected["normalized_sha256"]
            or manifest_count != inventory_source["counts"]["imported_observation_count"]
            or not source_url):
        raise BridgeError("handoff_manifest_inventory_mismatch")
    if (_utc(retrieved.isoformat(), "retrieved_at").isoformat() != _utc(expected["retrieved_at"], "retrieved_at").isoformat()
            or code != inventory_source["snapshot"].get("handoff_code_version")
            or config != inventory_source["snapshot"].get("handoff_config_version")):
        raise BridgeError("handoff_version_or_retrieval_mismatch")
    if urlsplit(source_url).hostname != inventory_source["snapshot"].get("source_host"):
        raise BridgeError("handoff_source_host_mismatch")
    normalized_hash, normalized_bytes = _digest(normalized_path)
    if normalized_hash != expected["normalized_sha256"]:
        raise BridgeError("normalized_handoff_hash_mismatch")
    graph_hash, _ = _digest(graph_records_path)
    if graph_hash != graph_manifest.get("records_sha256"):
        raise BridgeError("graph_handoff_hash_mismatch")
    rows = _read_jsonl(normalized_path)
    if len(rows) != inventory_source["counts"]["imported_observation_count"]:
        raise BridgeError("normalized_handoff_count_mismatch")
    if graph_manifest.get("candidate_rows") != len(rows):
        raise BridgeError("graph_handoff_count_mismatch")
    policy_path = ROOT / "pipeline" / "preview-enabled-sources.json"
    policy = json.loads(policy_path.read_text(encoding="utf-8")).get("sources", {}).get(source)
    if not isinstance(policy, dict) or policy.get("enabled") is not True:
        raise BridgeError("source_preview_policy_disabled")
    if policy.get("terms_decision") != "approved" or not isinstance(policy.get("terms_review"), str):
        raise BridgeError("source_terms_review_unavailable")
    terms_path = ROOT / policy["terms_review"]
    terms, terms_digest = _read_approved_terms(terms_path, source)
    IMPORTER.validate_preview_fields(normalized_path, set(policy.get("allowed_preview_fields", [])))
    parsed = []
    grouped: dict[str, list[tuple[tuple[Any, ...], dict[str, Any]]]] = defaultdict(list)
    for row in rows:
        value = IMPORTER.parse_row(source, row)
        grouped[str(value[IMPORTER.SOURCE_GROUP_KEY_INDEX])].append((value, row))
        parsed.append((value, row))
    graph_rows = _read_jsonl(graph_records_path)
    graph_keys = []
    for row in rows:
        graph_key = row.get("source_record_key", row.get("source_row_id"))
        source_row = row.get("source_row")
        graph_keys.append((source, str(graph_key), source_row))
    actual_graph_keys = [(str(row.get("source_id")), str(row.get("source_record_key")), row.get("source_row"))
                         for row in graph_rows]
    if sorted(graph_keys, key=str) != sorted(actual_graph_keys, key=str):
        raise BridgeError("graph_handoff_identifier_set_mismatch")
    representatives = {}
    for group, members in grouped.items():
        representatives[group] = min(members, key=lambda pair: (
            0 if pair[0][1] == "numeric_source_coordinate" else 1,
            pair[0][0],
        ))
    return {
        "source_id": source,
        "manifest_path": manifest_path,
        "normalized_path": normalized_path,
        "graph_manifest_path": graph_manifest_path,
        "graph_records_path": graph_records_path,
        "manifest": manifest,
        "graph_manifest": graph_manifest,
        "source_url": source_url,
        "source_host": urlsplit(source_url).hostname,
        "normalized_sha256": normalized_hash,
        "normalized_byte_size": normalized_bytes,
        "graph_records_sha256": graph_hash,
        "terms_review_sha256": terms_digest,
        "rows": parsed,
        "groups": grouped,
        "representatives": representatives,
    }


def _verify_preview_source(connection: Any, source: str, entry: dict[str, Any], handoff: dict[str, Any]) -> dict[str, Any]:
    snapshot = entry["snapshot_sha256"]
    run = connection.execute("""SELECT source_artifact_sha256, normalized_sha256, source_url, retrieved_at,
            accepted_count, quarantined_count, imported_observation_count, facility_count, public_rows
        FROM real_preview.source_preview_runs WHERE source_id=%s AND snapshot_sha256=%s""",
        (source, snapshot)).fetchone()
    manifest = connection.execute("""SELECT source_artifact_sha256, normalized_sha256, normalized_rows,
            source_url, retrieved_at, code_version, config_version
        FROM real_preview.source_manifests WHERE source_id=%s AND snapshot_sha256=%s""",
        (source, snapshot)).fetchone()
    if run is None or manifest is None:
        raise BridgeError("preview_snapshot_missing")
    expected = entry
    current = connection.execute("""SELECT snapshot_sha256 FROM real_preview.source_preview_runs
        WHERE source_id=%s ORDER BY created_at DESC,run_id DESC LIMIT 1""", (source,)).fetchone()
    if current is None or str(current[0]).strip() != snapshot:
        raise BridgeError("frozen_source_snapshot_is_not_latest")
    if (str(run[0]).strip() != expected["source_artifact_sha256"]
            or str(run[1]).strip() != expected["normalized_sha256"]
            or str(manifest[0]).strip() != expected["source_artifact_sha256"]
            or str(manifest[1]).strip() != expected["normalized_sha256"]
            or int(manifest[2]) != len(handoff["rows"])
            or int(run[6]) != len(handoff["rows"])
            or int(run[4]) != entry["accepted_count"]
            or int(run[5]) != entry["quarantined_count"]
            or int(run[7]) != len(handoff["representatives"])
            or int(run[8]) != 0):
        raise BridgeError("preview_snapshot_provenance_mismatch")
    if str(run[2]) != str(manifest[3]) or run[3] != manifest[4]:
        raise BridgeError("preview_run_manifest_mismatch")
    obs_rows = connection.execute("""SELECT preview_id::text,source_identifier,location_class,country_code,city,postal_code,
            latitude,longitude,coordinate_precision,source_observed_at,facility_candidate
        FROM real_preview.observations WHERE source_id=%s AND snapshot_sha256=%s""", (source, snapshot)).fetchall()
    preview_observations = {str(row[1]): row[2:] for row in obs_rows}
    preview_id_by_identifier = {str(row[1]): str(row[0]) for row in obs_rows}
    if len(preview_observations) != len(handoff["rows"]):
        raise BridgeError("preview_observation_count_mismatch")
    candidate_rows = connection.execute("""SELECT candidate_id::text,source_group_key,
            representative_observation_id::text,location_class,country_code,city,postal_code,
            latitude,longitude,coordinate_precision,observation_count,display_latitude,display_longitude,
            display_geometry_source,coordinate_method,coordinate_provider,coordinate_confidence,
            coordinate_confidence_band,category,activity_categories,source_activity_codes,
            source_activity_labels,activity_mapping_status,classification_ruleset_version,
            geocode_evidence.display_precision,local_evidence.display_precision,local_evidence.reference_source,
            geocode_evidence.geocode_result_id,geocode_evidence.provider_id,geocode_evidence.status,
            geocode_evidence.queried_at,geocode_evidence.coordinate_review_status,
            local_evidence.evidence_id,local_evidence.reference_source_id
        FROM real_preview.candidates candidate
        LEFT JOIN LATERAL (
            SELECT evidence.display_precision,evidence.geocode_result_id::text,
                   result.provider_id,result.status,result.queried_at,evidence.coordinate_review_status
            FROM real_preview.geocode_display_evidence evidence
            JOIN uec.geocode_results result USING (geocode_result_id)
            WHERE evidence.candidate_id=candidate.candidate_id AND result.status='accepted'
            ORDER BY evidence.created_at DESC,evidence.geocode_result_id DESC LIMIT 1
        ) geocode_evidence ON true
        LEFT JOIN LATERAL (
            SELECT evidence.display_precision,evidence.reference_source,
                   evidence.evidence_id::text,evidence.reference_source_id
            FROM real_preview.local_reference_display_evidence evidence
            WHERE evidence.candidate_id=candidate.candidate_id
            ORDER BY evidence.created_at DESC,evidence.evidence_id DESC LIMIT 1
        ) local_evidence ON true
        WHERE candidate.source_id=%s AND candidate.snapshot_sha256=%s""", (source, snapshot)).fetchall()
    if len(candidate_rows) != len(handoff["representatives"]):
        raise BridgeError("preview_candidate_count_mismatch")
    by_group = {str(row[1]): row for row in candidate_rows}
    if set(by_group) != set(handoff["representatives"]):
        raise BridgeError("preview_group_set_mismatch")
    taxonomy_by_identifier = {}
    for parsed, raw in handoff["rows"]:
        identifier = str(parsed[0])
        normalized = raw.get("normalized") if isinstance(raw.get("normalized"), dict) else {}
        source_values = raw.get("source_values") if isinstance(raw.get("source_values"), dict) else {}
        taxonomy_by_identifier[identifier] = IMPORTER.activity_contract(normalized, source, source_values)
    taxonomy_documents = {}
    for contract in taxonomy_by_identifier.values():
        document = contract.get("crosswalk_document")
        if isinstance(document, dict):
            taxonomy_documents[str(document["crosswalk_version"])] = document
    for version, document in taxonomy_documents.items():
        retained_crosswalk = connection.execute("""SELECT taxonomy_version,ruleset_version,definition_sha256
            FROM real_preview.taxonomy_crosswalks WHERE source_id=%s AND crosswalk_version=%s""",
            (source, version)).fetchone()
        if (retained_crosswalk is None or retained_crosswalk[0] != document["taxonomy_version"]
                or retained_crosswalk[1] != document["ruleset_version"]
                or str(retained_crosswalk[2]).strip() != crosswalk_sha256(document)):
            raise BridgeError("preview_taxonomy_crosswalk_mismatch")
    rep_by_id = {}
    for group, (parsed, raw) in handoff["representatives"].items():
        identifier = str(parsed[0])
        db_candidate = by_group[group]
        # Exact source identifier matching is validated by a lookup against the
        # immutable private preview row before any canonical record is staged.
        candidate_rep = connection.execute("SELECT source_identifier FROM real_preview.observations WHERE preview_id=%s",
                                           (db_candidate[2],)).fetchone()
        if candidate_rep is None or str(candidate_rep[0]) != identifier:
            raise BridgeError("preview_representative_mismatch")
        if int(db_candidate[10]) != len(handoff["groups"][group]):
            raise BridgeError("preview_group_observation_count_mismatch")
        if db_candidate[3:10] != (parsed[1], parsed[2], parsed[3], parsed[4], parsed[5], parsed[6], parsed[7]):
            raise BridgeError("preview_candidate_projection_mismatch")
        group_contracts = [taxonomy_by_identifier[str(row.get("source_record_key", row.get("source_row_id")))]
                           for _, row in handoff["groups"][group]]
        merged = IMPORTER.merge_activity_contracts(group_contracts, source)
        if (db_candidate[18] != merged["category"]
                or list(db_candidate[19] or []) != merged["activity_categories"]
                or list(db_candidate[20] or []) != merged["source_activity_codes"]
                or list(db_candidate[21] or []) != merged["source_activity_labels"]
                or db_candidate[22] != merged["activity_mapping_status"]
                or db_candidate[23] != merged["classification_ruleset_version"]):
            raise BridgeError("preview_candidate_taxonomy_mismatch")
        rep_by_id[group] = identifier
    for parsed, raw in handoff["rows"]:
        identifier = str(parsed[0])
        observed = preview_observations.get(identifier)
        if observed is None:
            raise BridgeError("preview_identifier_missing")
        (location_class, country, city, postal, latitude, longitude, precision,
         source_observed_at, is_candidate) = observed
        expected_tuple = (parsed[1], parsed[2], parsed[3], parsed[4], parsed[5], parsed[6], parsed[7], parsed[8])
        actual_tuple = (location_class, country, city, postal, latitude, longitude, precision, source_observed_at)
        if actual_tuple != expected_tuple:
            raise BridgeError("preview_observation_projection_mismatch")
        group = str(parsed[IMPORTER.SOURCE_GROUP_KEY_INDEX])
        if bool(is_candidate) != (rep_by_id.get(group) == identifier):
            raise BridgeError("preview_representative_flag_mismatch")
    return {"run": run, "manifest": manifest, "observations": preview_observations,
            "preview_ids": preview_id_by_identifier,
            "candidates": by_group, "representatives": rep_by_id,
            "taxonomy": taxonomy_by_identifier}


def _uuid(namespace: str, *parts: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, ":".join(("uec-v0", namespace, *parts))))


def _safe_normalized(normalized: Any) -> dict[str, Any]:
    if not isinstance(normalized, dict):
        return {}
    return {key: value for key, value in normalized.items()
            if key in _NORMALIZED_KEYS and key.casefold() not in _FORBIDDEN_KEYS}


def _coordinate(normalized: dict[str, Any], preview_candidate: tuple[Any, ...], *, allow_display: bool) -> tuple[float | None, float | None, str | None, str | None, str | None, str | None]:
    coords = normalized.get("coordinates") if isinstance(normalized.get("coordinates"), dict) else {}
    lat, lon = coords.get("latitude"), coords.get("longitude")
    precision = coords.get("precision") or normalized.get("coordinate_precision") or normalized.get("geography_precision")
    method = coords.get("method") or normalized.get("coordinate_method")
    provider = coords.get("provider") or normalized.get("coordinate_provider")
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        lat = lon = None
    if lat is not None and (not (-90 <= lat <= 90 and -180 <= lon <= 180) or (lat == 0 and lon == 0)):
        lat = lon = None
    origin = "source_coordinates" if lat is not None else None
    if lat is None and allow_display and preview_candidate[11] is not None:
        lat, lon = preview_candidate[11], preview_candidate[12]
        if preview_candidate[27] is not None and preview_candidate[29] == "accepted" and preview_candidate[24] is not None:
            method = "geoapify_forward"
            provider = preview_candidate[28]
            precision = preview_candidate[24]
            origin = "provider_derived"
        elif preview_candidate[32] is not None and preview_candidate[25] is not None:
            method = "coarse_reference"
            precision = preview_candidate[25]
            provider = str(preview_candidate[26] or "verified_local_reference")
            origin = "verified_coarse_reference"
        else:
            lat = lon = None
    if lat is None:
        return None, None, None, None, None, None
    method = str(method or "source_method_unknown")[:80]
    provider = str(provider)[:160] if provider else None
    precision = str(precision or "source_precision_unknown")[:80]
    return lat, lon, method, precision, provider, origin


def _insert_source(connection: Any, source: str, country: str, name: str, url: str) -> None:
    if len(country) != 2:
        raise BridgeError("source_country_missing")
    prior = connection.execute("SELECT country_code FROM uec.sources WHERE source_id=%s", (source,)).fetchone()
    if prior and str(prior[0]).strip().upper() != country:
        raise BridgeError("existing_source_identity_conflict")
    connection.execute("""INSERT INTO uec.sources(source_id,country_code,name,official_url,access_method,status,origin_type)
        VALUES (%s,%s,%s,%s,'source_handoff_private_candidate','source_candidate','official') ON CONFLICT (source_id) DO NOTHING""",
        (source, country, name, url))


def _ensure_artifact(connection: Any, entry: dict[str, Any], retrieved: datetime) -> str:
    if entry["source_bytes_state"] == "retained":
        storage_key = str(Path(entry["source_artifact_path"]).resolve(strict=True))
        byte_size = int(entry["source_artifact_byte_size"])
        state = "retained"
    else:
        storage_key = None
        byte_size = None
        state = "not_retained"
    connection.execute("""INSERT INTO uec.raw_artifacts
        (storage_key,sha256,byte_size,media_type,retrieved_at,retention_status)
        VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (sha256) DO NOTHING""",
        (storage_key, entry["source_artifact_sha256"], byte_size, entry.get("media_type"), retrieved, state))
    row = connection.execute("SELECT artifact_id::text,storage_key,byte_size,retention_status FROM uec.raw_artifacts WHERE sha256=%s",
                             (entry["source_artifact_sha256"],)).fetchone()
    if row is None:
        raise BridgeError("artifact_insert_failed")
    if state == "retained" and (row[1] is None or row[2] is None or int(row[2]) != byte_size or row[3] != "retained"):
        raise BridgeError("existing_artifact_provenance_conflict")
    if state == "not_retained" and row[3] not in {"retained", "not_retained"}:
        raise BridgeError("existing_artifact_provenance_conflict")
    if state == "not_retained" and row[3] == "not_retained" and (row[1] is not None or row[2] is not None):
        raise BridgeError("existing_artifact_provenance_conflict")
    return str(row[0])


def _release_existing(connection: Any, release_id: str, freeze_hash: str) -> bool:
    row = connection.execute("SELECT status,profile,test_only,ruleset_version,summary FROM uec.releases WHERE release_id=%s",
                             (release_id,)).fetchone()
    if row is None:
        return False
    summary = row[4] if isinstance(row[4], dict) else {}
    if (row[0] != "candidate" or row[1] != PROFILE or row[2] is not False
            or summary.get("candidate_only") is not True
            or summary.get("freeze_sha256") != freeze_hash):
        raise BridgeError("release_id_conflicts_with_existing_release")
    return True


def _public_projection_count(connection: Any) -> int:
    """Count only actual public map/graph projections, not candidate membership."""
    total = 0
    for relation in PUBLIC_PROJECTION_RELATIONS:
        if connection.execute("SELECT to_regclass(%s)", (relation,)).fetchone()[0] is None:
            continue
        total += int(connection.execute(f"SELECT count(*) FROM {relation}").fetchone()[0])
    return total


def bridge(database_url: str, expected_database: str, freeze: dict[str, Any], inventory: dict[str, Any],
            *, candidate_only_ack: bool) -> dict[str, Any]:
    parsed_url = urlsplit(database_url)
    if parsed_url.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise BridgeError("database_must_be_loopback")
    if not candidate_only_ack:
        raise BridgeError("explicit_candidate_only_ack_required")
    if not re.fullmatch(r"uec_v0_review(?:_[a-z0-9]+)?", expected_database):
        raise BridgeError("expected_database_name_must_be_isolated_v0_review")
    if parsed_url.path.lstrip("/") != expected_database:
        raise BridgeError("database_name_does_not_match_expected")
    entries = {item["source_id"]: item for item in freeze["selected_sources"]}
    inventory_sources = {item["source_id"]: item for item in inventory["source_scope"]["sources"]}
    handoffs = {source: verify_handoff(entry, inventory_sources[source]) for source, entry in entries.items()}
    freeze_hash = hashlib.sha256((json.dumps(freeze, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()).hexdigest()
    summary = {"candidate_only": True, "freeze_sha256": freeze_hash,
               "inventory_sha256": freeze["inventory_sha256"], "selected_sources": sorted(entries),
               "excluded_sources": [{"source_id": item["source_id"], "reason_code": item["reason_code"]}
                                    for item in freeze["excluded_sources"]],
               "source_provenance": [{
                   "source_id": source,
                   "snapshot_sha256": entries[source]["snapshot_sha256"],
                   "source_artifact_sha256": entries[source]["source_artifact_sha256"],
                   "source_bytes_state": entries[source]["source_bytes_state"],
                   "source_artifact_byte_size": entries[source].get("source_artifact_byte_size"),
                   "source_url": handoffs[source]["source_url"],
                   "source_host": handoffs[source]["source_host"],
                   "handoff_manifest_path": str(handoffs[source]["manifest_path"]),
                   "normalized_sha256": handoffs[source]["normalized_sha256"],
                   "handoff_manifest_sha256": _digest(handoffs[source]["manifest_path"])[0],
                   "graph_manifest_sha256": _digest(handoffs[source]["graph_manifest_path"])[0],
                   "graph_records_sha256": handoffs[source]["graph_records_sha256"],
                   "terms_review_sha256": handoffs[source]["terms_review_sha256"],
                   "retrieved_at": handoffs[source]["manifest"].get("retrieved_at_utc"),
                   "handoff_code_version": handoffs[source]["manifest"].get("code_version"),
                   "handoff_config_version": handoffs[source]["manifest"].get("config_version"),
                   "source_observations": len(handoffs[source]["rows"]),
                   "facility_candidates": len(handoffs[source]["representatives"]),
               } for source in sorted(entries)],
               "public_authorized": False, "review_approval_created": False,
               "graph_claims_imported": False, "graph_projection_verified": False,
               "graph_readiness": "not_imported",
               "source_observation_count": sum(len(item["rows"]) for item in handoffs.values()),
               "facility_candidate_count": sum(len(item["representatives"]) for item in handoffs.values())}
    counts = {"sources": len(entries), "source_observations": 0, "facility_candidates": 0,
              "source_coordinates": 0, "provider_derived_coordinates": 0, "coarse_references": 0,
              "unmapped": 0, "release_members": 0}
    try:
        with psycopg.connect(database_url) as connection, connection.transaction():
            connection.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
            connection.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("v0-candidate-bridge:" + freeze["release_id"],))
            db_name = connection.execute("SELECT current_database()").fetchone()[0]
            if db_name != expected_database:
                raise BridgeError("connected_database_mismatch")
            connection.execute("SELECT retention_status FROM uec.raw_artifacts LIMIT 0")
            public_projection_before = _public_projection_count(connection)
            if (public_projection_before != 0
                    or connection.execute("SELECT count(*) FROM uec.releases WHERE status IN ('validated','promoted')").fetchone()[0] != 0
                    or connection.execute("SELECT count(*) FROM uec.release_manifests").fetchone()[0] != 0):
                raise BridgeError("candidate_database_has_public_release_state")
            # The exact freeze key is immutable: same key is a safe no-op; a
            # reused release ID with a different selection stops before writes.
            existing = _release_existing(connection, freeze["release_id"], freeze_hash)
            if not existing:
                if connection.execute("SELECT count(*) FROM uec.release_members").fetchone()[0] != 0:
                    raise BridgeError("candidate_database_membership_not_empty")
                if connection.execute("SELECT count(*) FROM uec.releases").fetchone()[0] != 0:
                    raise BridgeError("candidate_database_releases_not_empty")
                connection.execute("""INSERT INTO uec.releases(release_id,status,ruleset_version,summary,profile,test_only)
                    VALUES (%s,'candidate',%s,%s,%s,false)""",
                    (freeze["release_id"], "v0-candidate-freeze-v1", Jsonb(summary), PROFILE))
            for source, entry in entries.items():
                handoff = handoffs[source]
                preview_check = _verify_preview_source(connection, source, entry, handoff)
                run, manifest = preview_check["run"], preview_check["manifest"]
                retrieved = _utc(str(handoff["manifest"].get("retrieved_at_utc") or handoff["manifest"].get("retrieved_at")), "retrieved_at")
                source_url = str(handoff["manifest"].get("source_url"))
                parsed_url = urlsplit(source_url)
                if parsed_url.scheme not in {"https", "http"} or not parsed_url.hostname or parsed_url.username or parsed_url.password:
                    raise BridgeError("source_url_invalid")
                # Country code is source-owned in normalized data and must be
                # internally consistent; do not infer it from source IDs.
                country_values = {str(parsed[2]).upper() for parsed, _ in handoff["rows"] if parsed[2]}
                if len(country_values) != 1:
                    raise BridgeError("source_country_inconsistent")
                country = next(iter(country_values))
                source_name = IMPORTER.SOURCE_NAMES.get(source, source)
                _insert_source(connection, source, country, source_name, source_url)
                artifact_id = _ensure_artifact(connection, entry, retrieved)
                candidate_rows = preview_check["candidates"]
                # Source-native group identity remains stable across snapshots;
                # no name/address-based cross-source matching is attempted.
                for parsed, raw in handoff["rows"]:
                    identifier = str(parsed[0])
                    group = str(parsed[IMPORTER.SOURCE_GROUP_KEY_INDEX])
                    parsed_at = retrieved
                    source_record_key = f"v0:{entry['snapshot_sha256']}:{identifier}"
                    normalized = raw.get("normalized") if isinstance(raw.get("normalized"), dict) else {}
                    contract = preview_check["taxonomy"][identifier]
                    raw_fields = {"evidence_kind": "authenticated_normalized_handoff",
                                  "snapshot_sha256": entry["snapshot_sha256"],
                                  "source_identifier": identifier,
                                  "normalized": _safe_normalized(normalized),
                                  "source_activity_codes": contract.get("source_activity_codes", []),
                                  "source_activity_labels": contract.get("source_activity_labels", []),
                                  "handoff_normalized_sha256": handoff["normalized_sha256"]}
                    record_row = connection.execute("""INSERT INTO uec.source_records
                        (source_id,source_record_key,artifact_id,raw_fields,parsed_at)
                        VALUES (%s,%s,%s,%s,%s) ON CONFLICT (source_id,source_record_key,artifact_id) DO NOTHING
                        RETURNING source_record_id::text""",
                        (source, source_record_key, artifact_id, Jsonb(raw_fields), parsed_at)).fetchone()
                    stored_record = connection.execute("SELECT source_record_id::text,raw_fields FROM uec.source_records WHERE source_id=%s AND source_record_key=%s AND artifact_id=%s",
                                                       (source, source_record_key, artifact_id)).fetchone()
                    if stored_record is None or stored_record[1] != raw_fields:
                        raise BridgeError("source_record_idempotency_conflict")
                    source_record_id = stored_record[0]
                    facility_id = _uuid("facility", source, group)
                    representative_parsed, _ = handoff["representatives"][group]
                    country = str(representative_parsed[2] or country).upper()
                    existing_facility = connection.execute("SELECT country_code FROM uec.facilities WHERE facility_id=%s", (facility_id,)).fetchone()
                    if existing_facility and str(existing_facility[0]).strip().upper() != country:
                        raise BridgeError("canonical_facility_identity_conflict")
                    linked_sources = connection.execute("""SELECT DISTINCT source_record.source_id
                        FROM uec.facility_source_links link JOIN uec.source_records source_record USING (source_record_id)
                        WHERE link.facility_id=%s""", (facility_id,)).fetchall()
                    if any(row[0] != source for row in linked_sources):
                        raise BridgeError("canonical_facility_source_identity_conflict")
                    connection.execute("""INSERT INTO uec.facilities(facility_id,country_code,city,postal_code)
                        VALUES (%s,%s,%s,%s) ON CONFLICT (facility_id) DO NOTHING""",
                        (facility_id, country, representative_parsed[3], representative_parsed[4]))
                    connection.execute("""INSERT INTO uec.facility_source_links(facility_id,source_record_id,match_method,review_status)
                        VALUES (%s,%s,'source_native_group_key','automatic') ON CONFLICT DO NOTHING""",
                        (facility_id, source_record_id))
                    candidate = candidate_rows[group]
                    source_observed = parsed[8]
                    observed_at = source_observed or retrieved
                    observed_basis = "source_asserted_at" if source_observed else "project_retrieved_at"
                    is_representative = preview_check["representatives"].get(group) == identifier
                    latitude, longitude, coord_method, coord_precision, coord_provider, point_origin = _coordinate(
                        normalized, candidate, allow_display=is_representative)
                    if latitude is None and parsed[5] is not None and parsed[6] is not None:
                        latitude, longitude = parsed[5], parsed[6]
                        coord_method = str(parsed[19] or "source_method_unknown")
                        coord_precision = str(parsed[7] or "source_precision_unknown")
                        coord_provider = parsed[20]
                        point_origin = "source_coordinates"
                    coord_geom = ("ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography" if latitude is not None else "NULL")
                    if is_representative and candidate[11] is not None:
                        if candidate[27] is not None and candidate[29] == "accepted":
                            display_location = {"latitude": candidate[11], "longitude": candidate[12],
                                "method": "geoapify_forward", "precision": candidate[24],
                                "provider": candidate[28], "evidence_kind": "provider_derived",
                                "evidence_id": candidate[27], "provider_status": candidate[29],
                                "provider_queried_at": candidate[30].isoformat() if candidate[30] else None,
                                "coordinate_review_status": candidate[31],
                                "confidence": candidate[16], "confidence_band": candidate[17]}
                        elif candidate[32] is not None:
                            display_location = {"latitude": candidate[11], "longitude": candidate[12],
                                "method": "coarse_reference", "precision": candidate[25],
                                "provider": candidate[26], "evidence_kind": "verified_coarse_reference",
                                "evidence_id": candidate[32], "reference_source_id": candidate[33],
                                "source": candidate[13]}
                        else:
                            display_location = {"latitude": candidate[11], "longitude": candidate[12],
                                "method": parsed[19] or "source_coordinates",
                                "precision": parsed[7] or "source_precision_unknown",
                                "provider": parsed[20], "evidence_kind": "source_coordinates",
                                "source": candidate[13]}
                    else:
                        display_location = None
                    observation_data = {
                        "source_id": source, "source_identifier": identifier,
                        "source_artifact_sha256": entry["source_artifact_sha256"],
                        "source_url": source_url, "source_retrieved_at": retrieved.isoformat(),
                        "source_observed_at": source_observed.isoformat() if source_observed else None,
                        "observed_at_basis": observed_basis,
                        "handoff_normalized_sha256": handoff["normalized_sha256"],
                        "handoff_manifest_sha256": _digest(handoff["manifest_path"])[0],
                        "graph_manifest_sha256": _digest(handoff["graph_manifest_path"])[0],
                        "graph_records_sha256": handoff["graph_records_sha256"],
                        "location_class": parsed[1], "source_location": {
                            "latitude": parsed[5], "longitude": parsed[6], "precision": parsed[7],
                            "coordinate_method": parsed[19], "coordinate_provider": parsed[20],
                        } if parsed[5] is not None else None,
                        "display_location": display_location,
                        "private_location_evidence": ({key: value for key, value in normalized["private_location_evidence"].items()
                            if key in _PRIVATE_LOCATION_KEYS} if isinstance(normalized.get("private_location_evidence"), dict) else None),
                        "source_preview_observation_id": preview_check["preview_ids"].get(identifier),
                        "source_preview_candidate_id": candidate[0],
                        "source_group_key": group,
                        "activity": {key: contract.get(key) for key in (
                            "category", "activity_categories", "source_activity_codes", "source_activity_labels",
                            "activity_mapping_status", "classification_ruleset_version", "taxonomy_mapping_method")},
                        "source_status": _safe_normalized(normalized),
                        "review_state": "review_required", "publication_state": "not_eligible",
                    }
                    category = contract.get("category") or "unclassified"
                    classification_data = {
                        "source_id": source, "source_category": category,
                        "taxonomy_version": "uec-taxonomy-v1",
                        "crosswalk_version": contract.get("crosswalk_document", {}).get("crosswalk_version") if contract.get("crosswalk_document") else None,
                        "ruleset_version": contract.get("classification_ruleset_version"),
                        "mapping_status": contract.get("activity_mapping_status"),
                        "mapping_method": contract.get("taxonomy_mapping_method"),
                        "source_activity_codes": contract.get("source_activity_codes", []),
                        "source_activity_labels": contract.get("source_activity_labels", []),
                    }
                    observation_params = (facility_id, source_record_id, observed_at, Jsonb(observation_data),
                        Jsonb(classification_data), contract.get("classification_ruleset_version") or "v0-unmapped",
                        "source-handoff-candidate", category, parsed[17])
                    if latitude is not None:
                        observation_params += (latitude, longitude)
                    observation_params += (coord_method, coord_precision, observed_at)
                    observation_row = connection.execute(f"""INSERT INTO uec.observations
                        (facility_id,source_record_id,observed_at,observation,classification,ruleset_id,rule_id,
                         classification_category,classification_review_status,default_visible,optional_filter,
                         coordinate,coordinate_method,coordinate_precision,coordinate_review_status,first_observed_at)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'review_required',false,%s,{coord_geom},%s,%s,'review_required',%s)
                        ON CONFLICT (facility_id,source_record_id,observed_at) DO NOTHING RETURNING observation_id::text""",
                        observation_params).fetchone()
                    stored_observation = connection.execute("""SELECT observation_id::text,observation,classification,
                            classification_category,classification_review_status,default_visible,optional_filter,
                            coordinate_method,coordinate_precision,coordinate_review_status,
                            CASE WHEN coordinate IS NULL THEN NULL ELSE ST_Y(coordinate::geometry) END,
                            CASE WHEN coordinate IS NULL THEN NULL ELSE ST_X(coordinate::geometry) END
                        FROM uec.observations WHERE facility_id=%s AND source_record_id=%s AND observed_at=%s""",
                        (facility_id, source_record_id, observed_at)).fetchone()
                    expected_optional = parsed[17]
                    actual_tuple = (stored_observation[1], stored_observation[2], stored_observation[3],
                        stored_observation[4], stored_observation[5], stored_observation[6],
                        stored_observation[7], stored_observation[8], stored_observation[9],
                        stored_observation[10], stored_observation[11]) if stored_observation else None
                    expected_tuple = (observation_data, classification_data, category, "review_required", False,
                        expected_optional, coord_method, coord_precision, "review_required", latitude, longitude)
                    if stored_observation is None or actual_tuple != expected_tuple:
                        raise BridgeError("observation_idempotency_conflict")
                    observation_id = stored_observation[0]
                    if contract.get("crosswalk_document"):
                        from pipeline.taxonomy.persistence import persist_uec_assignment_set
                        persist_uec_assignment_set(connection, observation_id=observation_id,
                            source_record_id=source_record_id, artifact_id=artifact_id,
                            document=contract["crosswalk_document"], assignment_rows=contract["taxonomy_assignment_rows"])
                    counts["source_observations"] += 1
                    if point_origin == "provider_derived":
                        counts["provider_derived_coordinates"] += 1
                    elif point_origin == "verified_coarse_reference":
                        counts["coarse_references"] += 1
                    elif point_origin == "source_coordinates":
                        counts["source_coordinates"] += 1
                    else:
                        counts["unmapped"] += 1
                for group, (rep, raw) in handoff["representatives"].items():
                    if source != str(rep and raw.get("source_id") or source):
                        raise BridgeError("representative_source_mismatch")
                    identifier = str(rep[0])
                    source_record_key = f"v0:{entry['snapshot_sha256']}:{identifier}"
                    record_row = connection.execute("SELECT source_record_id,artifact_id FROM uec.source_records WHERE source_id=%s AND source_record_key=%s",
                                                    (source, source_record_key)).fetchone()
                    if record_row is None:
                        raise BridgeError("release_representative_missing")
                    group_id = _uuid("facility", source, group)
                    obs = connection.execute("SELECT observation_id FROM uec.observations WHERE facility_id=%s AND source_record_id=%s ORDER BY observed_at DESC LIMIT 1",
                                             (group_id, record_row[0])).fetchone()
                    if obs is None:
                        raise BridgeError("release_representative_observation_missing")
                    connection.execute("""INSERT INTO uec.release_members(release_id,facility_id,observation_id,default_visible)
                        VALUES (%s,%s,%s,false) ON CONFLICT (release_id,facility_id) DO NOTHING""",
                        (freeze["release_id"], group_id, obs[0]))
                    member = connection.execute("SELECT observation_id,default_visible FROM uec.release_members WHERE release_id=%s AND facility_id=%s",
                                                (freeze["release_id"], group_id)).fetchone()
                    if member is None or str(member[0]) != str(obs[0]) or member[1] is not False:
                        raise BridgeError("release_member_conflict")
                    counts["release_members"] += 1
            counts["facility_candidates"] = counts["release_members"]
            if counts["source_observations"] != summary["source_observation_count"] or counts["facility_candidates"] != summary["facility_candidate_count"]:
                raise BridgeError("bridge_total_reconciliation_failed")
            actual_members, visible_members = connection.execute(
                "SELECT count(*),count(*) FILTER (WHERE default_visible) FROM uec.release_members WHERE release_id=%s",
                (freeze["release_id"],)).fetchone()
            if int(actual_members) != counts["facility_candidates"] or int(visible_members) != 0:
                raise BridgeError("release_membership_count_or_visibility_mismatch")
            if connection.execute("SELECT count(*) FROM uec.release_members WHERE release_id<>%s",
                                  (freeze["release_id"],)).fetchone()[0] != 0:
                raise BridgeError("candidate_database_has_unrelated_release_members")
            if _public_projection_count(connection) != 0:
                raise BridgeError("public_projection_state_changed")
            release_state = connection.execute("SELECT status,profile,test_only FROM uec.releases WHERE release_id=%s",
                                               (freeze["release_id"],)).fetchone()
            if release_state != ("candidate", PROFILE, False):
                raise BridgeError("candidate_release_state_mismatch")
            if connection.execute("SELECT count(*) FROM uec.release_manifests WHERE release_id=%s",
                                  (freeze["release_id"],)).fetchone()[0] != 0:
                raise BridgeError("candidate_release_manifest_exists")
    except psycopg.Error as error:
        # Database diagnostics may contain private URLs or server details.
        failure = BridgeError("candidate_bridge_database_operation_failed")
        # Keep only payload-free diagnostics on the in-process exception for
        # disposable integration tests; CLI output remains the generic code.
        failure.database_error_class = type(error).__name__
        failure.database_sqlstate = getattr(error, "sqlstate", None)
        raise failure from None
    return {"status": "candidate_only_staged", "release_id": freeze["release_id"],
            "freeze_sha256": freeze_hash, "counts": counts, "public_authorized": False,
            "graph_claims_imported": False, "graph_projection_verified": False,
            "graph_readiness": "not_imported",
            "review_events_created": 0, "rights_decisions_created": 0,
            "public_projection_rows_created": 0}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.environ.get("UEC_DATABASE_URL"))
    parser.add_argument("--expected-database", required=True)
    parser.add_argument("--freeze", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--candidate-only-ack", action="store_true")
    args = parser.parse_args(argv)
    if not args.database_url:
        parser.error("--database-url or UEC_DATABASE_URL is required")
    try:
        freeze, inventory = load_freeze(args.freeze, args.inventory)
        report = bridge(args.database_url, args.expected_database, freeze, inventory,
                        candidate_only_ack=args.candidate_only_ack)
    except (BridgeError, OSError, ValueError):
        print(json.dumps({"status": "blocked", "reason": "candidate_bridge_validation_failed"}, sort_keys=True))
        return 2
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
