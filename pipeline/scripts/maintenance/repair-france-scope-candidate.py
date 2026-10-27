#!/usr/bin/env python3
"""Append a narrowly pinned France map-scope correction to the local candidate.

Dry-run is the default. Applying appends a successor candidate with exactly
20 corrected France bindings. Existing candidates and evidence stay unchanged.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlsplit

import psycopg
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
BRIDGE_PATH = ROOT / "pipeline" / "scripts" / "maintenance" / "bridge-v0-candidates.py"
SPEC = importlib.util.spec_from_file_location("bridge_v0_candidates", BRIDGE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("candidate bridge unavailable")
BRIDGE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BRIDGE)

TARGET_DATABASE = "uec_country_release_test_20261027"
TARGET_RELEASE = "release-2026-10-27"
SUCCESSOR_RELEASE = "release-2026-10-27-r2"
FROZEN_INPUT_RELEASE = "v0-candidate-country-2026-10-27"
SOURCE_ID = "fr.georisques.icpe.animal"
EXPECTED_AFFECTED_MEMBERS = 20
SCOPE_POLICY = "france-source-coordinate-scope-v1"
CORRECTED_KEY_PREFIX = "fr-coordinate-scope-v1:"


class RepairError(ValueError):
    pass


def _is_out_of_scope_france(normalized: dict[str, Any]) -> bool:
    coordinates = normalized.get("coordinates") if isinstance(normalized.get("coordinates"), dict) else {}
    return (coordinates.get("jurisdiction_extent") == "outside-configured-france-extents"
            or normalized.get("in_default_map_scope") is False)


def _expected_targets(handoff: dict[str, Any]) -> dict[tuple[str, str], tuple[float, float]]:
    targets = {}
    for group, (parsed, raw) in handoff["representatives"].items():
        normalized = raw.get("normalized") if isinstance(raw.get("normalized"), dict) else {}
        coordinates = normalized.get("coordinates") if isinstance(normalized.get("coordinates"), dict) else None
        if (normalized.get("in_default_map_scope") is not False or not isinstance(coordinates, dict)
                or coordinates.get("jurisdiction_extent") != "outside-configured-france-extents"):
            continue
        identifier = str(parsed[0])
        try:
            latitude = float(coordinates["latitude"])
            longitude = float(coordinates["longitude"])
        except (TypeError, ValueError, KeyError):
            raise RepairError("frozen_france_out_of_scope_coordinate_missing") from None
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180) or (latitude == 0 and longitude == 0):
            raise RepairError("frozen_france_out_of_scope_coordinate_invalid")
        targets[(identifier, str(group))] = (latitude, longitude)
    if len(targets) != EXPECTED_AFFECTED_MEMBERS:
        raise RepairError("frozen_france_scope_target_count_mismatch")
    return targets


def _freeze_hash(freeze: dict[str, Any]) -> str:
    return hashlib.sha256((json.dumps(freeze, ensure_ascii=False, sort_keys=True,
                                      separators=(",", ":")) + "\n").encode()).hexdigest()


def _bind_candidate_release(freeze: dict[str, Any]) -> dict[str, Any]:
    if freeze.get("release_id") != FROZEN_INPUT_RELEASE:
        raise RepairError("repair_freeze_release_not_allowlisted")
    return {**freeze, "release_id": TARGET_RELEASE}


def _validate_dsn(database_url: str) -> None:
    parsed = urlsplit(database_url)
    routing = {key.lower() for key, _ in parse_qsl(parsed.query, keep_blank_values=True)}
    if (parsed.scheme not in {"postgres", "postgresql"}
            or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
            or parsed.path.strip("/") != TARGET_DATABASE
            or routing.intersection({"host", "hostaddr", "service", "servicefile"})):
        raise RepairError("repair_database_not_allowlisted")


def _repair_summary(*, apply: bool, release_id: str, already_corrected: int, corrected_this_run: int,
                    remaining_bad: int) -> dict[str, Any]:
    total = already_corrected + corrected_this_run
    return {"status": "applied" if apply else "dry_run", "release_id": release_id,
            "expected_members": EXPECTED_AFFECTED_MEMBERS, "already_corrected": already_corrected,
            "corrected_this_run": corrected_this_run if apply else 0,
            "total_corrected": total, "remaining_bad_members": remaining_bad,
            "public_authorized": False}


def _verified_handoff(freeze_path: Path, inventory_path: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    try:
        freeze, inventory = BRIDGE.load_freeze(freeze_path, inventory_path)
        freeze = _bind_candidate_release(freeze)
        entries = {entry["source_id"]: entry for entry in freeze["selected_sources"]}
        inventory_sources = {row["source_id"]: row for row in inventory["source_scope"]["sources"]}
        entry = entries.get(SOURCE_ID)
        inventory_source = inventory_sources.get(SOURCE_ID)
        if entry is None or inventory_source is None:
            raise RepairError("frozen_france_source_missing")
        handoff = BRIDGE.verify_handoff(entry, inventory_source)
        targets = _expected_targets(handoff)
        return freeze, inventory, entry, {"handoff": handoff, "targets": targets,
                                          "inventory_source": inventory_source}
    except BRIDGE.BridgeError as error:
        raise RepairError(f"frozen_input_invalid:{error}") from None
    except RepairError:
        raise
    except (OSError, ValueError):
        raise RepairError("frozen_input_invalid") from None


def _read_candidate_rows(connection: Any, freeze: dict[str, Any], entry: dict[str, Any],
                         handoff: dict[str, Any], targets: dict[tuple[str, str], tuple[float, float]]) -> list[tuple[Any, ...]]:
    artifact = entry["source_artifact_sha256"]
    snapshot = entry["snapshot_sha256"]
    identifiers = sorted({identifier for identifier, _ in targets})
    return connection.execute("""SELECT member.facility_id::text,member.observation_id::text,
            record.source_record_id::text,record.source_record_key,record.raw_fields,record.artifact_id::text,
            record.parsed_at,observation.observed_at,observation.observation,observation.classification,
            observation.ruleset_id,observation.rule_id,observation.classification_category,
            observation.classification_review_status,observation.default_visible,observation.optional_filter,
            observation.coordinate_method,observation.coordinate_precision,observation.coordinate_review_status,
            observation.first_observed_at,
            CASE WHEN observation.coordinate IS NULL THEN NULL ELSE ST_Y(observation.coordinate::geometry) END,
            CASE WHEN observation.coordinate IS NULL THEN NULL ELSE ST_X(observation.coordinate::geometry) END
        FROM uec.release_members member
        JOIN uec.observations observation ON observation.observation_id=member.observation_id
        JOIN uec.source_records record ON record.source_record_id=observation.source_record_id
        JOIN uec.raw_artifacts artifact ON artifact.artifact_id=record.artifact_id
        WHERE member.release_id=%s AND record.source_id=%s AND artifact.sha256=%s
          AND record.raw_fields->>'snapshot_sha256'=%s
          AND record.raw_fields->>'source_identifier'=ANY(%s)
        ORDER BY record.raw_fields->>'source_identifier',member.facility_id""",
        (TARGET_RELEASE, SOURCE_ID, artifact, snapshot, identifiers)).fetchall()


def _validate_candidate(connection: Any, freeze: dict[str, Any], inventory: dict[str, Any],
                        entry: dict[str, Any], handoff: dict[str, Any],
                        targets: dict[tuple[str, str], tuple[float, float]], *,
                        lock_candidate: bool = False) -> tuple[list[tuple[Any, ...]], list[tuple[Any, ...]]]:
    freeze_digest = _freeze_hash(freeze)
    release = connection.execute("SELECT status,profile,test_only,ruleset_version,summary FROM uec.releases WHERE release_id=%s"
                                 + (" FOR UPDATE" if lock_candidate else ""),
                                 (TARGET_RELEASE,)).fetchone()
    if (release is None or release[0] != "candidate" or release[1] != "official" or release[2] is not False
            or not isinstance(release[4], dict) or release[4].get("candidate_only") is not True
            or release[4].get("freeze_sha256") != freeze_digest
            or release[4].get("inventory_sha256") != inventory.get("inventory_sha256")):
        raise RepairError("candidate_release_identity_mismatch")
    provenance = [row for row in release[4].get("source_provenance", [])
                  if row.get("source_id") == SOURCE_ID]
    if (len(provenance) != 1 or provenance[0].get("snapshot_sha256") != entry["snapshot_sha256"]
            or provenance[0].get("source_artifact_sha256") != entry["source_artifact_sha256"]):
        raise RepairError("candidate_france_provenance_mismatch")
    artifact_rows = connection.execute("SELECT count(*) FROM uec.release_manifests WHERE release_id=%s",
                                       (TARGET_RELEASE,)).fetchone()[0]
    cohort_rows = connection.execute("SELECT count(*) FROM uec.release_cohort_review_documents WHERE release_id=%s",
                                     (TARGET_RELEASE,)).fetchone()[0]
    members, visible = connection.execute("SELECT count(*),count(*) FILTER (WHERE default_visible) "
                                          "FROM uec.release_members WHERE release_id=%s", (TARGET_RELEASE,)).fetchone()
    if artifact_rows or cohort_rows:
        raise RepairError("candidate_already_reviewed_or_manifested")
    if int(members) != 124264 or int(visible) != 0:
        raise RepairError("candidate_membership_state_mismatch")
    source = connection.execute("SELECT country_code FROM uec.sources WHERE source_id=%s", (SOURCE_ID,)).fetchone()
    if source is None or str(source[0]).strip().upper() != "FR":
        raise RepairError("candidate_france_source_country_mismatch")
    rows = _read_candidate_rows(connection, freeze, entry, handoff, targets)
    by_key: dict[tuple[str, str], tuple[Any, ...]] = {}
    for row in rows:
        observation_json = row[8] if isinstance(row[8], dict) else {}
        raw = row[4] if isinstance(row[4], dict) else {}
        key = (str(raw.get("source_identifier", "")), str(observation_json.get("source_group_key", "")))
        if key not in targets or key in by_key:
            raise RepairError("candidate_france_member_identity_mismatch")
        normalized = raw.get("normalized") if isinstance(raw.get("normalized"), dict) else {}
        coordinates = normalized.get("coordinates") if isinstance(normalized.get("coordinates"), dict) else {}
        expected_lat, expected_lon = targets[key]
        try:
            native_point_matches = (coordinates.get("latitude") is not None
                                    and coordinates.get("longitude") is not None
                                    and abs(float(coordinates["latitude"]) - expected_lat) <= 1e-8
                                    and abs(float(coordinates["longitude"]) - expected_lon) <= 1e-8)
        except (TypeError, ValueError):
            native_point_matches = False
        if (not _is_out_of_scope_france(normalized)
                or str(raw.get("snapshot_sha256")) != entry["snapshot_sha256"]
                or not native_point_matches):
            raise RepairError("candidate_france_member_evidence_mismatch")
        by_key[key] = row
    if set(by_key) != set(targets):
        raise RepairError("candidate_france_member_set_mismatch")
    remaining = []
    for key, row in by_key.items():
        corrected = (str(row[3]).startswith(CORRECTED_KEY_PREFIX)
                     and isinstance(row[8], dict)
                     and row[8].get("coordinate_scope_correction") == SCOPE_POLICY
                     and row[20] is None and row[21] is None)
        if corrected:
            continue
        expected_lat, expected_lon = targets[key]
        if row[20] is None or row[21] is None:
            raise RepairError("candidate_france_point_not_in_expected_state")
        if abs(float(row[20]) - expected_lat) > 1e-8 or abs(float(row[21]) - expected_lon) > 1e-8:
            raise RepairError("candidate_france_point_not_in_expected_state")
        remaining.append(row)
    return list(by_key.values()), remaining


def _append_corrected_lineage(connection: Any, row: tuple[Any, ...], snapshot_sha256: str) -> str:
    facility_id, old_observation_id, old_record_id = row[0], row[1], row[2]
    source_record_key = f"{CORRECTED_KEY_PREFIX}{snapshot_sha256}:{row[4]['source_identifier']}"
    raw_fields = dict(row[4])
    raw_fields["coordinate_scope_projection"] = SCOPE_POLICY
    connection.execute("""INSERT INTO uec.source_records
        (source_id,source_record_key,artifact_id,raw_fields,parsed_at)
        VALUES (%s,%s,%s,%s,%s) ON CONFLICT (source_id,source_record_key,artifact_id) DO NOTHING""",
        (SOURCE_ID, source_record_key, row[5], Jsonb(raw_fields), row[6]))
    new_record = connection.execute("""SELECT source_record_id::text,raw_fields FROM uec.source_records
        WHERE source_id=%s AND source_record_key=%s AND artifact_id=%s""",
        (SOURCE_ID, source_record_key, row[5])).fetchone()
    if new_record is None or new_record[1] != raw_fields:
        raise RepairError("corrected_source_record_conflict")

    corrected_observation = dict(row[8])
    corrected_observation.pop("display_location", None)
    corrected_observation["display_location"] = None
    corrected_observation["coordinate_scope_correction"] = SCOPE_POLICY
    connection.execute("""INSERT INTO uec.observations
        (facility_id,source_record_id,observed_at,observation,classification,ruleset_id,rule_id,
         classification_category,classification_review_status,default_visible,optional_filter,
         coordinate,coordinate_method,coordinate_precision,coordinate_review_status,first_observed_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,false,%s,NULL,NULL,NULL,%s,%s)
        ON CONFLICT (facility_id,source_record_id,observed_at) DO NOTHING""",
        (facility_id, new_record[0], row[7], Jsonb(corrected_observation), Jsonb(row[9]), row[10], row[11],
         row[12], row[13], row[15], row[18], row[19]))
    new_observation = connection.execute("""SELECT observation_id::text,observation,classification,
            classification_category,default_visible,coordinate_method,coordinate_precision,
            CASE WHEN coordinate IS NULL THEN NULL ELSE ST_Y(coordinate::geometry) END,
            CASE WHEN coordinate IS NULL THEN NULL ELSE ST_X(coordinate::geometry) END
        FROM uec.observations WHERE facility_id=%s AND source_record_id=%s AND observed_at=%s""",
        (facility_id, new_record[0], row[7])).fetchone()
    if (new_observation is None or new_observation[1] != corrected_observation
            or new_observation[2] != row[9] or new_observation[3] != row[12]
            or new_observation[4] is not False or new_observation[5] is not None
            or new_observation[6] is not None or new_observation[7] is not None
            or new_observation[8] is not None):
        raise RepairError("corrected_observation_conflict")

    old_set = connection.execute("""SELECT assignment_set_id::text,source_id,artifact_id::text,
            taxonomy_version,crosswalk_version,ruleset_version,display_category
        FROM uec.observation_taxonomy_assignment_sets WHERE observation_id=%s
        ORDER BY created_at DESC,assignment_set_id DESC LIMIT 1""", (old_observation_id,)).fetchone()
    if old_set is None or str(old_set[1]) != SOURCE_ID or str(old_set[2]) != str(row[5]):
        raise RepairError("source_taxonomy_lineage_missing")
    connection.execute("""INSERT INTO uec.observation_taxonomy_assignment_sets
        (observation_id,source_record_id,source_id,artifact_id,taxonomy_version,crosswalk_version,ruleset_version,display_category)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (observation_id,taxonomy_version,crosswalk_version,ruleset_version) DO NOTHING
        """,
        (new_observation[0], new_record[0], SOURCE_ID, row[5], old_set[3], old_set[4], old_set[5], old_set[6]))
    target_set = connection.execute("""SELECT assignment_set_id::text,source_record_id::text,source_id,
            artifact_id::text,taxonomy_version,crosswalk_version,ruleset_version,display_category
        FROM uec.observation_taxonomy_assignment_sets WHERE observation_id=%s AND taxonomy_version=%s
          AND crosswalk_version=%s AND ruleset_version=%s""",
        (new_observation[0], old_set[3], old_set[4], old_set[5])).fetchone()
    expected_set = (str(new_record[0]), SOURCE_ID, str(row[5]), old_set[3], old_set[4], old_set[5], old_set[6])
    if target_set is None or tuple(str(value) for value in target_set[1:]) != tuple(str(value) for value in expected_set):
        raise RepairError("corrected_taxonomy_set_conflict")
    new_set_id = target_set[0]
    connection.execute("""INSERT INTO uec.observation_taxonomy_assignments
        (assignment_set_id,assignment_ordinal,primary_key,leaf_key,leaf_label,source_code_reference,
         source_label_reference,source_code,source_label,mapping_method,mapping_status)
        SELECT %s,assignment_ordinal,primary_key,leaf_key,leaf_label,source_code_reference,
               source_label_reference,source_code,source_label,mapping_method,mapping_status
        FROM uec.observation_taxonomy_assignments WHERE assignment_set_id=%s
        ON CONFLICT DO NOTHING""", (new_set_id, old_set[0]))
    mismatch = connection.execute("""SELECT count(*) FROM (
        (SELECT assignment_ordinal,primary_key,leaf_key,leaf_label,source_code_reference,source_label_reference,
                source_code,source_label,mapping_method,mapping_status
         FROM uec.observation_taxonomy_assignments WHERE assignment_set_id=%s
         EXCEPT
         SELECT assignment_ordinal,primary_key,leaf_key,leaf_label,source_code_reference,source_label_reference,
                source_code,source_label,mapping_method,mapping_status
         FROM uec.observation_taxonomy_assignments WHERE assignment_set_id=%s)
        UNION ALL
        (SELECT assignment_ordinal,primary_key,leaf_key,leaf_label,source_code_reference,source_label_reference,
                source_code,source_label,mapping_method,mapping_status
         FROM uec.observation_taxonomy_assignments WHERE assignment_set_id=%s
         EXCEPT
         SELECT assignment_ordinal,primary_key,leaf_key,leaf_label,source_code_reference,source_label_reference,
                source_code,source_label,mapping_method,mapping_status
         FROM uec.observation_taxonomy_assignments WHERE assignment_set_id=%s)
    ) differences""", (old_set[0], new_set_id, new_set_id, old_set[0])).fetchone()[0]
    if int(mismatch):
        raise RepairError("corrected_taxonomy_lineage_conflict")
    connection.execute("""INSERT INTO uec.facility_source_links
        (facility_id,source_record_id,match_method,review_status)
        VALUES (%s,%s,'source_native_group_key','automatic') ON CONFLICT DO NOTHING""",
        (facility_id, new_record[0]))
    return new_observation[0]


def _ensure_successor_release(connection: Any, original: tuple[Any, ...],
                              replacement_observations: dict[str, str], *, create: bool) -> None:
    summary = dict(original[4])
    summary["supersedes_release_id"] = TARGET_RELEASE
    summary["coordinate_scope_correction"] = SCOPE_POLICY
    summary["coordinate_scope_corrected_member_count"] = EXPECTED_AFFECTED_MEMBERS
    if create:
        connection.execute("""INSERT INTO uec.releases(release_id,status,ruleset_version,summary,profile,test_only)
            VALUES (%s,'candidate',%s,%s,%s,false) ON CONFLICT (release_id) DO NOTHING""",
            (SUCCESSOR_RELEASE, original[3], Jsonb(summary), original[1]))
    target = connection.execute("SELECT status,profile,test_only,summary FROM uec.releases WHERE release_id=%s"
                                + (" FOR UPDATE" if create else ""),
                                (SUCCESSOR_RELEASE,)).fetchone()
    if (target is None or target[0] != "candidate" or target[1] != original[1] or target[2] is not False
            or target[3] != summary):
        raise RepairError("successor_release_identity_conflict")
    successor_evidence = connection.execute("""SELECT
          (SELECT count(*) FROM uec.release_manifests WHERE release_id=%s),
          (SELECT count(*) FROM uec.release_cohort_review_documents WHERE release_id=%s)""",
        (SUCCESSOR_RELEASE, SUCCESSOR_RELEASE)).fetchone()
    if any(int(value) for value in successor_evidence):
        raise RepairError("successor_release_already_reviewed_or_manifested")
    old_count = connection.execute("SELECT count(*) FROM uec.release_members WHERE release_id=%s",
                                   (TARGET_RELEASE,)).fetchone()[0]
    if int(old_count) != 124264:
        raise RepairError("successor_source_membership_mismatch")
    replacements_by_old = replacement_observations
    if len(replacements_by_old) != EXPECTED_AFFECTED_MEMBERS:
        raise RepairError("successor_correction_binding_count_mismatch")
    values_sql = ",".join("(%s::uuid,%s::uuid)" for _ in replacements_by_old)
    insert_sql = """WITH replacements(old_observation_id,new_observation_id) AS (VALUES """ + values_sql + """)
        INSERT INTO uec.release_members(release_id,facility_id,observation_id,default_visible)
        SELECT %s,old.facility_id,COALESCE(replacements.new_observation_id,old.observation_id),old.default_visible
        FROM uec.release_members old LEFT JOIN replacements ON replacements.old_observation_id=old.observation_id
        WHERE old.release_id=%s ON CONFLICT (release_id,facility_id) DO NOTHING"""
    insert_params = [value for pair in replacements_by_old.items() for value in pair]
    insert_params.extend((SUCCESSOR_RELEASE, TARGET_RELEASE))
    if create:
        connection.execute(insert_sql, insert_params)
    expected_count = int(old_count)
    actual_count = connection.execute("SELECT count(*) FROM uec.release_members WHERE release_id=%s",
                                      (SUCCESSOR_RELEASE,)).fetchone()[0]
    mismatch_query = """WITH replacements(old_observation_id,new_observation_id) AS (VALUES """ + ",".join(
        "(%s::uuid,%s::uuid)" for _ in replacements_by_old) + """), expected AS (
        SELECT old.facility_id,COALESCE(replacements.new_observation_id,old.observation_id) observation_id,
               old.default_visible
        FROM uec.release_members old LEFT JOIN replacements ON replacements.old_observation_id=old.observation_id
        WHERE old.release_id=%s
    ), differences AS (
        (SELECT facility_id,observation_id,default_visible FROM expected EXCEPT
         SELECT facility_id,observation_id,default_visible FROM uec.release_members WHERE release_id=%s)
        UNION ALL
        (SELECT facility_id,observation_id,default_visible FROM uec.release_members WHERE release_id=%s EXCEPT
         SELECT facility_id,observation_id,default_visible FROM expected)
    ) SELECT count(*) FROM differences"""
    mismatch_params = [value for pair in replacements_by_old.items() for value in pair]
    mismatch_params.extend((TARGET_RELEASE, SUCCESSOR_RELEASE, SUCCESSOR_RELEASE))
    mismatches = connection.execute(mismatch_query, mismatch_params).fetchone()[0]
    if int(actual_count) != expected_count or int(mismatches):
        raise RepairError("successor_release_membership_conflict")


def _successor_replacements(connection: Any, members: list[tuple[Any, ...]], snapshot_sha256: str) -> dict[str, str]:
    old_by_facility = {str(row[0]): str(row[1]) for row in members}
    corrected_rows = connection.execute("""SELECT observation.facility_id::text,observation.observation_id::text
        FROM uec.observations observation JOIN uec.source_records record USING (source_record_id)
        WHERE record.source_id=%s AND record.source_record_key LIKE %s
          AND observation.observation->>'coordinate_scope_correction'=%s""",
        (SOURCE_ID, CORRECTED_KEY_PREFIX + snapshot_sha256 + ":%", SCOPE_POLICY)).fetchall()
    result = {}
    for facility_id, corrected_id in corrected_rows:
        facility_id = str(facility_id)
        if facility_id not in old_by_facility:
            raise RepairError("successor_corrected_facility_unexpected")
        result[old_by_facility[facility_id]] = str(corrected_id)
    return result


def repair(database_url: str, freeze_path: Path, inventory_path: Path, *, apply: bool = False) -> dict[str, Any]:
    _validate_dsn(database_url)
    freeze, inventory, entry, context = _verified_handoff(freeze_path, inventory_path)
    handoff, targets = context["handoff"], context["targets"]
    try:
        with psycopg.connect(database_url, prepare_threshold=None) as connection, connection.transaction():
            if apply:
                connection.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
                connection.execute("SELECT pg_advisory_xact_lock(hashtext(%s))",
                                   ("v0-candidate-bridge:" + TARGET_RELEASE,))
            else:
                connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            if connection.execute("SELECT current_database()").fetchone()[0] != TARGET_DATABASE:
                raise RepairError("connected_database_mismatch")
            members, remaining = _validate_candidate(connection, freeze, inventory, entry, handoff, targets,
                                                      lock_candidate=apply)
            already_corrected = EXPECTED_AFFECTED_MEMBERS - len(remaining)
            original_release = connection.execute("SELECT status,profile,test_only,ruleset_version,summary "
                                                  "FROM uec.releases WHERE release_id=%s",
                                                  (TARGET_RELEASE,)).fetchone()
            if original_release is None:
                raise RepairError("candidate_release_identity_mismatch")
            public_before = {relation: int(connection.execute(f"SELECT count(*) FROM {relation}").fetchone()[0])
                             for relation in BRIDGE.PUBLIC_PROJECTION_RELATIONS
                             if connection.execute("SELECT to_regclass(%s)", (relation,)).fetchone()[0] is not None}
            successor_exists = connection.execute("SELECT 1 FROM uec.releases WHERE release_id=%s",
                                                   (SUCCESSOR_RELEASE,)).fetchone() is not None
            successor_preexisting = successor_exists
            replacements = _successor_replacements(connection, members, entry["snapshot_sha256"]) if successor_exists else {}
            if apply and not successor_exists:
                for row in remaining:
                    replacements[str(row[1])] = _append_corrected_lineage(connection, row, entry["snapshot_sha256"])
                _ensure_successor_release(connection, original_release, replacements, create=True)
                successor_exists = True
            elif successor_exists:
                _ensure_successor_release(connection, original_release, replacements, create=False)
            corrected_count = connection.execute("""SELECT count(*)
                FROM uec.release_members member
                JOIN uec.observations observation ON observation.observation_id=member.observation_id
                JOIN uec.source_records record ON record.source_record_id=observation.source_record_id
                WHERE member.release_id=%s AND record.source_id=%s
                  AND record.source_record_key LIKE %s
                  AND observation.observation->>'coordinate_scope_correction'=%s
                  AND observation.coordinate IS NULL""",
                (SUCCESSOR_RELEASE, SOURCE_ID, CORRECTED_KEY_PREFIX + entry["snapshot_sha256"] + ":%", SCOPE_POLICY)).fetchone()[0] if successor_exists else 0
            remaining_bad = connection.execute("""SELECT count(*)
                FROM uec.release_members member
                JOIN uec.observations observation ON observation.observation_id=member.observation_id
                JOIN uec.source_records record ON record.source_record_id=observation.source_record_id
                JOIN uec.raw_artifacts artifact ON artifact.artifact_id=record.artifact_id
                WHERE member.release_id=%s AND record.source_id=%s AND artifact.sha256=%s
                  AND record.raw_fields->>'snapshot_sha256'=%s
                  AND record.raw_fields->>'coordinate_scope_projection' IS NULL
                  AND record.raw_fields->'normalized'->>'in_default_map_scope'='false'
                  AND record.raw_fields->'normalized'->'coordinates'->>'jurisdiction_extent'='outside-configured-france-extents'
                  AND observation.coordinate IS NOT NULL""",
                (SUCCESSOR_RELEASE, SOURCE_ID, entry["source_artifact_sha256"], entry["snapshot_sha256"])).fetchone()[0] if successor_exists else 0
            if successor_exists and (int(corrected_count) != EXPECTED_AFFECTED_MEMBERS or int(remaining_bad) != 0):
                raise RepairError("candidate_scope_repair_reconciliation_failed")
            if not successor_exists and (already_corrected + len(remaining) != EXPECTED_AFFECTED_MEMBERS):
                raise RepairError("candidate_scope_repair_preflight_count_mismatch")
            public_after = {relation: int(connection.execute(f"SELECT count(*) FROM {relation}").fetchone()[0])
                            for relation in public_before}
            if public_after != public_before:
                raise RepairError("public_projection_changed")
    except psycopg.Error as error:
        failure = RepairError("candidate_scope_repair_database_operation_failed")
        failure.database_error_class = type(error).__name__
        failure.database_sqlstate = getattr(error, "sqlstate", None)
        raise failure from None
    except RepairError:
        raise
    except Exception:
        raise RepairError("candidate_scope_repair_validation_failed") from None
    if successor_exists:
        return _repair_summary(apply=apply, release_id=SUCCESSOR_RELEASE,
                               already_corrected=EXPECTED_AFFECTED_MEMBERS if successor_preexisting else 0,
                               corrected_this_run=len(remaining) if apply and not successor_preexisting else 0,
                               remaining_bad=int(remaining_bad))
    return _repair_summary(apply=False, release_id=TARGET_RELEASE, already_corrected=0,
                           corrected_this_run=0, remaining_bad=EXPECTED_AFFECTED_MEMBERS)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.environ.get("UEC_DATABASE_URL"), required=False)
    parser.add_argument("--freeze", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--apply", action="store_true", help="apply the exact 20-member candidate-only correction")
    args = parser.parse_args(argv)
    if not args.database_url:
        parser.error("--database-url or UEC_DATABASE_URL is required")
    try:
        report = repair(args.database_url, args.freeze, args.inventory, apply=args.apply)
    except RepairError as error:
        report = {"status": "blocked", "reason_code": str(error)}
        if getattr(error, "database_sqlstate", None):
            report["database_sqlstate"] = error.database_sqlstate
            report["database_error_class"] = error.database_error_class
        print(json.dumps(report, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
