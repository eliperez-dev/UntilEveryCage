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
import sys
import uuid
from collections import defaultdict
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlsplit

import psycopg
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from pipeline.taxonomy.contract import choose_display_category, crosswalk_sha256
from pipeline.taxonomy.persistence import _canonical_rows

IMPORTER_PATH = ROOT / "pipeline" / "scripts" / "maintenance" / "import-real-preview.py"
SPEC = importlib.util.spec_from_file_location("uec_real_preview_importer", IMPORTER_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("private preview parser unavailable")
IMPORTER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(IMPORTER)

SCHEMA = "v0-candidate-freeze-v1"
PROFILE = "official"
CORRECTION_PROJECTION_VERSION = "v0-correction-v4"
CORRECTION_SCOPE_PROJECTION_VERSION = "v0-correction-v6"
PUBLIC_PROJECTION_RELATIONS = (
    "uec.map_facilities_public_discovery",
    "uec.map_facilities_public_discovery_read_model",
    "uec.graph_public_relationships",
    "uec.graph_public_claims",
)
RELEASE_BASELINE_ID = "release-2026-10-18"
RELEASE_BASELINE_MANIFEST_SHA256 = "f06aa554f2b49aa8e4a285df948b8baa47952f60bfb344251109b9788cc2a661"
RELEASE_BASELINE_PUBLIC_ROWS = 69220
RELEASE_REPLACEMENT_SOURCES = frozenset({
    "de.locations", "es.locations", "fr.georisques.icpe.animal", "mx.locations",
    "nz.locations", "fsa_approved_establishments", "fss_approved_establishments",
})
RETAINED_RELEASE_IDS = (
    "v0-candidate-2026-10-10-fsis-au-repair",
    "v0-candidate-2026-10-10-fsis-au-repair-r2",
    "v0-candidate-2026-10-10-fsis-au-repair-r3",
    "v0-candidate-2026-10-10-fsis-au-repair-r4",
    "v0-candidate-2026-10-10-fsis-au-repair-r5",
)
RETAINED_MANIFEST_SHA256 = {"v0-candidate-2026-10-10-fsis-au-repair-r2":
    "b47b411a27542da4a538a2773dd383b0a1003ed188b7e8304f0898c39c592926"}
GRAPH_IMMUTABLE_RELATIONS = (
    "uec.graph_public_projection_builds", "uec.graph_public_projection_endpoints",
    "uec.graph_public_projection_edges", "uec.graph_public_projection_edge_supports",
    "uec.graph_public_projection_anchors", "uec.graph_public_projection_evidence_refs",
    "uec.graph_public_projection_org_labels", "uec.graph_projection_generation",
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
    "alternate_names", "dba_names", "grant_date", "activity_volume_codes",
    "primary_anzsic_class_code", "primary_anzsic_class_name", "main_activities",
    "native_code", "native_label", "sector", "sector_code",
    "private_geocode_scope", "private_geocode_scope_policy_id", "source_address_eligible",
    "source_address_restricted", "evidence_summary", "city",
    "clee", "activity_class_id", "activity_name", "activity_size_stratum",
    "source_start_date", "source_administrative_location",
    "mpi_risk_measure_id", "source_entity_type", "business_identifier",
    "business_identifier_type", "risk_measure_type", "programme_type",
    "product_material", "primary_activity", "secondary_activity", "intended_use",
    "market", "is_suspended", "effective_date", "expiry_date", "suspension_type",
    "suspension_start_date", "suspension_end_date", "suspended_operations",
    "verification_agency", "location_role", "operator_local_authority",
    "location_local_authority", "location_count", "location_count_state",
    "dairy_ulis", "fishing_vessel_name",
}
_PRIVATE_LOCATION_KEYS = {"address", "address_lines", "city", "postal_code", "region", "country_code",
                          "coordinates", "municipality_code", "comarca_code", "department_number", "region_code"}

# Explicit normalized business/facility labels only. In particular, never fall
# back to operator_name or generic name for sources whose adapters conflate
# facilities and people. Keep this projection separate from raw_fields so
# replay equality and the retained evidence schema remain unchanged.
_FACILITY_NAME_FIELDS = {
    "au.npi.facilities": ("facility_name", "trading_name", "name", "registered_business_name"),
    "dk.smiley": ("trading_name",),
    "ca.ontario.meat-plants": ("trading_name",),
    "fsa_approved_establishments": ("trading_name",),
    "nl.nvwa.approved-food": ("trading_name",),
    "fr.dgal.section-i": ("trading_name", "name"),
    "fr.dgal.section-ii": ("trading_name", "name"),
    "it.853-2004": ("trading_name", "name"),
    "it.1069-2009": ("trading_name", "name"),
    "us.fsis": ("canonical_name",),
    "us.aphis": ("canonical_name",),
    "fss_approved_establishments": ("trading_name",),
    "de.locations": ("name", "trading_name"),
    "es.locations": ("name",),
    "fr.georisques.icpe.animal": ("trading_name", "name"),
    "mx.locations": ("name",),
    "nz.locations": ("trading_name", "name"),
}


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


def _retained_source_artifact_digest(source: str, path: Path) -> tuple[str, int]:
    """Digest retained source bytes, including France's verified page-set contract."""
    path = Path(path)
    if path.is_symlink():
        raise BridgeError("retained_artifact_locator_invalid")
    if path.is_dir():
        if source != "fr.georisques.icpe.animal":
            raise BridgeError("retained_artifact_locator_invalid")
        try:
            page_files = sorted(path.glob("page-*.json"))
            snapshot_manifest = path.parent / "snapshot-manifest.json"
            if (not page_files or any(child.is_symlink() for child in path.iterdir())
                    or snapshot_manifest.is_symlink() or not snapshot_manifest.is_file()
                    or [item.name for item in page_files] !=
                    [f"page-{index:05d}.json" for index in range(1, len(page_files) + 1)]):
                raise BridgeError("retained_artifact_locator_invalid")
            from pipeline.sources.france.georisques_icpe.adapter import GeorisquesIcpeAnimalAdapter
            result = GeorisquesIcpeAnimalAdapter().parse_pages(path)
        except BridgeError:
            raise
        except Exception:
            raise BridgeError("retained_artifact_verification_failed") from None
        return str(result["sha256"]), int(result["byte_size"])
    if not path.is_file():
        raise BridgeError("retained_artifact_locator_invalid")
    return _digest(path)


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


def _validate_preview_timeline(handoff_value: Any, manifest_value: Any, run_value: Any,
                               inventory_source: dict[str, Any], entry: dict[str, Any]) -> tuple[datetime, datetime]:
    snapshot = inventory_source.get("snapshot", {})
    latest = _utc(snapshot.get("retrieved_at"), "latest_retrieved_at")
    first = _utc(snapshot.get("first_manifest_retrieved_at") or snapshot.get("retrieved_at"),
                 "first_manifest_retrieved_at")
    handoff = _utc(handoff_value, "handoff_retrieved_at")
    manifest = _utc(manifest_value, "first_manifest_retrieved_at")
    run = _utc(run_value, "latest_retrieved_at")
    now = datetime.now(timezone.utc)
    if (handoff not in (first, latest) or manifest != first or run != latest
            or first > latest or latest > now or manifest > run or handoff > now):
        raise BridgeError("preview_run_retrieval_timeline_mismatch")
    if (entry.get("latest_retrieved_at") is not None
            and _utc(entry["latest_retrieved_at"], "latest_retrieved_at") != latest):
        raise BridgeError("freeze_latest_acquisition_time_mismatch")
    return handoff, run


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
        if (item.get("latest_retrieved_at") is not None
                and _utc(item["latest_retrieved_at"], "latest_retrieved_at").isoformat()
                != _utc(snapshot.get("retrieved_at"), "latest_retrieved_at").isoformat()):
            raise BridgeError("freeze_latest_acquisition_time_mismatch")
        if item.get("source_bytes_state") not in {"retained", "not_retained"}:
            raise BridgeError("freeze_artifact_retention_state_invalid")
        if item.get("source_bytes_state") == "retained":
            locator = item.get("source_artifact_path")
            if not isinstance(locator, str) or not Path(locator).is_absolute():
                raise BridgeError("retained_artifact_locator_missing")
            if Path(locator).is_symlink():
                raise BridgeError("retained_artifact_locator_invalid")
            digest, size = _retained_source_artifact_digest(item["source_id"], Path(locator))
            if digest != item.get("source_artifact_sha256") or item.get("source_artifact_byte_size") != size:
                raise BridgeError("retained_artifact_verification_failed")
        elif item.get("source_artifact_path") is not None or item.get("source_artifact_byte_size") is not None:
            raise BridgeError("not_retained_artifact_metadata_must_be_null")
    return freeze, inventory


def verify_handoff(entry: dict[str, Any], inventory_source: dict[str, Any]) -> dict[str, Any]:
    source = str(entry["source_id"])
    manifest_path, normalized_path, graph_manifest_path, graph_records_path = _source_paths(entry)
    manifest = _read_json(manifest_path)
    nz_graph_not_applicable = source == "nz.locations"
    if nz_graph_not_applicable:
        if (graph_manifest_path.exists() or graph_manifest_path.is_symlink()
                or graph_records_path.exists() or graph_records_path.is_symlink()):
            raise BridgeError("nz_graph_artifacts_not_applicable")
        graph_manifest = None
    else:
        if (graph_manifest_path.is_symlink() or not graph_manifest_path.is_file()
                or graph_records_path.is_symlink() or not graph_records_path.is_file()):
            raise BridgeError("handoff_file_unavailable")
        graph_manifest = _read_json(graph_manifest_path)
    if (manifest.get("source_id") != source
            or manifest.get("contract_version") != "candidate-handoff-v1"
            or manifest.get("publication_state") != "private-candidate"
            or manifest.get("release_state") != "not-created"
            or manifest.get("review_state") != "review_required"
            or manifest.get("privacy_gate") != "pending"
            or manifest.get("coordinate_gate") != "review_required"):
        raise BridgeError("handoff_policy_state_invalid")
    if not nz_graph_not_applicable:
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
    handoff_time = _utc(retrieved.isoformat(), "retrieved_at")
    first_manifest_time = _utc(
        expected.get("first_manifest_retrieved_at") or expected["retrieved_at"], "first_manifest_retrieved_at")
    latest_acquisition_time = _utc(expected["retrieved_at"], "latest_retrieved_at")
    if (handoff_time not in (first_manifest_time, latest_acquisition_time)
            or first_manifest_time > latest_acquisition_time
            or latest_acquisition_time > datetime.now(timezone.utc)
            or code != inventory_source["snapshot"].get("handoff_code_version")
            or config != inventory_source["snapshot"].get("handoff_config_version")):
        raise BridgeError("handoff_version_or_retrieval_mismatch")
    if urlsplit(source_url).hostname != inventory_source["snapshot"].get("source_host"):
        raise BridgeError("handoff_source_host_mismatch")
    normalized_hash, normalized_bytes = _digest(normalized_path)
    if normalized_hash != expected["normalized_sha256"]:
        raise BridgeError("normalized_handoff_hash_mismatch")
    graph_hash = None
    graph_manifest_hash = None
    if not nz_graph_not_applicable:
        graph_hash, _ = _digest(graph_records_path)
        if graph_hash != graph_manifest.get("records_sha256"):
            raise BridgeError("graph_handoff_hash_mismatch")
    manifest_hash, _ = _digest(manifest_path)
    if not nz_graph_not_applicable:
        graph_manifest_hash, _ = _digest(graph_manifest_path)
    rows = _read_jsonl(normalized_path)
    if len(rows) != inventory_source["counts"]["imported_observation_count"]:
        raise BridgeError("normalized_handoff_count_mismatch")
    if not nz_graph_not_applicable and graph_manifest.get("candidate_rows") != len(rows):
        raise BridgeError("graph_handoff_count_mismatch")
    if nz_graph_not_applicable:
        if len(rows) > 100_000:
            raise BridgeError("nz_programme_handoff_count_out_of_bounds")
        identifiers = set()
        for row in rows:
            normalized = row.get("normalized") if isinstance(row, dict) else None
            source_row_id = row.get("source_row_id") if isinstance(row, dict) else None
            record_key = row.get("source_record_key") if isinstance(row, dict) else None
            source_row = row.get("source_row") if isinstance(row, dict) else None
            if (row.get("source_id") != source or not isinstance(source_row_id, (str, int))
                    or not str(source_row_id).strip() or not isinstance(record_key, (str, int))
                    or not str(record_key).strip() or type(source_row) is not int or source_row < 1):
                raise BridgeError("nz_programme_identity_missing")
            mpi_id = normalized.get("mpi_risk_measure_id") if isinstance(normalized, dict) else None
            if (not isinstance(mpi_id, (str, int)) or not str(mpi_id).strip()
                    or normalized.get("establishment_id") != mpi_id
                    or str(record_key) not in {str(mpi_id), str(source_row_id)}):
                raise BridgeError("nz_programme_identity_missing")
            identity = (str(source_row_id), str(record_key), source_row)
            if identity in identifiers:
                raise BridgeError("nz_programme_identity_duplicate")
            identifiers.add(identity)
            if (not isinstance(normalized, dict)
                    or normalized.get("source_entity_type") != "registered-risk-management-programme"
                    or normalized.get("coordinates") is not None
                    or normalized.get("facility_identity_state") !=
                    "programme-record; location cardinality is source-reported and may be multiple"
                    or normalized.get("location_role") !=
                    "RMP-associated physical address; not verified as a unique operating facility"):
                raise BridgeError("nz_programme_identity_scope_invalid")
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
    if not nz_graph_not_applicable:
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
        "manifest_sha256": manifest_hash,
        "graph_manifest_sha256": graph_manifest_hash,
        "source_url": source_url,
        "source_host": urlsplit(source_url).hostname,
        "handoff_retrieved_at": handoff_time.isoformat(),
        "latest_verified_acquisition_at": _utc(expected["retrieved_at"], "retrieved_at").isoformat(),
        "normalized_sha256": normalized_hash,
        "normalized_byte_size": normalized_bytes,
        "graph_records_sha256": graph_hash,
        "graph_handoff_state": "not_applicable_programme_not_unique_site" if nz_graph_not_applicable else "private_candidates_verified",
        "terms_review_sha256": terms_digest,
        "rows": parsed,
        "groups": grouped,
        "representatives": representatives,
    }


def verify_current_candidate_taxonomy(connection: Any, *, candidate_id: str,
                                      representative_observation_id: str, snapshot_sha256: str,
                                      source_id: str, document: dict[str, Any],
                                      assignment_rows: list[dict[str, Any]]) -> None:
    """Require the exact append-only current assignment set, independent of legacy cache columns."""
    try:
        expected_rows = _canonical_rows(representative_observation_id, candidate_id, snapshot_sha256,
                                        document, assignment_rows)
        display_category = choose_display_category(expected_rows)
    except Exception:
        raise BridgeError("preview_candidate_taxonomy_expectation_invalid") from None
    sets = connection.execute("""SELECT assignment_set_id::text,representative_observation_id::text,
            snapshot_sha256,source_id,taxonomy_version,crosswalk_version,ruleset_version,display_category
        FROM real_preview.candidate_taxonomy_assignment_sets assignment_set
        WHERE candidate_id=%s AND snapshot_sha256=%s AND source_id=%s
          AND taxonomy_version=%s AND crosswalk_version=%s AND ruleset_version=%s
          AND NOT EXISTS (
              SELECT 1 FROM real_preview.candidate_taxonomy_assignment_sets newer
              WHERE newer.candidate_id=assignment_set.candidate_id
                AND newer.taxonomy_version=assignment_set.taxonomy_version
                AND (newer.created_at,newer.assignment_set_id) >
                    (assignment_set.created_at,assignment_set.assignment_set_id)
          )""",
        (candidate_id, snapshot_sha256, source_id, document["taxonomy_version"],
         document["crosswalk_version"], document["ruleset_version"])).fetchall()
    if len(sets) != 1:
        raise BridgeError("preview_candidate_taxonomy_assignment_set_missing_or_ambiguous")
    set_row = sets[0]
    expected_lineage = (representative_observation_id, snapshot_sha256, source_id,
                        document["taxonomy_version"], document["crosswalk_version"],
                        document["ruleset_version"], display_category)
    actual_lineage = tuple(str(value).strip() for value in set_row[1:])
    if actual_lineage != expected_lineage:
        raise BridgeError("preview_candidate_taxonomy_assignment_lineage_mismatch")
    actual_rows = connection.execute("""SELECT assignment_ordinal,primary_key,leaf_key,leaf_label,
            source_code_reference,source_label_reference,source_code,source_label,mapping_method,mapping_status
        FROM real_preview.candidate_taxonomy_assignments
        WHERE assignment_set_id=%s ORDER BY assignment_ordinal""", (set_row[0],)).fetchall()
    expected_assignments = tuple((ordinal, row.primary_key, row.leaf_key, row.leaf_label,
                                  row.source_code_reference, row.source_label_reference,
                                  row.source_code, row.source_label, row.method, row.status)
                                 for ordinal, row in enumerate(expected_rows))
    if tuple(tuple(row) for row in actual_rows) != expected_assignments:
        raise BridgeError("preview_candidate_taxonomy_assignments_mismatch")


def _deduplicate_exact_assignment_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse only rows equivalent under TaxonomyAssignment.ordering_key()."""
    unique = []
    seen = set()
    for row in rows:
        key = (
            row.get("primary_key"), row.get("leaf_key") or "", row.get("leaf_label") or "",
            row.get("source_code_reference") or "", row.get("source_label_reference") or "",
            row.get("source_code") or "", row.get("source_label") or "",
            row.get("mapping_method"), row.get("mapping_status"),
        )
        if key not in seen:
            seen.add(key)
            unique.append(row)
    return unique


def _verify_preview_source(connection: Any, source: str, entry: dict[str, Any], handoff: dict[str, Any],
                          inventory_source: dict[str, Any] | None = None) -> dict[str, Any]:
    snapshot = entry["snapshot_sha256"]
    run = connection.execute("""SELECT source_artifact_sha256, normalized_sha256, source_url, retrieved_at,
            accepted_count, quarantined_count, imported_observation_count, facility_count, public_rows,
            adapter_version, schema_version
        FROM real_preview.source_preview_runs WHERE source_id=%s AND snapshot_sha256=%s
        ORDER BY created_at DESC,run_id DESC LIMIT 1""",
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
    if str(run[2]) != str(manifest[3]):
        raise BridgeError("preview_run_manifest_mismatch")
    if str(run[9]) != str(manifest[5]) or str(run[10]) != str(manifest[6]):
        raise BridgeError("preview_run_manifest_version_mismatch")
    run_retrieved_at = _utc(
        run[3].isoformat() if hasattr(run[3], "isoformat") else str(run[3]), "latest_retrieved_at")
    manifest_retrieved_at = _utc(
        manifest[4].isoformat() if hasattr(manifest[4], "isoformat") else str(manifest[4]),
        "first_manifest_retrieved_at")
    handoff_retrieved_at = _utc(
        handoff["manifest"].get("retrieved_at_utc") or handoff["manifest"].get("retrieved_at"),
        "handoff_retrieved_at")
    if inventory_source is not None:
        handoff_retrieved_at, run_retrieved_at = _validate_preview_timeline(
            handoff["manifest"].get("retrieved_at_utc") or handoff["manifest"].get("retrieved_at"),
            manifest[4].isoformat() if hasattr(manifest[4], "isoformat") else str(manifest[4]),
            run[3].isoformat() if hasattr(run[3], "isoformat") else str(run[3]),
            inventory_source, entry)
    elif manifest_retrieved_at != handoff_retrieved_at or manifest_retrieved_at != run_retrieved_at:
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
        contract = IMPORTER.activity_contract(normalized, source, source_values)
        contract["taxonomy_assignment_rows"] = _deduplicate_exact_assignment_rows(
            contract["taxonomy_assignment_rows"]
        )
        try:
            _canonical_rows(
                preview_id_by_identifier[identifier],
                _uuid("preflight-source-record", source, snapshot, identifier),
                _uuid("preflight-artifact", source, snapshot),
                contract["crosswalk_document"], contract["taxonomy_assignment_rows"],
            )
        except Exception:
            raise BridgeError("preview_observation_taxonomy_contract_invalid") from None
        taxonomy_by_identifier[identifier] = contract
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
        verify_current_candidate_taxonomy(
            connection, candidate_id=str(db_candidate[0]),
            representative_observation_id=str(db_candidate[2]), snapshot_sha256=snapshot,
            source_id=source, document=merged["crosswalk_document"],
            assignment_rows=merged["taxonomy_assignment_rows"],
        )
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
    display_evidence_revision = hashlib.sha256(json.dumps(
        [(str(row[0]), row[27], row[29], row[30].isoformat() if row[30] else None,
          row[32], row[33]) for row in sorted(candidate_rows, key=lambda value: str(value[0]))],
        sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
    return {"run": run, "manifest": manifest, "observations": preview_observations,
            "preview_ids": preview_id_by_identifier,
            "candidates": by_group, "representatives": rep_by_id,
            "taxonomy": taxonomy_by_identifier,
            "display_evidence_revision": display_evidence_revision,
            "source_handoff_retrieved_at": handoff_retrieved_at.isoformat(),
            "latest_verified_acquisition_at": run_retrieved_at.isoformat()}


def _uuid(namespace: str, *parts: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, ":".join(("uec-v0", namespace, *parts))))


def _correction_source_record_key(snapshot_sha256: str, source_identifier: str,
                                  projection_revision: str | None = None,
                                  projection_policy_revision: str | None = None) -> str:
    """Append correction-derived evidence without colliding with frozen V0 rows."""
    if projection_revision:
        if not re.fullmatch(r"[0-9a-f]{64}", projection_revision):
            raise BridgeError("projection_revision_invalid")
        version = CORRECTION_SCOPE_PROJECTION_VERSION if projection_policy_revision else "v0-correction-v5"
        return f"{version}:{snapshot_sha256}:{source_identifier}:{projection_revision}"
    return f"{CORRECTION_PROJECTION_VERSION}:{snapshot_sha256}:{source_identifier}"


def _projection_revision(display_evidence_revision: str, contract: Mapping[str, Any],
                         projection_policy_revision: str | None = None) -> str:
    """Version only derived display/taxonomy projection, never source evidence."""
    payload = {
        "display_evidence_revision": display_evidence_revision,
        "crosswalk_document": contract.get("crosswalk_document"),
        "classification_ruleset_version": contract.get("classification_ruleset_version"),
    }
    if projection_policy_revision:
        payload["projection_policy_revision"] = projection_policy_revision
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _candidate_display_evidence_revision(candidate: Sequence[Any]) -> str:
    """Scope successor lineage to one candidate's display evidence only."""
    return hashlib.sha256(json.dumps(
        [str(candidate[0]), candidate[27], candidate[29],
         candidate[30].isoformat() if candidate[30] else None, candidate[32], candidate[33]],
        sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _safe_normalized(normalized: Any, source: str | None = None, source_values: Any = None) -> dict[str, Any]:
    if not isinstance(normalized, dict):
        return {}
    safe = {key: value for key, value in normalized.items()
            if key in _NORMALIZED_KEYS and key.casefold() not in _FORBIDDEN_KEYS}
    aliases = safe.get("alternate_names")
    aliases = aliases if isinstance(aliases, list) else []
    dba = safe.get("dba_names")
    if isinstance(dba, str) and dba.strip() and dba.strip() not in aliases:
        aliases.append(dba.strip())
    if aliases:
        safe["alternate_names"] = aliases
    if source:
        label = _facility_display_name(source, normalized, source_values)
        if isinstance(label, str) and 0 < len(label) <= 200:
            safe["facility_display_name"] = label
    safe.pop("dba_names", None)
    volumes = safe.get("activity_volume_codes")
    if isinstance(volumes, dict):
        safe["source_volume_categories"] = [
            {"code": str(value.get("code")), "provenance": key}
            for key, value in sorted(volumes.items()) if isinstance(value, dict) and value.get("code") is not None
        ]
    safe.pop("activity_volume_codes", None)
    return safe


def _facility_display_name(source: str, normalized: Any, source_values: Any = None) -> str | None:
    """Return a bounded source-typed facility label, never a contact/operator name."""
    if source == "ca.ontario.meat-plants":
        # Ontario's adapter normalizes a dedicated Plant Name column, while
        # the shared Canadian adapter also handles CFIA operator-name data.
        # Keep this source pinned to the exact bilingual acquisition header.
        value = source_values.get("Plant Name_ Nom de l'usine") if isinstance(source_values, dict) else None
        values = (value,)
    else:
        values = (normalized.get(field) for field in _FACILITY_NAME_FIELDS.get(source, ())) if isinstance(normalized, dict) else ()
    for value in values:
        if not isinstance(value, str):
            continue
        value = " ".join(value.split())
        if value and len(value) <= 200 and not any(ord(char) < 32 for char in value):
            return value
    return None


def _coordinate_scope_revision(source: str, normalized: dict[str, Any]) -> str | None:
    if source != "fr.georisques.icpe.animal":
        return None
    coordinates = normalized.get("coordinates") if isinstance(normalized.get("coordinates"), dict) else {}
    if (coordinates.get("jurisdiction_extent") == "outside-configured-france-extents"
            or normalized.get("in_default_map_scope") is False):
        return "france-source-coordinate-scope-v1"
    return None


def _source_coordinates_allowed(source: str, normalized: dict[str, Any]) -> bool:
    return _coordinate_scope_revision(source, normalized) is None


def _coordinate(normalized: dict[str, Any], preview_candidate: tuple[Any, ...], *, allow_display: bool,
                source: str | None = None) -> tuple[float | None, float | None, str | None, str | None, str | None, str | None]:
    coords = normalized.get("coordinates") if isinstance(normalized.get("coordinates"), dict) else {}
    lat, lon = coords.get("latitude"), coords.get("longitude")
    precision = coords.get("precision") or normalized.get("coordinate_precision") or normalized.get("geography_precision")
    method = coords.get("method") or normalized.get("coordinate_method")
    provider = coords.get("provider") or normalized.get("coordinate_provider")
    excluded_france_coordinate = source is not None and not _source_coordinates_allowed(source, normalized)
    if excluded_france_coordinate:
        lat = lon = None
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
            method = {"geoapify": "geoapify_forward", "locationiq": "locationiq_forward"}.get(
                preview_candidate[28], "address_geocode")
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


def _point_sql_parameters(latitude: float, longitude: float) -> tuple[float, float]:
    """Return PostGIS ST_MakePoint parameters in its required x, y order."""
    return longitude, latitude


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


def _preflight_target_identity(connection: Any, entries: dict[str, dict[str, Any]],
                               handoffs: dict[str, dict[str, Any]]) -> dict[str, dict[str, tuple[Any, list[Any]]]]:
    """Read-only collision check for all frozen handoffs before baseline hashing or writes."""
    countries: dict[str, str] = {}
    for source, handoff in handoffs.items():
        values = {str(parsed[2]).upper() for parsed, _ in handoff["rows"] if parsed[2]}
        if len(values) != 1 or len(next(iter(values), "")) != 2:
            raise BridgeError("source_country_inconsistent")
        countries[source] = next(iter(values))

    source_rows = connection.execute(
        "SELECT source_id,country_code FROM uec.sources WHERE source_id=ANY(%s)",
        (sorted(entries),)).fetchall()
    for source_id, country_code in source_rows:
        source = str(source_id)
        if source not in countries or str(country_code).strip().upper() != countries[source]:
            raise BridgeError("existing_source_identity_conflict")

    hashes = sorted({str(entry["source_artifact_sha256"]) for entry in entries.values()})
    artifact_rows = connection.execute(
        "SELECT sha256,storage_key,byte_size,retention_status FROM uec.raw_artifacts WHERE sha256=ANY(%s)",
        (hashes,)).fetchall()
    artifacts = {str(row[0]): (row[1], row[2], row[3]) for row in artifact_rows}
    for source in entries:
        entry = entries[source]
        digest = str(entry["source_artifact_sha256"])
        current = artifacts.get(digest)
        if entry["source_bytes_state"] == "retained":
            byte_size = int(entry["source_artifact_byte_size"])
            if current is not None and (current[0] is None or current[1] is None
                                        or int(current[1]) != byte_size or current[2] != "retained"):
                raise BridgeError("existing_artifact_provenance_conflict")
            artifacts[digest] = (str(Path(entry["source_artifact_path"]).resolve(strict=True)),
                                 byte_size, "retained")
        else:
            if current is not None and current[2] not in {"retained", "not_retained"}:
                raise BridgeError("existing_artifact_provenance_conflict")
            if current is not None and current[2] == "not_retained" and (current[0] is not None or current[1] is not None):
                raise BridgeError("existing_artifact_provenance_conflict")
            if current is None:
                artifacts[digest] = (None, None, "not_retained")

    preflight_facilities: dict[str, dict[str, tuple[Any, list[Any]]]] = {}
    for source in sorted(handoffs):
        groups = handoffs[source]["representatives"]
        facility_ids = {group: _uuid("facility", source, group) for group in groups}
        preflight_facilities[source] = {}
        if not facility_ids:
            continue
        rows = connection.execute("""SELECT facility.facility_id::text,facility.country_code,facility.canonical_name,
                array_agg(DISTINCT source_record.source_id) FILTER (WHERE source_record.source_id IS NOT NULL)
            FROM uec.facilities facility
            LEFT JOIN uec.facility_source_links link USING(facility_id)
            LEFT JOIN uec.source_records source_record USING(source_record_id)
            WHERE facility.facility_id=ANY(%s::uuid[])
            GROUP BY facility.facility_id,facility.country_code""",
            (list(facility_ids.values()),)).fetchall()
        group_by_id = {facility_id: group for group, facility_id in facility_ids.items()}
        for facility_id, country_code, canonical_name, linked_sources in rows:
            if str(country_code).strip().upper() != countries[source]:
                raise BridgeError("canonical_facility_identity_conflict")
            if any(str(linked_source) != source for linked_source in (linked_sources or [])):
                raise BridgeError("canonical_facility_source_identity_conflict")
            preflight_facilities[source][group_by_id[str(facility_id)]] = (
                (country_code, canonical_name), [(linked_source,) for linked_source in (linked_sources or [])])
    return preflight_facilities


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


def _baseline_contract() -> dict[str, Any]:
    """Load the approved V0 identity; never accept it from an operator flag."""
    try:
        value = json.loads((ROOT / "pipeline/contracts/development-baseline.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise BridgeError("development_baseline_contract_invalid") from None
    if (value.get("release_id") != "v0-candidate-2026-10-04-r3"
            or value.get("profile") != PROFILE
            or not _HASH.fullmatch(str(value.get("manifest_sha256")))):
        raise BridgeError("development_baseline_contract_invalid")
    return value


def _digest_query(connection: Any, query: str, params: tuple[Any, ...] = ()) -> str:
    """Hash ordered JSONB rows on the server, transferring only row digests."""
    digest = hashlib.sha256()
    with connection.cursor() as cursor:
        cursor.execute("SELECT encode(digest(row_payload::text,'sha256'),'hex') FROM ("
                       + query + ") AS baseline_rows(row_payload)", params)
        for row in cursor:
            digest.update(row[0].encode("ascii"))
            digest.update(b"\n")
    return digest.hexdigest()


def _baseline_snapshot(connection: Any, contract: dict[str, Any], *, expected_status: str = "promoted",
                       include_shared: bool = True, include_facts: bool = True) -> dict[str, Any]:
    """Verify and fingerprint the exact approved V0 state allowed beside a candidate."""
    release_id = contract["release_id"]
    expected = contract["expected"]
    release = connection.execute("SELECT status,profile,test_only FROM uec.releases WHERE release_id=%s", (release_id,)).fetchone()
    manifest = connection.execute("SELECT manifest_sha256 FROM uec.release_manifests WHERE release_id=%s", (release_id,)).fetchone()
    if release != (expected_status, PROFILE, False) or manifest != (contract["manifest_sha256"],):
        raise BridgeError("approved_v0_baseline_identity_mismatch")
    members, visible = connection.execute("SELECT count(*),count(*) FILTER (WHERE default_visible) FROM uec.release_members WHERE release_id=%s", (release_id,)).fetchone()
    named = connection.execute("SELECT count(*) FROM uec.release_members member JOIN uec.facilities facility USING(facility_id) WHERE member.release_id=%s AND member.default_visible AND NULLIF(BTRIM(facility.canonical_name),'') IS NOT NULL", (release_id,)).fetchone()[0]
    if int(members) < int(expected["public_rows"]) or int(visible) != int(expected["public_rows"]) or int(named) != int(expected["named_rows"]):
        raise BridgeError("approved_v0_baseline_count_mismatch")
    snapshot = {
        "release": _digest_query(connection, "SELECT to_jsonb(release) FROM uec.releases release WHERE release_id=%s ORDER BY release_id", (release_id,)),
        "manifest": _digest_query(connection, "SELECT to_jsonb(manifest) FROM uec.release_manifests manifest WHERE release_id=%s ORDER BY release_id", (release_id,)),
        "members": _digest_query(connection, "SELECT to_jsonb(member) FROM uec.release_members member WHERE release_id=%s ORDER BY facility_id,observation_id", (release_id,)),
    }
    if include_facts:
        snapshot.update({
            "facilities": _digest_query(connection, "SELECT to_jsonb(facility) FROM uec.facilities facility JOIN uec.release_members member USING(facility_id) WHERE member.release_id=%s ORDER BY facility.facility_id", (release_id,)),
            "observations": _digest_query(connection, "SELECT to_jsonb(observation) FROM uec.observations observation JOIN uec.release_members member ON member.observation_id=observation.observation_id WHERE member.release_id=%s ORDER BY observation.observation_id", (release_id,)),
            "source_records": _digest_query(connection, "SELECT to_jsonb(record) FROM uec.source_records record JOIN uec.observations observation USING(source_record_id) JOIN uec.release_members member ON member.observation_id=observation.observation_id WHERE member.release_id=%s ORDER BY record.source_record_id", (release_id,)),
        })
    if include_shared:
        snapshot["restrictions"] = _digest_query(
            connection, "SELECT to_jsonb(event) FROM uec.record_access_events event ORDER BY event.access_event_id")
    # Public relations may legitimately contain the V0 projection.  Their exact
    # row hashes must remain unchanged while candidate-only rows are appended.
    public = {}
    if include_shared:
        for relation in PUBLIC_PROJECTION_RELATIONS:
            if connection.execute("SELECT to_regclass(%s)", (relation,)).fetchone()[0] is not None:
                public[relation] = _digest_query(connection, f"SELECT to_jsonb(value) FROM {relation} value ORDER BY to_jsonb(value)::text")
        snapshot["public"] = public
    return snapshot


def _release_baseline_snapshot(connection: Any, release_id: str, manifest_sha256: str) -> dict[str, Any]:
    """Verify/fingerprint the Oct 18 public release facts and public aggregates."""
    if (release_id != RELEASE_BASELINE_ID
            or manifest_sha256 != RELEASE_BASELINE_MANIFEST_SHA256):
        raise BridgeError("release_baseline_contract_invalid")
    release = connection.execute(
        "SELECT status,profile,test_only FROM uec.releases WHERE release_id=%s", (release_id,)
    ).fetchone()
    manifest = connection.execute(
        "SELECT manifest_sha256 FROM uec.release_manifests WHERE release_id=%s", (release_id,)
    ).fetchone()
    if release != ("promoted", PROFILE, False) or manifest != (manifest_sha256,):
        raise BridgeError("release_baseline_identity_mismatch")
    members, visible = connection.execute(
        "SELECT count(*),count(*) FILTER (WHERE default_visible) FROM uec.release_members WHERE release_id=%s",
        (release_id,),
    ).fetchone()
    named = connection.execute(
        "SELECT count(*) FROM uec.release_members member JOIN uec.facilities facility USING(facility_id) "
        "WHERE member.release_id=%s AND member.default_visible AND NULLIF(BTRIM(facility.canonical_name),'') IS NOT NULL",
        (release_id,),
    ).fetchone()[0]
    if int(members) != RELEASE_BASELINE_PUBLIC_ROWS or int(visible) != RELEASE_BASELINE_PUBLIC_ROWS or int(named) <= 0:
        raise BridgeError("release_baseline_public_aggregate_mismatch")
    return _release_facts_snapshot(connection, release_id, {
        "members": int(members), "visible": int(visible), "named": int(named),
    }, include_facts=False)


def _release_facts_snapshot(connection: Any, release_id: str,
                             aggregates: dict[str, int] | None = None,
                             *, include_facts: bool = True) -> dict[str, Any]:
    """Fingerprint one release's immutable normalized facts, without shared tables."""
    snapshot = {
        "aggregates": aggregates or {},
        "release": _digest_query(connection, "SELECT to_jsonb(value) FROM uec.releases value WHERE release_id=%s", (release_id,)),
        "manifest": _digest_query(connection, "SELECT to_jsonb(value) FROM uec.release_manifests value WHERE release_id=%s", (release_id,)),
        "members": _digest_query(connection, "SELECT to_jsonb(value) FROM uec.release_members value WHERE release_id=%s ORDER BY facility_id,observation_id", (release_id,)),
    }
    if include_facts:
        snapshot.update({
            "facilities": _digest_query(connection, "SELECT to_jsonb(value) FROM uec.facilities value JOIN uec.release_members member USING(facility_id) WHERE member.release_id=%s ORDER BY value.facility_id", (release_id,)),
            "observations": _digest_query(connection, "SELECT to_jsonb(value) FROM uec.observations value JOIN uec.release_members member ON member.observation_id=value.observation_id WHERE member.release_id=%s ORDER BY value.observation_id", (release_id,)),
            "source_records": _digest_query(connection, "SELECT to_jsonb(value) FROM uec.source_records value JOIN uec.observations observation USING(source_record_id) JOIN uec.release_members member ON member.observation_id=observation.observation_id WHERE member.release_id=%s ORDER BY value.source_record_id", (release_id,)),
        })
    return snapshot


def _shared_fact_queries(release_ids: tuple[str, ...]) -> dict[str, tuple[str, tuple[list[str], ...]]]:
    ids = list(release_ids)
    return {
        "facilities": ("SELECT to_jsonb(value) FROM uec.facilities value WHERE EXISTS "
                       "(SELECT 1 FROM uec.release_members member WHERE member.facility_id=value.facility_id "
                       "AND member.release_id=ANY(%s)) ORDER BY value.facility_id", (ids,)),
        "observations": ("SELECT to_jsonb(value) FROM uec.observations value WHERE EXISTS "
                         "(SELECT 1 FROM uec.release_members member WHERE member.observation_id=value.observation_id "
                         "AND member.release_id=ANY(%s)) ORDER BY value.observation_id", (ids,)),
        "source_records": ("SELECT to_jsonb(value) FROM uec.source_records value WHERE EXISTS "
                           "(SELECT 1 FROM uec.observations observation JOIN uec.release_members member "
                           "ON member.observation_id=observation.observation_id "
                           "WHERE observation.source_record_id=value.source_record_id "
                           "AND member.release_id=ANY(%s)) ORDER BY value.source_record_id", (ids,)),
    }


def _shared_baseline_snapshot(connection: Any, release_ids: tuple[str, ...]) -> dict[str, Any]:
    """Hash shared restrictions/public/graph state once per before/after phase."""
    active_build = connection.execute(
        "SELECT count(*) FROM uec.graph_public_projection_builds "
        "WHERE release_id=%s AND active AND status='completed'", (RELEASE_BASELINE_ID,)
    ).fetchone()[0]
    if int(active_build) != 1:
        raise BridgeError("release_baseline_graph_build_mismatch")
    graph_edges = int(connection.execute(
        "SELECT count(*) FROM uec.graph_public_projection_edges edge "
        "JOIN uec.graph_public_projection_builds build USING(projection_id,release_id) "
        "WHERE build.release_id=%s AND build.active AND build.status='completed'", (RELEASE_BASELINE_ID,)
    ).fetchone()[0])
    evidence_references = int(connection.execute(
        "SELECT count(*) FROM uec.graph_public_projection_evidence_refs reference "
        "JOIN uec.graph_public_projection_builds build USING(projection_id) "
        "WHERE build.release_id=%s AND build.active AND build.status='completed'", (RELEASE_BASELINE_ID,)
    ).fetchone()[0])
    if graph_edges != 60263 or evidence_references != 1024:
        raise BridgeError("release_baseline_graph_aggregate_mismatch")
    result: dict[str, Any] = {
        "aggregates": {"graph_edges": graph_edges, "graph_evidence_references": evidence_references},
        "restrictions": _digest_query(connection, "SELECT to_jsonb(value) FROM uec.record_access_events value ORDER BY access_event_id"),
        "public": {}, "graph": {}, "facts": {},
    }
    for name, (query, params) in _shared_fact_queries(release_ids).items():
        result["facts"][name] = _digest_query(connection, query, params)
    for relation in PUBLIC_PROJECTION_RELATIONS:
        if connection.execute("SELECT to_regclass(%s)", (relation,)).fetchone()[0] is not None:
            result["public"][relation] = _digest_query(
                connection, f"SELECT to_jsonb(value) FROM {relation} value ORDER BY to_jsonb(value)::text"
            )
    for relation in GRAPH_IMMUTABLE_RELATIONS:
        if connection.execute("SELECT to_regclass(%s)", (relation,)).fetchone()[0] is not None:
            result["graph"][relation] = _digest_query(
                connection, f"SELECT to_jsonb(value) FROM {relation} value ORDER BY to_jsonb(value)::text"
            )
    return result


def _retained_release_snapshots(connection: Any, release_ids: tuple[str, ...]) -> dict[str, dict[str, Any]]:
    if len(set(release_ids)) != len(release_ids) or RELEASE_BASELINE_ID in release_ids:
        raise BridgeError("retained_release_inventory_invalid")
    snapshots: dict[str, dict[str, Any]] = {}
    for release_id in sorted(release_ids):
        row = connection.execute(
            "SELECT status,profile,test_only FROM uec.releases WHERE release_id=%s", (release_id,)
        ).fetchone()
        if row != ("candidate", PROFILE, False):
            raise BridgeError("retained_release_missing")
        manifest = connection.execute(
            "SELECT manifest_sha256 FROM uec.release_manifests WHERE release_id=%s", (release_id,)
        ).fetchone()
        expected_manifest = RETAINED_MANIFEST_SHA256.get(release_id)
        if (expected_manifest is None and manifest is not None) or (
                expected_manifest is not None and manifest != (expected_manifest,)):
            raise BridgeError("retained_release_manifest_mismatch")
        snapshots[release_id] = _release_facts_snapshot(connection, release_id, include_facts=False)
    return snapshots


def _release_append_scope_is_valid(connection: Any, baseline_ids: tuple[str, ...], retained_ids: tuple[str, ...],
                                   candidate_release_id: str) -> None:
    allowed_ids = {*baseline_ids, *retained_ids, candidate_release_id}
    releases = connection.execute("SELECT release_id FROM uec.releases ORDER BY release_id").fetchall()
    if {str(row[0]) for row in releases} - allowed_ids:
        raise BridgeError("candidate_append_has_unexpected_release")
    manifests = connection.execute("SELECT release_id FROM uec.release_manifests ORDER BY release_id").fetchall()
    manifest_ids = {str(row[0]) for row in manifests}
    if not set(baseline_ids).issubset(manifest_ids) or manifest_ids - (set(baseline_ids) | set(retained_ids)):
        raise BridgeError("candidate_append_manifest_scope_mismatch")


def _validate_preview_source_database_url(database_url: str) -> None:
    parsed = urlsplit(database_url)
    query_options = {key.lower() for key, _ in parse_qsl(parsed.query, keep_blank_values=True)}
    if (parsed.scheme not in {"postgres", "postgresql"}
            or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
            or parsed.path.strip("/") != "uec_launch_sources_test_20261025"
            or query_options.intersection({"host", "hostaddr", "service", "servicefile"})):
        raise BridgeError("preview_source_database_not_allowlisted")


def _inheritance_parent_id(append_to_release_baseline: bool, baseline_release_id: str,
                           parent_candidate_release_id: str | None) -> str | None:
    if parent_candidate_release_id is not None:
        return parent_candidate_release_id
    return baseline_release_id if append_to_release_baseline else None


def _reconcile_release_source_cohort(connection: Any, candidate_release_id: str,
                                     parent_release_id: str,
                                     replacement_sources: tuple[str, ...]) -> list[str]:
    expected_inherited = {str(row[0]) for row in connection.execute("""SELECT DISTINCT record.source_id
        FROM uec.release_members member
        JOIN uec.observations observation ON observation.observation_id=member.observation_id
        JOIN uec.source_records record ON record.source_record_id=observation.source_record_id
        WHERE member.release_id=%s AND NOT (record.source_id = ANY(%s))""",
        (parent_release_id, list(replacement_sources))).fetchall()}
    expected = expected_inherited | set(replacement_sources)
    actual = {str(row[0]) for row in connection.execute("""SELECT DISTINCT record.source_id
        FROM uec.release_members member
        JOIN uec.observations observation ON observation.observation_id=member.observation_id
        JOIN uec.source_records record ON record.source_record_id=observation.source_record_id
        WHERE member.release_id=%s""", (candidate_release_id,)).fetchall()}
    if actual != expected:
        raise BridgeError("candidate_source_cohort_reconciliation_mismatch")
    return sorted(actual)


def _append_scope_is_valid(connection: Any, baseline_release_id: str, candidate_release_id: str) -> None:
    releases = connection.execute("SELECT release_id,status,test_only,summary FROM uec.releases ORDER BY release_id").fetchall()
    prior_ids: set[str] = set()
    successor = re.fullmatch(r"(.+)-r([2-9][0-9]*)", candidate_release_id)
    if successor:
        family, revision = successor.group(1), int(successor.group(2))
        prior_ids = {family, *(f"{family}-r{value}" for value in range(2, revision))}
    permitted = {baseline_release_id, candidate_release_id}
    permitted.update(prior_ids)
    if {str(row[0]) for row in releases} - permitted:
        raise BridgeError("candidate_append_has_unexpected_release")
    for release_id, status, test_only, summary in releases:
        if str(release_id) in prior_ids and (status != "candidate" or test_only is not False
                                             or not isinstance(summary, dict)
                                             or summary.get("candidate_only") is not True):
            raise BridgeError("candidate_append_prior_candidate_identity_mismatch")
    manifests = connection.execute("SELECT release_id FROM uec.release_manifests ORDER BY release_id").fetchall()
    manifest_ids = {str(row[0]) for row in manifests}
    # A successor may coexist with the verified candidate lineage.  Preserve
    # the baseline manifest requirement, allow manifests only for the exact
    # predecessor releases, and reject a pre-created target manifest.
    permitted_manifest_ids = {baseline_release_id}
    permitted_manifest_ids.update(prior_ids)
    if (baseline_release_id not in manifest_ids
            or manifest_ids - permitted_manifest_ids
            or candidate_release_id in manifest_ids):
        raise BridgeError("candidate_append_manifest_scope_mismatch")


def bridge(database_url: str, expected_database: str, freeze: dict[str, Any], inventory: dict[str, Any],
            *, candidate_only_ack: bool, append_to_v0_baseline: bool = False,
            parent_candidate_release_id: str | None = None,
            append_to_release_baseline: bool = False,
            baseline_release_id: str | None = None,
            baseline_manifest_sha256: str | None = None,
            retained_release_ids: tuple[str, ...] = (),
            preview_source_database_url: str | None = None) -> dict[str, Any]:
    parsed_url = urlsplit(database_url)
    routing = {key.lower() for key, _ in parse_qsl(parsed_url.query, keep_blank_values=True)}
    if (parsed_url.scheme not in {"postgres", "postgresql"}
            or parsed_url.hostname not in {"127.0.0.1", "localhost", "::1"}
            or routing.intersection({"host", "hostaddr", "service", "servicefile"})):
        raise BridgeError("database_must_be_loopback")
    if not candidate_only_ack:
        raise BridgeError("explicit_candidate_only_ack_required")
    if append_to_v0_baseline and append_to_release_baseline:
        raise BridgeError("baseline_modes_are_mutually_exclusive")
    append_mode = append_to_v0_baseline or append_to_release_baseline
    additional_baseline_ids: tuple[str, ...] = ()
    if append_to_v0_baseline:
        if expected_database not in {"uec_v0_api_repair", "uec_launch_sources_test_20261025"}:
            raise BridgeError("append_candidate_database_not_allowlisted")
        baseline_contract = _baseline_contract()
        if freeze["release_id"] == baseline_contract["release_id"]:
            raise BridgeError("append_candidate_release_id_must_be_distinct")
        if parent_candidate_release_id is not None:
            successor = re.fullmatch(r"(.+)-r([2-9][0-9]*)", freeze["release_id"])
            if (successor is None or parent_candidate_release_id != f"{successor.group(1)}-r{int(successor.group(2)) - 1}"):
                raise BridgeError("parent_candidate_must_be_immediate_same_family_predecessor")
    elif append_to_release_baseline:
        if expected_database != "uec_country_release_test_20261027":
            raise BridgeError("append_candidate_database_not_allowlisted")
        baseline_contract = _baseline_contract()
        if (baseline_release_id != RELEASE_BASELINE_ID
                or baseline_manifest_sha256 != RELEASE_BASELINE_MANIFEST_SHA256):
            raise BridgeError("release_baseline_contract_invalid")
        if tuple(sorted(retained_release_ids)) != tuple(sorted(RETAINED_RELEASE_IDS)):
            raise BridgeError("retained_release_inventory_invalid")
        if preview_source_database_url is None:
            raise BridgeError("preview_source_database_url_required")
        _validate_preview_source_database_url(preview_source_database_url)
        if freeze["release_id"] in {baseline_contract["release_id"], baseline_release_id, *retained_release_ids}:
            raise BridgeError("append_candidate_release_id_must_be_distinct")
        additional_baseline_ids = (baseline_release_id, *retained_release_ids)
        if parent_candidate_release_id is not None:
            if parent_candidate_release_id != baseline_release_id:
                successor = re.fullmatch(r"(.+)-r([2-9][0-9]*)", freeze["release_id"])
                if (successor is None or parent_candidate_release_id != f"{successor.group(1)}-r{int(successor.group(2)) - 1}"):
                    raise BridgeError("parent_candidate_must_be_immediate_same_family_predecessor")
    elif preview_source_database_url is not None:
        raise BridgeError("preview_source_database_requires_release_baseline_mode")
    elif not re.fullmatch(r"uec_v0_review(?:_[a-z0-9]+)?", expected_database):
        raise BridgeError("expected_database_name_must_be_isolated_v0_review")
    if parsed_url.path.lstrip("/") != expected_database:
        raise BridgeError("database_name_does_not_match_expected")
    entries = {item["source_id"]: item for item in freeze["selected_sources"]}
    if append_to_release_baseline and set(entries) != RELEASE_REPLACEMENT_SOURCES:
        raise BridgeError("release_baseline_requires_seven_non_us_replacement_sources")
    inheritance_parent_release_id = _inheritance_parent_id(
        append_to_release_baseline, baseline_release_id or "", parent_candidate_release_id)
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
                   "handoff_manifest_sha256": handoffs[source]["manifest_sha256"],
                   "graph_manifest_sha256": handoffs[source]["graph_manifest_sha256"],
                   "graph_records_sha256": handoffs[source]["graph_records_sha256"],
                   "graph_handoff_state": handoffs[source]["graph_handoff_state"],
                   "terms_review_sha256": handoffs[source]["terms_review_sha256"],
                   "retrieved_at": handoffs[source].get("handoff_retrieved_at"),
                   "source_handoff_retrieved_at": handoffs[source].get("handoff_retrieved_at"),
                   "latest_verified_acquisition_at": handoffs[source].get("latest_verified_acquisition_at"),
                   "handoff_code_version": handoffs[source]["manifest"].get("code_version"),
                   "handoff_config_version": handoffs[source]["manifest"].get("config_version"),
                   "source_observations": len(handoffs[source]["rows"]),
                    "facility_candidates": len(handoffs[source]["representatives"]),
               } for source in sorted(entries)],
               "public_authorized": False, "review_approval_created": False,
               "graph_claims_imported": False, "graph_projection_verified": False,
               "graph_readiness": "not_imported",
               "source_observation_count": sum(len(item["rows"]) for item in handoffs.values()),
               "facility_candidate_count": sum(len(item["representatives"]) for item in handoffs.values()),
               "parent_candidate_release_id": inheritance_parent_release_id}
    counts = {"sources": len(entries), "source_observations": 0, "facility_candidates": 0,
              "source_coordinates": 0, "provider_derived_coordinates": 0, "coarse_references": 0,
              "unmapped": 0, "release_members": 0}
    try:
        # This transaction grows substantially as the selected cohort is inserted.
        # Disable psycopg's automatic prepared-statement promotion so plans are
        # not fixed against the initially empty isolated candidate database.
        with ExitStack() as stack:
            preview_connection = None
            if append_to_release_baseline:
                preview_connection = stack.enter_context(
                    psycopg.connect(preview_source_database_url, prepare_threshold=None))
                stack.enter_context(preview_connection.transaction())
                preview_connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                source_database = preview_connection.execute("SELECT current_database()").fetchone()[0]
                if source_database != "uec_launch_sources_test_20261025":
                    raise BridgeError("preview_source_database_mismatch")
                from pipeline.scripts import release_baseline
                try:
                    contract = release_baseline.load_contract(ROOT / "pipeline/contracts/development-baseline.json")
                    baseline_report = release_baseline.verify_connection(preview_connection, contract)
                except Exception:
                    raise BridgeError("preview_source_baseline_verification_failed") from None
                if (baseline_report.get("status") != "verified"
                        or baseline_report.get("release_id") != "v0-candidate-2026-10-04-r3"
                        or baseline_report.get("manifest_sha256") != baseline_contract["manifest_sha256"]):
                    raise BridgeError("preview_source_baseline_verification_failed")
            connection = stack.enter_context(psycopg.connect(database_url, prepare_threshold=None))
            stack.enter_context(connection.transaction())
            connection.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
            connection.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("v0-candidate-bridge:" + freeze["release_id"],))
            db_name = connection.execute("SELECT current_database()").fetchone()[0]
            if db_name != expected_database:
                raise BridgeError("connected_database_mismatch")
            connection.execute("SELECT retention_status FROM uec.raw_artifacts LIMIT 0")
            target_facility_checks = _preflight_target_identity(connection, entries, handoffs)
            public_projection_before = _public_projection_count(connection)
            baseline_before = None
            if append_mode:
                baseline_before = {"v0": _baseline_snapshot(
                    connection, baseline_contract,
                    expected_status="validated" if append_to_release_baseline else "promoted",
                    include_shared=not append_to_release_baseline,
                    include_facts=not append_to_release_baseline)}
                if append_to_release_baseline:
                    shared_release_ids = tuple(sorted((baseline_contract["release_id"], baseline_release_id,
                                                       *retained_release_ids)))
                    baseline_before["shared"] = _shared_baseline_snapshot(connection, shared_release_ids)
                    baseline_before["release"] = _release_baseline_snapshot(
                        connection, baseline_release_id, baseline_manifest_sha256)
                    baseline_before["retained"] = _retained_release_snapshots(connection, retained_release_ids)
            if (not append_mode and (public_projection_before != 0
                    or connection.execute("SELECT count(*) FROM uec.releases WHERE status IN ('validated','promoted')").fetchone()[0] != 0
                    or connection.execute("SELECT count(*) FROM uec.release_manifests").fetchone()[0] != 0)):
                raise BridgeError("candidate_database_has_public_release_state")
            if append_to_v0_baseline:
                _append_scope_is_valid(connection, baseline_contract["release_id"], freeze["release_id"])
            elif append_to_release_baseline:
                _release_append_scope_is_valid(
                    connection, (baseline_contract["release_id"], baseline_release_id),
                    retained_release_ids, freeze["release_id"])
            inherited_members = 0
            if inheritance_parent_release_id is not None:
                parent = connection.execute("SELECT status,profile,test_only,summary FROM uec.releases WHERE release_id=%s",
                                            (inheritance_parent_release_id,)).fetchone()
                if append_to_release_baseline and inheritance_parent_release_id == baseline_release_id:
                    if parent is None or parent[:3] != ("promoted", PROFILE, False):
                        raise BridgeError("parent_candidate_identity_mismatch")
                else:
                    if (parent is None or parent[0] != "candidate" or parent[1] != PROFILE or parent[2] is not False
                            or not isinstance(parent[3], dict) or parent[3].get("candidate_only") is not True):
                        raise BridgeError("parent_candidate_identity_mismatch")
                    if connection.execute("SELECT count(*) FROM uec.release_manifests WHERE release_id=%s",
                                          (inheritance_parent_release_id,)).fetchone()[0] != 0:
                        raise BridgeError("parent_candidate_manifest_exists")
            # The exact freeze key is immutable: same key is a safe no-op; a
            # reused release ID with a different selection stops before writes.
            existing = _release_existing(connection, freeze["release_id"], freeze_hash)
            if not existing:
                if (not append_mode
                        and connection.execute("SELECT count(*) FROM uec.release_members").fetchone()[0] != 0):
                    raise BridgeError("candidate_database_membership_not_empty")
                if (not append_mode
                        and connection.execute("SELECT count(*) FROM uec.releases").fetchone()[0] != 0):
                    raise BridgeError("candidate_database_releases_not_empty")
            # Validate every frozen source while the transaction is still
            # read-only. A late source mismatch must not follow hours of
            # canonical inserts only to force a rollback.
            preview_checks = {}
            for source, entry in entries.items():
                print(json.dumps({"phase": "preview_validation", "source_id": source}, sort_keys=True), file=sys.stderr)
                try:
                    preview_checks[source] = _verify_preview_source(
                        preview_connection or connection, source, entry, handoffs[source],
                        inventory_sources[source])
                except BridgeError as error:
                    # Source IDs and stable guard codes are safe operational
                    # diagnostics; do not surface row data or SQL payloads.
                    raise BridgeError(f"preview_validation_failed:{source}:{error}") from None
            for provenance in summary["source_provenance"]:
                provenance["display_evidence_revision"] = preview_checks[provenance["source_id"]]["display_evidence_revision"]
            if not existing:
                connection.execute("""INSERT INTO uec.releases(release_id,status,ruleset_version,summary,profile,test_only)
                    VALUES (%s,'candidate',%s,%s,%s,false)""",
                    (freeze["release_id"], "v0-candidate-freeze-v1", Jsonb(summary), PROFILE))
            for source, entry in entries.items():
                print(json.dumps({"phase": "source_write_started", "source_id": source,
                                  "observation_count": len(handoffs[source]["rows"])}, sort_keys=True), file=sys.stderr)
                handoff = handoffs[source]
                preview_check = preview_checks[source]
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
                projection_revisions: dict[str, str] = {}
                projection_policy_revisions: dict[str, str | None] = {}
                facility_checks = target_facility_checks[source]
                # Source-native group identity remains stable across snapshots;
                # no name/address-based cross-source matching is attempted.
                for parsed, raw in handoff["rows"]:
                    identifier = str(parsed[0])
                    group = str(parsed[IMPORTER.SOURCE_GROUP_KEY_INDEX])
                    parsed_at = retrieved
                    normalized = raw.get("normalized") if isinstance(raw.get("normalized"), dict) else {}
                    contract = preview_check["taxonomy"][identifier]
                    candidate = candidate_rows[group]
                    candidate_display_revision = _candidate_display_evidence_revision(candidate)
                    projection_policy_revision = _coordinate_scope_revision(source, normalized)
                    projection_policy_revisions[identifier] = projection_policy_revision
                    projection_revision = _projection_revision(candidate_display_revision, contract,
                                                                projection_policy_revision)
                    projection_revisions[identifier] = projection_revision
                    source_record_key = _correction_source_record_key(
                        entry["snapshot_sha256"], identifier, projection_revision, projection_policy_revision)
                    raw_fields = {"evidence_kind": "authenticated_normalized_handoff",
                                  "snapshot_sha256": entry["snapshot_sha256"],
                                  "source_identifier": identifier,
                                  "normalized": _safe_normalized(normalized, source, raw.get("source_values")),
                                  "source_activity_codes": contract.get("source_activity_codes", []),
                                  "source_activity_labels": contract.get("source_activity_labels", []),
                                  "handoff_normalized_sha256": handoff["normalized_sha256"]}
                    connection.execute("""INSERT INTO uec.source_records
                        (source_id,source_record_key,artifact_id,raw_fields,parsed_at)
                        VALUES (%s,%s,%s,%s,%s) ON CONFLICT (source_id,source_record_key,artifact_id) DO NOTHING""",
                        (source, source_record_key, artifact_id, Jsonb(raw_fields), parsed_at))
                    stored_record = connection.execute("SELECT source_record_id::text,raw_fields FROM uec.source_records WHERE source_id=%s AND source_record_key=%s AND artifact_id=%s",
                                                       (source, source_record_key, artifact_id)).fetchone()
                    if stored_record is None or stored_record[1] != raw_fields:
                        raise BridgeError("source_record_idempotency_conflict")
                    source_record_id = stored_record[0]
                    facility_id = _uuid("facility", source, group)
                    representative_parsed, _ = handoff["representatives"][group]
                    country = str(representative_parsed[2] or country).upper()
                    existing_facility, linked_sources = facility_checks.get(group, (None, []))
                    if existing_facility and str(existing_facility[0]).strip().upper() != country:
                        raise BridgeError("canonical_facility_identity_conflict")
                    if any(row[0] != source for row in linked_sources):
                        raise BridgeError("canonical_facility_source_identity_conflict")
                    rep_row = handoff["representatives"][group][1]
                    display_name = _facility_display_name(source, rep_row.get("normalized"), rep_row.get("source_values"))
                    if (not append_mode and existing_facility and existing_facility[1]
                            and display_name and existing_facility[1] != display_name):
                        raise BridgeError("canonical_facility_name_conflict")
                    facility_conflict = "DO NOTHING" if append_mode else (
                        "DO UPDATE SET canonical_name=COALESCE(NULLIF(BTRIM(uec.facilities.canonical_name),''),EXCLUDED.canonical_name)"
                    )
                    connection.execute(f"""INSERT INTO uec.facilities(facility_id,canonical_name,country_code,city,postal_code)
                        VALUES (%s,%s,%s,%s,%s) ON CONFLICT (facility_id) {facility_conflict}""",
                        (facility_id, display_name, country, representative_parsed[3], representative_parsed[4]))
                    connection.execute("""INSERT INTO uec.facility_source_links(facility_id,source_record_id,match_method,review_status)
                        VALUES (%s,%s,'source_native_group_key','automatic') ON CONFLICT DO NOTHING""",
                        (facility_id, source_record_id))
                    source_observed = parsed[8]
                    observed_at = source_observed or retrieved
                    observed_basis = "source_asserted_at" if source_observed else "project_retrieved_at"
                    is_representative = preview_check["representatives"].get(group) == identifier
                    latitude, longitude, coord_method, coord_precision, coord_provider, point_origin = _coordinate(
                        normalized, candidate, allow_display=is_representative, source=source)
                    if (latitude is None and parsed[5] is not None and parsed[6] is not None
                            and _source_coordinates_allowed(source, normalized)):
                        latitude, longitude = parsed[5], parsed[6]
                        coord_method = str(parsed[19] or "source_method_unknown")
                        coord_precision = str(parsed[7] or "source_precision_unknown")
                        coord_provider = parsed[20]
                        point_origin = "source_coordinates"
                    coord_geom = ("ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography" if latitude is not None else "NULL")
                    candidate_display_allowed = (_source_coordinates_allowed(source, normalized)
                                                  or point_origin in {"provider_derived", "verified_coarse_reference"})
                    if is_representative and candidate[11] is not None and candidate_display_allowed:
                        if candidate[27] is not None and candidate[29] == "accepted":
                            display_location = {"latitude": candidate[11], "longitude": candidate[12],
                                "method": coord_method, "precision": candidate[24],
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
                        "handoff_manifest_sha256": handoff["manifest_sha256"],
                        "graph_manifest_sha256": handoff["graph_manifest_sha256"],
                        "graph_records_sha256": handoff["graph_records_sha256"],
                        "graph_handoff_state": handoff["graph_handoff_state"],
                        "location_class": parsed[1], "source_location": {
                            "latitude": parsed[5], "longitude": parsed[6], "precision": parsed[7],
                            "coordinate_method": parsed[19], "coordinate_provider": parsed[20],
                        } if parsed[5] is not None else None,
                        "display_location": display_location,
                        "private_location_evidence": ({key: value for key, value in normalized["private_location_evidence"].items()
                            if key in _PRIVATE_LOCATION_KEYS} if isinstance(normalized.get("private_location_evidence"), dict) else None),
                        "source_preview_observation_id": preview_check["preview_ids"].get(identifier),
                        "source_preview_candidate_id": candidate[0],
                        "display_evidence_revision": candidate_display_revision,
                        "source_group_key": group,
                        "activity": {key: contract.get(key) for key in (
                            "category", "activity_categories", "source_activity_codes", "source_activity_labels",
                            "activity_mapping_status", "classification_ruleset_version", "taxonomy_mapping_method")},
                        "source_status": _safe_normalized(normalized, source, raw.get("source_values")),
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
                        observation_params += _point_sql_parameters(latitude, longitude)
                    observation_params += (coord_method, coord_precision, observed_at)
                    connection.execute(f"""INSERT INTO uec.observations
                        (facility_id,source_record_id,observed_at,observation,classification,ruleset_id,rule_id,
                         classification_category,classification_review_status,default_visible,optional_filter,
                         coordinate,coordinate_method,coordinate_precision,coordinate_review_status,first_observed_at)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'review_required',false,%s,{coord_geom},%s,%s,'review_required',%s)
                        ON CONFLICT (facility_id,source_record_id,observed_at) DO NOTHING""",
                        observation_params)
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
                    source_record_key = _correction_source_record_key(
                        entry["snapshot_sha256"], identifier, projection_revisions[identifier],
                        projection_policy_revisions[identifier])
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
                print(json.dumps({"phase": "source_write_verified", "source_id": source,
                                  "observation_count": len(handoff["rows"])}, sort_keys=True), file=sys.stderr)
            if inheritance_parent_release_id is not None:
                inherited_members = connection.execute("""INSERT INTO uec.release_members
                    (release_id,facility_id,observation_id,default_visible)
                    SELECT %s,parent.facility_id,parent.observation_id,false
                      FROM uec.release_members parent
                      JOIN uec.observations observation ON observation.observation_id=parent.observation_id
                      JOIN uec.source_records record ON record.source_record_id=observation.source_record_id
                     WHERE parent.release_id=%s AND NOT (record.source_id = ANY(%s))
                    ON CONFLICT (release_id,facility_id) DO NOTHING
                    RETURNING facility_id""", (freeze["release_id"], inheritance_parent_release_id, sorted(entries))).fetchall()
                expected_inherited = connection.execute("""SELECT count(*)
                      FROM uec.release_members parent
                      JOIN uec.observations observation ON observation.observation_id=parent.observation_id
                      JOIN uec.source_records record ON record.source_record_id=observation.source_record_id
                     WHERE parent.release_id=%s AND NOT (record.source_id = ANY(%s))""",
                    (inheritance_parent_release_id, sorted(entries))).fetchone()[0]
                inherited_members = int(expected_inherited)
                preserved = connection.execute("""SELECT count(*)
                      FROM uec.release_members parent
                      JOIN uec.observations observation ON observation.observation_id=parent.observation_id
                      JOIN uec.source_records record ON record.source_record_id=observation.source_record_id
                      JOIN uec.release_members successor ON successor.release_id=%s AND successor.facility_id=parent.facility_id
                     WHERE parent.release_id=%s AND NOT (record.source_id = ANY(%s))
                       AND successor.observation_id=parent.observation_id AND successor.default_visible=false""",
                    (freeze["release_id"], inheritance_parent_release_id, sorted(entries))).fetchone()[0]
                stale_selected = connection.execute("""SELECT count(*) FROM uec.release_members member
                      JOIN uec.observations observation ON observation.observation_id=member.observation_id
                      JOIN uec.source_records record ON record.source_record_id=observation.source_record_id
                     WHERE member.release_id=%s AND record.source_id = ANY(%s)
                       AND observation.observation->>'source_preview_candidate_id' IS NULL""",
                    (freeze["release_id"], sorted(entries))).fetchone()[0]
                if int(preserved) != inherited_members or int(stale_selected) != 0:
                    raise BridgeError("parent_candidate_copy_integrity_mismatch")
                summary["inherited_member_count"] = inherited_members
                connection.execute("UPDATE uec.releases SET summary=summary || %s::jsonb WHERE release_id=%s",
                                   (Jsonb({"parent_candidate_release_id": inheritance_parent_release_id,
                                           "inherited_member_count": inherited_members}), freeze["release_id"]))
            counts["facility_candidates"] = counts["release_members"]
            counts["facility_candidates"] += inherited_members
            if counts["source_observations"] != summary["source_observation_count"] or counts["facility_candidates"] != summary["facility_candidate_count"] + inherited_members:
                raise BridgeError("bridge_total_reconciliation_failed")
            actual_members, visible_members = connection.execute(
                "SELECT count(*),count(*) FILTER (WHERE default_visible) FROM uec.release_members WHERE release_id=%s",
                (freeze["release_id"],)).fetchone()
            if int(actual_members) != counts["facility_candidates"] or int(visible_members) != 0:
                raise BridgeError("release_membership_count_or_visibility_mismatch")
            if append_to_release_baseline:
                actual_sources = _reconcile_release_source_cohort(
                    connection, freeze["release_id"], inheritance_parent_release_id,
                    tuple(sorted(entries)))
                summary["replacement_sources"] = sorted(entries)
                summary["selected_sources"] = actual_sources
                connection.execute("UPDATE uec.releases SET summary=summary || %s::jsonb WHERE release_id=%s",
                                   (Jsonb({"selected_sources": actual_sources,
                                           "replacement_sources": sorted(entries)}), freeze["release_id"]))
            if (not append_mode and connection.execute("SELECT count(*) FROM uec.release_members WHERE release_id<>%s",
                                  (freeze["release_id"],)).fetchone()[0] != 0):
                raise BridgeError("candidate_database_has_unrelated_release_members")
            if not append_mode and _public_projection_count(connection) != 0:
                raise BridgeError("public_projection_state_changed")
            release_state = connection.execute("SELECT status,profile,test_only FROM uec.releases WHERE release_id=%s",
                                               (freeze["release_id"],)).fetchone()
            if release_state != ("candidate", PROFILE, False):
                raise BridgeError("candidate_release_state_mismatch")
            if connection.execute("SELECT count(*) FROM uec.release_manifests WHERE release_id=%s",
                                  (freeze["release_id"],)).fetchone()[0] != 0:
                raise BridgeError("candidate_release_manifest_exists")
            if append_to_v0_baseline:
                _append_scope_is_valid(connection, baseline_contract["release_id"], freeze["release_id"])
                if _baseline_snapshot(connection, baseline_contract) != baseline_before["v0"]:
                    raise BridgeError("approved_v0_baseline_changed")
            elif append_to_release_baseline:
                _release_append_scope_is_valid(
                    connection, (baseline_contract["release_id"], baseline_release_id),
                    retained_release_ids, freeze["release_id"])
                baseline_after = {
                    "v0": _baseline_snapshot(connection, baseline_contract, expected_status="validated",
                                              include_shared=False, include_facts=False),
                    "shared": _shared_baseline_snapshot(connection, shared_release_ids),
                    "release": _release_baseline_snapshot(connection, baseline_release_id, baseline_manifest_sha256),
                    "retained": _retained_release_snapshots(connection, retained_release_ids),
                }
                if baseline_after != baseline_before:
                    raise BridgeError("approved_release_baseline_changed")
    except psycopg.Error as error:
        # Database diagnostics may contain private URLs or server details.
        failure = BridgeError("candidate_bridge_database_operation_failed")
        # Keep only payload-free diagnostics on the in-process exception for
        # disposable integration tests; CLI output remains the generic code.
        failure.database_error_class = type(error).__name__
        failure.database_sqlstate = getattr(error, "sqlstate", None)
        failure.database_column = getattr(getattr(error, "diag", None), "column_name", None)
        failure.database_message = getattr(getattr(error, "diag", None), "message_primary", None)
        raise failure from None
    return {"status": "candidate_only_staged", "release_id": freeze["release_id"],
            "freeze_sha256": freeze_hash, "counts": counts, "public_authorized": False,
            "graph_claims_imported": False, "graph_projection_verified": False,
            "graph_readiness": "not_imported",
            "review_events_created": 0, "rights_decisions_created": 0,
            "public_projection_rows_created": 0}


def _repair_candidate_names_checked(database_url: str, expected_database: str, freeze: dict[str, Any],
                                    inventory: dict[str, Any], *, apply: bool,
                                    required_database: str, required_release_id: str) -> dict[str, Any]:
    """Project verified retained facility labels onto blank names only.

    This operation deliberately does not rewrite evidence, observations,
    membership, or review state. Dry-run is the default.
    """
    if expected_database != required_database or freeze.get("release_id") != required_release_id:
        raise BridgeError("name_repair_target_mismatch")
    parsed_url = urlsplit(database_url)
    if parsed_url.scheme not in {"postgres", "postgresql"} or parsed_url.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise BridgeError("database_must_be_loopback")
    if parsed_url.path.lstrip("/") != expected_database:
        raise BridgeError("database_name_does_not_match_expected")
    entries = {item["source_id"]: item for item in freeze["selected_sources"]}
    inventory_sources = {item["source_id"]: item for item in inventory["source_scope"]["sources"]}
    handoffs = {source: verify_handoff(entry, inventory_sources[source]) for source, entry in entries.items()}
    freeze_hash = hashlib.sha256((json.dumps(freeze, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()).hexdigest()
    expected: dict[str, str | None] = {}
    facility_sources: dict[str, str] = {}
    source_counts: dict[str, dict[str, int]] = {}
    for source, handoff in handoffs.items():
        metrics = {"groups": len(handoff["representatives"]), "with_name": 0, "missing_name": 0,
                   "ambiguous_name": 0, "updated_or_would_update": 0, "already_named_unchanged": 0}
        for group, (_rep, rep_row) in handoff["representatives"].items():
            name = _facility_display_name(source, rep_row.get("normalized"), rep_row.get("source_values"))
            if name is None:
                names = {_facility_display_name(source, row.get("normalized"), row.get("source_values"))
                         for _parsed, row in handoff["groups"][group]}
                names.discard(None)
                if len(names) == 1:
                    name = next(iter(names))
                elif len(names) > 1:
                    metrics["ambiguous_name"] += 1
            if name is None:
                metrics["missing_name"] += 1
            else:
                metrics["with_name"] += 1
            facility_id = str(_uuid("facility", source, group))
            expected[facility_id] = name
            facility_sources[facility_id] = source
        source_counts[source] = metrics

    def member_snapshot(connection: Any) -> tuple[list[tuple[str, str]], str]:
        rows = connection.execute("""SELECT member.facility_id::text,member.observation_id::text
            FROM uec.release_members member WHERE member.release_id=%s
            ORDER BY member.facility_id,member.observation_id""", (freeze["release_id"],)).fetchall()
        digest = hashlib.sha256()
        for facility_id, observation_id in rows:
            digest.update((json.dumps([freeze["release_id"], str(facility_id), str(observation_id)],
                                      separators=(",", ":")) + "\n").encode())
        return [(str(row[0]), str(row[1])) for row in rows], digest.hexdigest()

    try:
        with psycopg.connect(database_url, prepare_threshold=None) as connection, connection.transaction():
            connection.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("v0-candidate-name-repair:" + freeze["release_id"],))
            if connection.execute("SELECT current_database()").fetchone()[0] != expected_database:
                raise BridgeError("connected_database_mismatch")
            release = connection.execute("SELECT status,profile,test_only,summary FROM uec.releases WHERE release_id=%s",
                                         (freeze["release_id"],)).fetchone()
            if (release is None or release[0] != "candidate" or release[1] != PROFILE or release[2] is not False
                    or not isinstance(release[3], dict) or release[3].get("candidate_only") is not True
                    or release[3].get("freeze_sha256") != freeze_hash):
                raise BridgeError("frozen_candidate_identity_mismatch")
            members, before_digest = member_snapshot(connection)
            if len(members) != len(expected) or {row[0] for row in members} != set(expected):
                raise BridgeError("frozen_membership_identity_mismatch")
            if connection.execute("SELECT count(*) FROM uec.release_members WHERE release_id=%s AND default_visible",
                                  (freeze["release_id"],)).fetchone()[0] != 0:
                raise BridgeError("candidate_member_visibility_mismatch")
            if connection.execute("SELECT count(*) FROM uec.releases WHERE release_id<>%s",
                                  (freeze["release_id"],)).fetchone()[0] != 0:
                raise BridgeError("candidate_database_has_unrelated_release")
            connection.execute("""CREATE TEMP TABLE candidate_name_repair (
                facility_id uuid PRIMARY KEY, source_id text NOT NULL, display_name text
            ) ON COMMIT DROP""")
            with connection.cursor().copy("COPY candidate_name_repair(facility_id,source_id,display_name) FROM STDIN") as copy:
                for facility_id in sorted(expected):
                    copy.write_row((facility_id, facility_sources[facility_id], expected[facility_id]))
            joined = connection.execute("""SELECT repair.facility_id::text,repair.source_id,
                    facility.canonical_name,repair.display_name
                FROM candidate_name_repair repair
                JOIN uec.release_members member ON member.facility_id=repair.facility_id
                    AND member.release_id=%s
                JOIN uec.facilities facility ON facility.facility_id=repair.facility_id
                ORDER BY repair.facility_id""", (freeze["release_id"],)).fetchall()
            if len(joined) != len(expected):
                raise BridgeError("candidate_facility_or_membership_missing")
            for _facility_id, source, current, desired in joined:
                if current is not None and str(current).strip():
                    source_counts[source]["already_named_unchanged"] += 1
                elif desired is not None:
                    source_counts[source]["updated_or_would_update"] += 1
            if apply:
                updated_rows = connection.execute("""UPDATE uec.facilities facility
                    SET canonical_name=repair.display_name
                    FROM candidate_name_repair repair
                    JOIN uec.release_members member ON member.facility_id=repair.facility_id
                        AND member.release_id=%s
                    WHERE facility.facility_id=repair.facility_id
                      AND repair.display_name IS NOT NULL
                      AND (facility.canonical_name IS NULL OR BTRIM(facility.canonical_name)='')
                    RETURNING repair.facility_id::text,repair.source_id""", (freeze["release_id"],)).fetchall()
                if len(updated_rows) != sum(item["updated_or_would_update"] for item in source_counts.values()):
                    raise BridgeError("candidate_name_update_count_mismatch")
            after_members, after_digest = member_snapshot(connection)
            if members != after_members or before_digest != after_digest:
                raise BridgeError("frozen_membership_changed")
    except psycopg.Error as error:
        failure = BridgeError("candidate_name_repair_database_operation_failed")
        failure.database_error_class = type(error).__name__
        failure.database_sqlstate = getattr(error, "sqlstate", None)
        raise failure from None
    return {"status": "applied" if apply else "dry_run", "release_id": freeze["release_id"],
            "freeze_sha256": freeze_hash, "member_count": len(members), "member_digest_before": before_digest,
            "member_digest_after": after_digest, "sources": source_counts, "public_authorized": False}


def repair_candidate_names(database_url: str, expected_database: str, freeze: dict[str, Any],
                           inventory: dict[str, Any], *, apply: bool = False) -> dict[str, Any]:
    """Run the narrowly bound r3 repair; dry-run is the default."""
    return _repair_candidate_names_checked(database_url, expected_database, freeze, inventory,
        apply=apply, required_database="uec_v0_review_r3",
        required_release_id="v0-candidate-2026-10-04-r3")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.environ.get("UEC_DATABASE_URL"))
    parser.add_argument("--expected-database", required=True)
    parser.add_argument("--freeze", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--candidate-only-ack", action="store_true")
    parser.add_argument("--append-to-v0-baseline", action="store_true",
                        help="append a non-visible candidate beside the exact approved local V0 clone")
    parser.add_argument("--append-to-release-baseline", action="store_true",
                        help="append beside the verified Oct 18/V0 baseline and explicit retained history")
    parser.add_argument("--baseline-release-id", help="exact current public release ID")
    parser.add_argument("--baseline-manifest-sha256", help="exact current public release manifest digest")
    parser.add_argument("--retained-release-id", action="append", default=[],
                        help="exact release to preserve (repeat for each retained historical release)")
    parser.add_argument("--preview-source-database-url-env", default="UEC_PREVIEW_SOURCE_DATABASE_URL",
                        help="environment variable containing the loopback country-preview database URL")
    parser.add_argument("--candidate-release-id",
                        help="required with --append-to-v0-baseline; distinct local candidate identity")
    parser.add_argument("--parent-candidate-release-id",
                        help="immediate same-family candidate predecessor; copies only its non-selected source memberships")
    parser.add_argument("--repair-names", action="store_true", help="dry-run a bounded facility-name projection repair")
    parser.add_argument("--apply-names", action="store_true", help="apply the verified name repair; requires --repair-names")
    args = parser.parse_args(argv)
    if not args.database_url:
        parser.error("--database-url or UEC_DATABASE_URL is required")
    if args.append_to_v0_baseline and args.append_to_release_baseline:
        parser.error("baseline append modes are mutually exclusive")
    if args.apply_names and not args.repair_names:
        parser.error("--apply-names requires --repair-names")
    if args.append_to_v0_baseline and args.repair_names:
        parser.error("--append-to-v0-baseline cannot be combined with --repair-names")
    if args.append_to_v0_baseline and (not isinstance(args.candidate_release_id, str)
                                       or not _SAFE_RELEASE_ID.fullmatch(args.candidate_release_id)
                                       or not args.candidate_release_id.startswith("v0-candidate-")):
        parser.error("--append-to-v0-baseline requires a v0-candidate-* --candidate-release-id")
    if not args.append_to_v0_baseline and not args.append_to_release_baseline and args.candidate_release_id:
        parser.error("--candidate-release-id requires --append-to-v0-baseline")
    if args.append_to_release_baseline:
        if args.repair_names:
            parser.error("--append-to-release-baseline cannot be combined with --repair-names")
        if args.baseline_release_id != RELEASE_BASELINE_ID or args.baseline_manifest_sha256 != RELEASE_BASELINE_MANIFEST_SHA256:
            parser.error("--append-to-release-baseline requires the exact public baseline identity")
        if tuple(sorted(args.retained_release_id)) != tuple(sorted(RETAINED_RELEASE_IDS)):
            parser.error("--append-to-release-baseline requires the exact retained release inventory")
        if not re.fullmatch(r"[A-Z_][A-Z0-9_]{0,63}", args.preview_source_database_url_env):
            parser.error("--preview-source-database-url-env must be an environment variable name")
        if (not isinstance(args.candidate_release_id, str) or not _SAFE_RELEASE_ID.fullmatch(args.candidate_release_id)
                or args.candidate_release_id.startswith("v0-candidate-")
                or args.candidate_release_id in {RELEASE_BASELINE_ID, *RETAINED_RELEASE_IDS}):
            parser.error("--append-to-release-baseline requires a distinct non-V0 --candidate-release-id")
    elif (args.baseline_release_id or args.baseline_manifest_sha256 or args.retained_release_id
          or args.preview_source_database_url_env != "UEC_PREVIEW_SOURCE_DATABASE_URL"):
        parser.error("release baseline arguments require --append-to-release-baseline")
    if args.parent_candidate_release_id and not (args.append_to_v0_baseline or args.append_to_release_baseline):
        parser.error("--parent-candidate-release-id requires an append baseline mode")
    try:
        freeze, inventory = load_freeze(args.freeze, args.inventory)
        if args.repair_names:
            report = repair_candidate_names(args.database_url, args.expected_database, freeze, inventory,
                                            apply=args.apply_names)
        else:
            if args.append_to_v0_baseline or args.append_to_release_baseline:
                # The freeze is immutable historical evidence.  Only the
                # in-memory candidate identity changes for the new local
                # correction release, and its hash is stored in that release.
                freeze = {**freeze, "release_id": args.candidate_release_id}
            report = bridge(args.database_url, args.expected_database, freeze, inventory,
                            candidate_only_ack=args.candidate_only_ack,
                            append_to_v0_baseline=args.append_to_v0_baseline,
                            parent_candidate_release_id=args.parent_candidate_release_id,
                            append_to_release_baseline=args.append_to_release_baseline,
                            baseline_release_id=args.baseline_release_id,
                            baseline_manifest_sha256=args.baseline_manifest_sha256,
                            retained_release_ids=tuple(args.retained_release_id),
                            preview_source_database_url=(os.environ.get(args.preview_source_database_url_env)
                                if args.append_to_release_baseline else None))
    except (BridgeError, OSError, ValueError) as error:
        reason = str(error) if isinstance(error, BridgeError) and re.fullmatch(r"[a-z0-9_.:-]{1,160}", str(error)) else "candidate_bridge_validation_failed"
        print(json.dumps({"status": "blocked", "reason": reason}, sort_keys=True))
        return 2
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
