#!/usr/bin/env python3
"""Build a repeatable, read-only, row-free inventory of retained v0 candidates.

This reports the latest imported private-preview snapshot for each source. It
does not create a UEC release, publication decision, or public projection.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit

import psycopg


SCHEMA_VERSION = "release-candidate-inventory-v1"
_HASH = re.compile(r"^[0-9a-f]{64}$")
_SAFE_CODE = re.compile(r"^[a-z][a-z0-9_:-]{0,63}$")
_SAFE_PROVIDER = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_FORBIDDEN_OUTPUT_KEYS = frozenset({
    "name", "canonical_name", "address", "street_address", "latitude", "longitude",
    "coordinates", "source_identifier", "source_record_key", "source_record_id",
    "candidate_id", "facility_id", "observation_id", "raw_fields", "payload",
    "query", "response", "credentials", "password", "secret", "database_url",
})

REQUIRED_RELATIONS = (
    "real_preview.source_preview_runs",
    "real_preview.source_manifests",
    "real_preview.observations",
    "real_preview.candidates",
    "real_preview.candidate_enrichment_reconciliation",
    "real_preview.candidate_taxonomy_assignment_sets",
    "real_preview.candidate_taxonomy_assignments",
    "real_preview.taxonomy_crosswalks",
    "uec.releases",
    "uec.release_members",
    "uec.release_manifests",
)
OPTIONAL_RELATIONS = (
    "real_preview.geocode_targets",
    "real_preview.geocode_display_evidence",
    "uec.geocode_jobs",
    "uec.geocode_results",
    "uec.schema_migrations",
    "uec.public_discovery_read_model_rows",
    "uec.map_facilities_public_discovery",
    "uec.map_facilities_public",
    "uec.graph_connection_edges",
    "uec.graph_public_relationships",
    "uec.graph_public_claims",
)

_SOURCE_COLUMNS = (
    "source_id", "snapshot_sha256", "source_artifact_sha256", "normalized_sha256",
    "source_url", "retrieved_at", "adapter_version", "schema_version", "input_count",
    "accepted_count", "quarantined_count", "out_of_scope_count", "imported_observation_count",
    "facility_count", "numeric_coordinate_count", "coarse_placeable_count", "unmapped_count",
    "api_listable_count", "map_visible_count", "idempotent_replay", "public_rows",
    "runtime_details", "physical_observation_count", "physical_candidate_count",
    "source_coordinate_candidates", "coarse_location_candidates", "display_coordinate_candidates",
    "unmapped_observations", "manifest_artifact_sha256", "manifest_normalized_sha256",
    "manifest_normalized_rows", "manifest_source_url", "manifest_retrieved_at",
    "manifest_code_version", "manifest_config_version",
)

_SOURCE_SQL = """
-- release-candidate-inventory: latest private source snapshots and physical counts
WITH latest AS (
    SELECT DISTINCT ON (source_id) *
    FROM real_preview.source_preview_runs
    ORDER BY source_id, created_at DESC, run_id DESC
)
SELECT run.source_id, run.snapshot_sha256, run.source_artifact_sha256,
       run.normalized_sha256, run.source_url, run.retrieved_at,
       run.adapter_version, run.schema_version, run.input_count,
       run.accepted_count, run.quarantined_count, run.out_of_scope_count,
       run.imported_observation_count, run.facility_count,
       run.numeric_coordinate_count, run.coarse_placeable_count,
       run.unmapped_count, run.api_listable_count, run.map_visible_count,
       run.idempotent_replay, run.public_rows, run.runtime_details,
       (SELECT count(*) FROM real_preview.observations obs
         WHERE obs.source_id = run.source_id AND obs.snapshot_sha256 = run.snapshot_sha256),
       (SELECT count(*) FROM real_preview.candidates candidate
         WHERE candidate.source_id = run.source_id AND candidate.snapshot_sha256 = run.snapshot_sha256),
       (SELECT count(*) FROM real_preview.candidates candidate
         WHERE candidate.source_id = run.source_id AND candidate.snapshot_sha256 = run.snapshot_sha256
           AND candidate.location_class = 'numeric_source_coordinate'),
       (SELECT count(*) FROM real_preview.candidates candidate
         WHERE candidate.source_id = run.source_id AND candidate.snapshot_sha256 = run.snapshot_sha256
           AND candidate.location_class = 'city_postal'),
       (SELECT count(*) FROM real_preview.candidates candidate
         WHERE candidate.source_id = run.source_id AND candidate.snapshot_sha256 = run.snapshot_sha256
           AND candidate.display_latitude IS NOT NULL AND candidate.display_longitude IS NOT NULL),
       (SELECT count(*) FROM real_preview.observations obs
         WHERE obs.source_id = run.source_id AND obs.snapshot_sha256 = run.snapshot_sha256
           AND obs.location_class = 'unmapped_private_observation'),
       manifest.source_artifact_sha256, manifest.normalized_sha256,
       manifest.normalized_rows, manifest.source_url, manifest.retrieved_at,
       manifest.code_version, manifest.config_version
FROM latest run
LEFT JOIN real_preview.source_manifests manifest
  ON manifest.snapshot_sha256 = run.snapshot_sha256 AND manifest.source_id = run.source_id
ORDER BY run.source_id
"""

_RELATION_SQL = """
-- release-candidate-inventory: relation availability
SELECT relation_name, to_regclass(relation_name) IS NOT NULL
FROM unnest(%s::text[]) AS relation_name
"""

_TAXONOMY_SQL = """
-- release-candidate-inventory: taxonomy coverage by version and display class
WITH latest AS (
    SELECT DISTINCT ON (source_id) source_id, snapshot_sha256
    FROM real_preview.source_preview_runs
    ORDER BY source_id, created_at DESC, run_id DESC
)
SELECT sets.source_id, sets.taxonomy_version, sets.crosswalk_version,
       sets.ruleset_version, sets.display_category,
       count(DISTINCT sets.candidate_id), count(assignments.assignment_ordinal)
FROM real_preview.candidate_taxonomy_assignment_sets sets
JOIN latest USING (source_id, snapshot_sha256)
LEFT JOIN real_preview.candidate_taxonomy_assignments assignments USING (assignment_set_id)
GROUP BY sets.source_id, sets.taxonomy_version, sets.crosswalk_version,
         sets.ruleset_version, sets.display_category
ORDER BY sets.source_id, sets.taxonomy_version, sets.crosswalk_version,
         sets.ruleset_version, sets.display_category
"""

_TAXONOMY_MAPPING_SQL = """
-- release-candidate-inventory: taxonomy mapping status and method aggregates
WITH latest AS (
    SELECT DISTINCT ON (source_id) source_id, snapshot_sha256
    FROM real_preview.source_preview_runs
    ORDER BY source_id, created_at DESC, run_id DESC
)
SELECT sets.source_id, sets.taxonomy_version, sets.crosswalk_version,
       sets.ruleset_version, assignments.primary_key,
       assignments.mapping_method, assignments.mapping_status,
       count(*)
FROM real_preview.candidate_taxonomy_assignment_sets sets
JOIN latest USING (source_id, snapshot_sha256)
JOIN real_preview.candidate_taxonomy_assignments assignments USING (assignment_set_id)
GROUP BY sets.source_id, sets.taxonomy_version, sets.crosswalk_version,
         sets.ruleset_version, assignments.primary_key,
         assignments.mapping_method, assignments.mapping_status
ORDER BY sets.source_id, sets.taxonomy_version, sets.crosswalk_version,
         sets.ruleset_version, assignments.primary_key,
         assignments.mapping_method, assignments.mapping_status
"""

_CROSSWALKS_SQL = """
-- release-candidate-inventory: crosswalk hashes and rule totals only
WITH latest AS (
    SELECT DISTINCT ON (source_id) source_id
    FROM real_preview.source_preview_runs
    ORDER BY source_id, created_at DESC, run_id DESC
)
SELECT crosswalk.source_id, crosswalk.taxonomy_version,
       crosswalk.crosswalk_version, crosswalk.ruleset_version,
       crosswalk.definition_sha256, jsonb_array_length(crosswalk.definition->'rules')
FROM real_preview.taxonomy_crosswalks crosswalk
JOIN latest USING (source_id)
ORDER BY crosswalk.source_id, crosswalk.taxonomy_version,
         crosswalk.crosswalk_version, crosswalk.ruleset_version
"""

_GEOGRAPHY_SQL = """
-- release-candidate-inventory: source geometry origin counts, without points
WITH latest AS (
    SELECT DISTINCT ON (source_id) source_id, snapshot_sha256
    FROM real_preview.source_preview_runs
    ORDER BY source_id, created_at DESC, run_id DESC
), categorized AS (
    SELECT candidate.source_id,
           CASE
             WHEN display.display_latitude IS NOT NULL
                  AND candidate.coordinate_method IN ('address_geocode', 'geoapify_forward') THEN 'provider_derived'
             WHEN display.display_latitude IS NOT NULL
                  AND candidate.location_class = 'numeric_source_coordinate' THEN 'source_coordinate'
             WHEN display.display_latitude IS NOT NULL
                  AND candidate.location_class = 'city_postal' THEN 'coarse_reference'
             WHEN display.display_latitude IS NOT NULL THEN 'other_display_point'
             WHEN candidate.default_map_scope
                  AND candidate.location_class = 'numeric_source_coordinate'
                  AND candidate.latitude IS NOT NULL AND candidate.longitude IS NOT NULL THEN 'source_coordinate_fallback'
             WHEN display.display_latitude IS NULL THEN 'no_display_point'
             ELSE 'other_or_unrecognized'
           END AS geometry_source,
           display.display_latitude,
           (display.display_latitude IS NOT NULL AND display.display_longitude IS NOT NULL)
             OR (candidate.default_map_scope
                 AND candidate.location_class = 'numeric_source_coordinate'
                 AND candidate.latitude IS NOT NULL AND candidate.longitude IS NOT NULL) AS served_by_private_map
    FROM real_preview.candidates candidate
    JOIN real_preview.candidate_display display
      ON display.candidate_id = candidate.candidate_id
    JOIN latest
      ON latest.source_id = candidate.source_id
     AND latest.snapshot_sha256 = candidate.snapshot_sha256
)
SELECT source_id, geometry_source, count(*),
       count(*) FILTER (WHERE display_latitude IS NOT NULL),
       count(*) FILTER (WHERE served_by_private_map)
FROM categorized
GROUP BY source_id, geometry_source
ORDER BY source_id, geometry_source
"""

_ENRICHMENT_SQL = """
-- release-candidate-inventory: current source-private enrichment reason counts
WITH latest AS (
    SELECT DISTINCT ON (source_id) source_id, snapshot_sha256
    FROM real_preview.source_preview_runs
    ORDER BY source_id, created_at DESC, run_id DESC
)
SELECT state.source_id, state.state_code, state.reason_code, count(*)
FROM real_preview.candidate_enrichment_reconciliation state
JOIN latest USING (source_id, snapshot_sha256)
GROUP BY state.source_id, state.state_code, state.reason_code
ORDER BY state.source_id, state.state_code, state.reason_code
"""

_PROVIDER_SQL = """
-- release-candidate-inventory: provider/result aggregates, no query/response
WITH latest AS (
    SELECT DISTINCT ON (source_id) source_id, snapshot_sha256
    FROM real_preview.source_preview_runs
    ORDER BY source_id, created_at DESC, run_id DESC
)
SELECT candidate.source_id, job.provider_id, result.status, result.precision,
       count(DISTINCT candidate.candidate_id)
FROM real_preview.candidates candidate
JOIN latest USING (source_id, snapshot_sha256)
JOIN real_preview.geocode_targets target USING (candidate_id)
JOIN uec.geocode_jobs job USING (job_id)
JOIN uec.geocode_results result USING (source_record_id)
GROUP BY candidate.source_id, job.provider_id, result.status, result.precision
ORDER BY candidate.source_id, job.provider_id, result.status, result.precision
"""

_DISPLAY_PROVIDER_SQL = """
-- release-candidate-inventory: accepted display evidence provider aggregates
WITH latest AS (
    SELECT DISTINCT ON (source_id) source_id, snapshot_sha256
    FROM real_preview.source_preview_runs
    ORDER BY source_id, created_at DESC, run_id DESC
)
SELECT candidate.source_id, result.provider_id, result.status, evidence.display_precision,
       count(DISTINCT candidate.candidate_id)
FROM real_preview.candidates candidate
JOIN latest USING (source_id, snapshot_sha256)
JOIN real_preview.geocode_display_evidence evidence USING (candidate_id)
JOIN uec.geocode_results result USING (geocode_result_id)
GROUP BY candidate.source_id, result.provider_id, result.status, evidence.display_precision
ORDER BY candidate.source_id, result.provider_id, result.status, evidence.display_precision
"""

_RELEASES_SQL = """
-- release-candidate-inventory: release counts only, no IDs or metadata payloads
SELECT release.status, release.profile, count(DISTINCT release.release_id),
       count(DISTINCT member.release_id), count(member.observation_id)
FROM uec.releases release
LEFT JOIN uec.release_members member USING (release_id)
GROUP BY release.status, release.profile
ORDER BY release.status, release.profile
"""

_RELEASE_TOTALS_SQL = """
-- release-candidate-inventory: physical release and manifest totals
SELECT (SELECT count(*) FROM uec.releases),
       (SELECT count(*) FROM uec.release_members),
       (SELECT count(*) FROM uec.release_manifests),
       (SELECT count(*) FROM uec.releases WHERE status = 'promoted')
"""

_PRIVATE_GRAPH_SQL = """
-- release-candidate-inventory: private graph counts only
SELECT connection_type, publication_status, storage_state, count(*)
FROM uec.graph_connection_edges
GROUP BY connection_type, publication_status, storage_state
ORDER BY connection_type, publication_status, storage_state
"""

_MIGRATION_SQL = """
-- release-candidate-inventory: migration ledger metadata
SELECT count(*), max(version) FROM uec.schema_migrations
"""

_SAFE_PUBLIC_RELATIONS = (
    "uec.map_facilities_public_discovery",
    "uec.map_facilities_public",
    "uec.graph_public_relationships",
    "uec.graph_public_claims",
    "uec.public_discovery_read_model_rows",
    "uec.map_facilities_display_history",
    "uec.map_facilities_public_discovery_read_model",
)


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _safe_count(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"invalid nonnegative count in {field}")
    return value


def _safe_hash(value: Any, field: str) -> str:
    text = str(value or "").strip().lower()
    if not _HASH.fullmatch(text):
        raise ValueError(f"invalid digest in {field}")
    return text


def _safe_dimension(value: Any, field: str) -> str:
    text = str(value or "")
    if not _SAFE_PROVIDER.fullmatch(text):
        return "other_or_unrecognized"
    return text


def _assert_row_free(value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).casefold() in _FORBIDDEN_OUTPUT_KEYS:
                raise ValueError(f"private payload field cannot be written to inventory: {key}")
            _assert_row_free(child)
    elif isinstance(value, list):
        for child in value:
            _assert_row_free(child)


def _safe_source_url(value: Any) -> str:
    parsed = urlsplit(str(value or ""))
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("source provenance URL is not a public HTTP(S) URL")
    return parsed.hostname.lower()


def _safe_reason_counts(details: Any) -> dict[str, int]:
    details = details if isinstance(details, dict) else {}
    values = details.get("quarantine_reasons")
    if not isinstance(values, dict):
        return {}
    result: dict[str, int] = {}
    for key, value in values.items():
        if not _SAFE_CODE.fullmatch(str(key)):
            continue
        try:
            result[str(key)] = _safe_count(value, "quarantine_reasons")
        except ValueError:
            continue
    return dict(sorted(result.items()))


def _safe_source_flags(details: Any) -> dict[str, Any]:
    details = details if isinstance(details, dict) else {}
    allowed = {"fresh_live_run", "offline_handoff", "processing_mode", "acquisition_classification"}
    flags = {key: value for key, value in details.items() if key in allowed}
    if "fresh_live_run" in flags and not isinstance(flags["fresh_live_run"], bool):
        flags.pop("fresh_live_run")
    if "offline_handoff" in flags and not isinstance(flags["offline_handoff"], bool):
        flags.pop("offline_handoff")
    for key in ("processing_mode", "acquisition_classification"):
        if key in flags and (not isinstance(flags[key], str) or not _SAFE_CODE.fullmatch(flags[key])):
            flags.pop(key)
    return dict(sorted(flags.items()))


def _safe_exclusion_details(details: Any) -> dict[str, Any]:
    details = details if isinstance(details, dict) else {}
    source = details.get("source_specific_counts")
    source = source if isinstance(source, dict) else {}
    numeric_keys = (
        "accepted_rows", "rejected_rows", "out_of_scope_rows",
        "quarantined_coordinate_claims", "graph_relationships_emitted",
    )
    counts: dict[str, Any] = {}
    for key in numeric_keys:
        value = source.get(key)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            counts[key] = value
    reason_map = source.get("coordinate_quarantine_reasons")
    if isinstance(reason_map, dict):
        safe_reasons = {
            str(key): value for key, value in reason_map.items()
            if _SAFE_CODE.fullmatch(str(key)) and isinstance(value, int)
            and not isinstance(value, bool) and value >= 0
        }
        if safe_reasons:
            counts["coordinate_quarantine_reason_counts"] = dict(sorted(safe_reasons.items()))
    return counts


def _typed_rows(connection: Any, query: str, columns: Iterable[str], parameters: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    names = tuple(columns)
    result = connection.execute(query, parameters).fetchall()
    return [dict(zip(names, row, strict=True)) for row in result]


def _counter_rows(rows: list[dict[str, Any]], *, keys: tuple[str, ...], count_key: str) -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = {}
    for row in rows:
        source = str(row["source_id"])
        key = ":".join(str(row[name]) for name in keys)
        result.setdefault(source, {})[key] = _safe_count(row[count_key], count_key)
    return {source: dict(sorted(values.items())) for source, values in sorted(result.items())}


def _source_report(row: dict[str, Any], *, taxonomy: list[dict[str, Any]], crosswalks: list[dict[str, Any]],
                   geography: dict[str, dict[str, int]], enrichment: dict[str, dict[str, int]],
                   providers: dict[str, dict[str, int]], display_providers: dict[str, dict[str, int]]) -> dict[str, Any]:
    source_id = str(row["source_id"])
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{1,127}", source_id):
        raise ValueError("source ID is malformed")
    source_hash = _safe_hash(row["source_artifact_sha256"], "source_artifact_sha256")
    normalized_hash = _safe_hash(row["normalized_sha256"], "normalized_sha256")
    snapshot_hash = _safe_hash(row["snapshot_sha256"], "snapshot_sha256")
    counts = {key: _safe_count(row[key], key) for key in (
        "input_count", "accepted_count", "quarantined_count", "out_of_scope_count",
        "imported_observation_count", "facility_count", "numeric_coordinate_count",
        "coarse_placeable_count", "unmapped_count", "api_listable_count", "map_visible_count",
        "public_rows", "physical_observation_count", "physical_candidate_count",
        "source_coordinate_candidates", "coarse_location_candidates",
        "display_coordinate_candidates", "unmapped_observations",
    )}
    details = row["runtime_details"] if isinstance(row["runtime_details"], dict) else {}
    host = _safe_source_url(row["source_url"])
    manifest_values = (
        row["manifest_artifact_sha256"], row["manifest_normalized_sha256"],
        row["manifest_normalized_rows"], row["manifest_source_url"],
        row["manifest_retrieved_at"], row["manifest_code_version"],
        row["manifest_config_version"],
    )
    manifest_present = all(value is not None for value in manifest_values)
    manifest_reconciliation = {
        "present": manifest_present,
        "raw_hash_matches_run": False,
        "normalized_hash_matches_run": False,
        "normalized_rows_match_imported_observation_count": False,
        "source_host_matches_run": False,
        "retrieved_at_matches_run": False,
    }
    if manifest_present:
        manifest_reconciliation.update({
            "raw_hash_matches_run": _safe_hash(row["manifest_artifact_sha256"], "manifest_artifact_sha256") == source_hash,
            "normalized_hash_matches_run": _safe_hash(row["manifest_normalized_sha256"], "manifest_normalized_sha256") == normalized_hash,
            "normalized_rows_match_imported_observation_count": _safe_count(row["manifest_normalized_rows"], "manifest_normalized_rows") == counts["imported_observation_count"],
            "source_host_matches_run": _safe_source_url(row["manifest_source_url"]) == host,
            "retrieved_at_matches_run": row["manifest_retrieved_at"] == row["retrieved_at"],
        })
    physical_checks = {
        "observations_match_import_counter": counts["physical_observation_count"] == counts["imported_observation_count"],
        "candidate_groups_match_facility_counter": counts["physical_candidate_count"] == counts["facility_count"],
        "source_coordinate_candidates_match_import_counter": counts["source_coordinate_candidates"] == counts["numeric_coordinate_count"],
        "api_listable_matches_physical_candidates": counts["physical_candidate_count"] == counts["api_listable_count"],
        # These are import-time counters. Later private provider/reference
        # enrichment and source-coordinate fallback can change current map
        # serving without changing the immutable source-preview run.
        "import_time_map_counters_not_compared_to_current_geometry": True,
        "source_run_public_rows_zero": counts["public_rows"] == 0,
        "idempotent_replay_recorded": isinstance(row["idempotent_replay"], bool),
    }
    return {
        "source_id": source_id,
        "snapshot": {
            "snapshot_sha256": snapshot_hash,
            "source_artifact_sha256": source_hash,
            "normalized_sha256": normalized_hash,
            "source_host": host,
            "retrieved_at": row["retrieved_at"].isoformat() if hasattr(row["retrieved_at"], "isoformat") else str(row["retrieved_at"]),
            "adapter_version": _safe_dimension(row["adapter_version"], "adapter_version"),
            "schema_version": _safe_dimension(row["schema_version"], "schema_version"),
            "handoff_code_version": _safe_dimension(row["manifest_code_version"], "handoff_code_version") if manifest_present else None,
            "handoff_config_version": _safe_dimension(row["manifest_config_version"], "handoff_config_version") if manifest_present else None,
            "manifest_reconciliation": manifest_reconciliation,
            "processing_flags": _safe_source_flags(details),
            "idempotent_replay": bool(row["idempotent_replay"]),
        },
        "counts": counts,
        "exclusions": {
            "quarantine_reason_counts": _safe_reason_counts(details),
            "quarantine_reasons_with_safe_code_total": sum(_safe_reason_counts(details).values()),
            "source_scope_out_of_scope": counts["out_of_scope_count"],
            "source_quarantine": counts["quarantined_count"],
            "source_specific_aggregate_flags": _safe_exclusion_details(details),
        },
        "physical_reconciliation": physical_checks,
        "source_coordinates_and_display_geometry": geography.get(source_id, {}),
        "private_enrichment_state_reason_counts": enrichment.get(source_id, {}),
        "geocoder_provider_result_counts": providers.get(source_id, {}),
        "geocoder_display_evidence_counts": display_providers.get(source_id, {}),
        "taxonomy": [item for item in taxonomy if item["source_id"] == source_id],
        "taxonomy_crosswalks": [item for item in crosswalks if item["source_id"] == source_id],
        "candidate_scope": "private_preview_only_not_publication_eligible",
    }


def _public_relation_counts(connection: Any, available: dict[str, bool]) -> dict[str, Any]:
    counts: dict[str, Any] = {}
    for relation in _SAFE_PUBLIC_RELATIONS:
        if not available.get(relation, False):
            counts[relation] = {"state": "relation_unavailable", "count": None}
            continue
        schema, name = relation.split(".", 1)
        # Both identifiers come from the fixed allowlist above.
        row = connection.execute(f"SELECT count(*) FROM {schema}.{name}").fetchone()
        counts[relation] = {"state": "measured", "count": _safe_count(row[0], relation)}
    return counts


def build_inventory(connection: Any) -> dict[str, Any]:
    """Collect aggregate values in one read-only repeatable-read transaction."""
    connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
    read_at = connection.execute("SELECT transaction_timestamp()").fetchone()[0]
    requested_relations = REQUIRED_RELATIONS + OPTIONAL_RELATIONS
    relation_rows = _typed_rows(connection, _RELATION_SQL, ("relation", "available"), (list(requested_relations),))
    available = {str(row["relation"]): bool(row["available"]) for row in relation_rows}
    missing = [relation for relation in REQUIRED_RELATIONS if not available.get(relation, False)]
    if missing:
        base = {
            "schema_version": SCHEMA_VERSION,
            "status": "blocked_schema_incomplete",
            "schema": {"required_relations_available": False, "missing_required_relations": missing},
            "candidate_release": {"release_id": None, "status": "not-created-by-inventory", "member_rows": 0},
            "publication": {"authorized": False, "claim": "none"},
        }
        return _with_hash(base, read_at)

    source_rows = _typed_rows(connection, _SOURCE_SQL, _SOURCE_COLUMNS)
    taxonomy_rows = _typed_rows(connection, _TAXONOMY_SQL, (
        "source_id", "taxonomy_version", "crosswalk_version", "ruleset_version",
        "display_category", "candidate_sets", "assignment_rows",
    ))
    mapping_rows = _typed_rows(connection, _TAXONOMY_MAPPING_SQL, (
        "source_id", "taxonomy_version", "crosswalk_version", "ruleset_version",
        "primary_category", "mapping_method", "mapping_status", "assignment_rows",
    ))
    crosswalk_rows = _typed_rows(connection, _CROSSWALKS_SQL, (
        "source_id", "taxonomy_version", "crosswalk_version", "ruleset_version",
        "definition_sha256", "rule_count",
    ))
    geography_rows = _typed_rows(connection, _GEOGRAPHY_SQL, (
        "source_id", "geometry_source", "candidate_count", "display_point_count", "private_map_served_count",
    ))
    enrichment_rows = _typed_rows(connection, _ENRICHMENT_SQL, (
        "source_id", "state_code", "reason_code", "count",
    ))
    geo_by_source: dict[str, dict[str, Any]] = {}
    for row in geography_rows:
        source = str(row["source_id"])
        raw_geometry = str(row["geometry_source"])
        geometry = raw_geometry if _SAFE_CODE.fullmatch(raw_geometry) else "other_or_unrecognized"
        geo_by_source.setdefault(source, {})[geometry] = {
            "candidate_groups": _safe_count(row["candidate_count"], "geometry_candidate_groups"),
            "display_point_groups": _safe_count(row["display_point_count"], "geometry_display_point_groups"),
            "currently_private_map_served_groups": _safe_count(row["private_map_served_count"], "geometry_private_map_served_groups"),
        }
    for row in enrichment_rows:
        row["state_code"] = _safe_dimension(row["state_code"], "enrichment_state")
        row["reason_code"] = _safe_dimension(row["reason_code"], "enrichment_reason")
    enrich_by_source = _counter_rows(enrichment_rows, keys=("state_code", "reason_code"), count_key="count")

    provider_by_source: dict[str, dict[str, int]] = {}
    if all(available.get(item, False) for item in ("real_preview.geocode_targets", "uec.geocode_jobs", "uec.geocode_results")):
        provider_rows = _typed_rows(connection, _PROVIDER_SQL, (
            "source_id", "provider_id", "status", "precision", "candidate_count",
        ))
        for row in provider_rows:
            row["provider_id"] = _safe_dimension(row["provider_id"], "provider_id")
            row["status"] = _safe_dimension(row["status"], "geocode_status")
            row["precision"] = _safe_dimension(row["precision"], "geocode_precision")
        provider_by_source = _counter_rows(provider_rows, keys=("provider_id", "status", "precision"), count_key="candidate_count")
    display_by_source: dict[str, dict[str, int]] = {}
    if all(available.get(item, False) for item in ("real_preview.geocode_display_evidence", "uec.geocode_results")):
        display_rows = _typed_rows(connection, _DISPLAY_PROVIDER_SQL, (
            "source_id", "provider_id", "status", "display_precision", "candidate_count",
        ))
        for row in display_rows:
            row["provider_id"] = _safe_dimension(row["provider_id"], "provider_id")
            row["status"] = _safe_dimension(row["status"], "geocode_status")
            row["display_precision"] = _safe_dimension(row["display_precision"], "display_precision")
        display_by_source = _counter_rows(display_rows, keys=("provider_id", "status", "display_precision"), count_key="candidate_count")

    taxonomy = []
    for row in taxonomy_rows:
        taxonomy.append({
            "source_id": str(row["source_id"]),
            "taxonomy_version": _safe_dimension(row["taxonomy_version"], "taxonomy_version"),
            "crosswalk_version": _safe_dimension(row["crosswalk_version"], "crosswalk_version"),
            "ruleset_version": _safe_dimension(row["ruleset_version"], "ruleset_version"),
            "display_category": _safe_dimension(row["display_category"], "display_category"),
            "candidate_sets": _safe_count(row["candidate_sets"], "taxonomy_candidate_sets"),
            "assignment_rows": _safe_count(row["assignment_rows"], "taxonomy_assignment_rows"),
        })
    mapping = []
    for row in mapping_rows:
        mapping.append({
            "source_id": str(row["source_id"]),
            "taxonomy_version": _safe_dimension(row["taxonomy_version"], "taxonomy_version"),
            "crosswalk_version": _safe_dimension(row["crosswalk_version"], "crosswalk_version"),
            "ruleset_version": _safe_dimension(row["ruleset_version"], "ruleset_version"),
            "primary_category": _safe_dimension(row["primary_category"], "primary_category"),
            "mapping_method": _safe_dimension(row["mapping_method"], "mapping_method"),
            "mapping_status": _safe_dimension(row["mapping_status"], "mapping_status"),
            "assignment_rows": _safe_count(row["assignment_rows"], "taxonomy_mapping_rows"),
        })
    crosswalks = []
    for row in crosswalk_rows:
        crosswalks.append({
            "source_id": str(row["source_id"]),
            "taxonomy_version": _safe_dimension(row["taxonomy_version"], "taxonomy_version"),
            "crosswalk_version": _safe_dimension(row["crosswalk_version"], "crosswalk_version"),
            "ruleset_version": _safe_dimension(row["ruleset_version"], "ruleset_version"),
            "definition_sha256": _safe_hash(row["definition_sha256"], "crosswalk_definition_sha256"),
            "rule_count": _safe_count(row["rule_count"], "crosswalk_rule_count"),
        })

    source_reports = [
        _source_report(row, taxonomy=taxonomy, crosswalks=crosswalks,
                       geography=geo_by_source, enrichment=enrich_by_source,
                       providers=provider_by_source, display_providers=display_by_source)
        for row in source_rows
    ]
    release_rows = _typed_rows(connection, _RELEASES_SQL, (
        "status", "profile", "release_count", "release_with_members_count", "member_observation_rows",
    ))
    release_totals = connection.execute(_RELEASE_TOTALS_SQL).fetchone()
    release_counts = [{
        "status": _safe_dimension(row["status"], "release_status"), "profile": _safe_dimension(row["profile"], "release_profile"),
        "release_count": _safe_count(row["release_count"], "release_count"),
        "releases_with_members": _safe_count(row["release_with_members_count"], "release_with_members"),
        "member_observation_rows": _safe_count(row["member_observation_rows"], "member_observation_rows"),
    } for row in release_rows]
    graph_rows = []
    if available.get("uec.graph_connection_edges", False):
        graph_rows = _typed_rows(connection, _PRIVATE_GRAPH_SQL, (
            "connection_type", "publication_status", "storage_state", "edge_count",
        ))
    private_graph = [{
        "connection_type": _safe_dimension(row["connection_type"], "connection_type"),
        "publication_status": _safe_dimension(row["publication_status"], "publication_status"),
        "storage_state": _safe_dimension(row["storage_state"], "storage_state"),
        "edge_count": _safe_count(row["edge_count"], "private_graph_edges"),
    } for row in graph_rows]
    public_counts = _public_relation_counts(connection, available)
    migrations = None
    if available.get("uec.schema_migrations", False):
        migration_row = connection.execute(_MIGRATION_SQL).fetchone()
        migrations = {"applied_count": _safe_count(migration_row[0], "migration_count"), "latest_version": migration_row[1]}

    source_inventoried_candidates = sum(item["counts"]["physical_candidate_count"] for item in source_reports)
    source_inventoried_observations = sum(item["counts"]["physical_observation_count"] for item in source_reports)
    inventory = {
        "schema_version": SCHEMA_VERSION,
        "status": "measured" if source_reports else "no_latest_private_snapshots",
        "read_consistency": "repeatable_read_read_only",
        "schema": {"required_relations_available": True, "relation_availability": available, "migrations": migrations},
        "source_scope": {
            "latest_imported_source_snapshot_count": len(source_reports),
            "source_ids_are_snapshot_presence_only_not_publication_or_live_readiness": True,
            "candidate_observation_rows": source_inventoried_observations,
            "private_candidate_groups": source_inventoried_candidates,
            "sources": source_reports,
        },
        "release_milestone": {
            "dataset_version": "v0",
            "recommended_calver": "2026.10.1-rc.1",
            "calver_status": "recommendation_pending_human_choice",
            "website_v2_is_a_separate_milestone": True,
        },
        "taxonomy_mapping_aggregates": mapping,
        "candidate_release": {
            "release_id": None,
            "status": "not-created-by-inventory",
            "member_rows": 0,
            "note": "The private candidate pool is not a uec.release_manifests promoted release; human review and the release workflow remain separate.",
        },
        "release_database_state": {
            "release_rows": _safe_count(release_totals[0], "release_rows"),
            "release_member_rows": _safe_count(release_totals[1], "release_member_rows"),
            "release_manifest_rows": _safe_count(release_totals[2], "release_manifest_rows"),
            "promoted_release_rows": _safe_count(release_totals[3], "promoted_release_rows"),
            "by_status_and_profile": release_counts,
        },
        "graph_database_state": {
            "private_connection_edge_counts": private_graph if available.get("uec.graph_connection_edges", False) else None,
            "public_projection_counts": public_counts,
        },
        "publication": {
            "authorized": False,
            "claim": "none",
            "reason": "This read-only candidate inventory does not record approvals, validate source redistribution rights, create release membership, or build publication projections.",
        },
        "limitations": [
            "Latest imported private-preview snapshots are not evidence that all source routes are current, complete, or live-ready.",
            "A source snapshot is not a reviewed facility count; source-specific candidate grouping, exclusions, and taxonomy remain separate evidence.",
            "Physical private preview counts do not establish privacy eligibility, factual review, project approval, source redistribution rights, or public visibility.",
            "Zero public counts are only the measured state of listed database projections in this repeatable-read transaction, not proof that all deployment copies or caches are empty.",
            "The inventory does not create or update uec.releases, uec.release_members, uec.release_manifests, or public read models.",
        ],
    }
    _assert_row_free(inventory)
    return _with_hash(inventory, read_at)


def _with_hash(inventory: dict[str, Any], read_at: Any) -> dict[str, Any]:
    payload = dict(inventory)
    payload["inventory_sha256"] = hashlib.sha256(_canonical_bytes(inventory)).hexdigest()
    payload["read_at_utc"] = read_at.isoformat() if hasattr(read_at, "isoformat") else str(read_at)
    return payload


def write_inventory(path: Path, inventory: dict[str, Any]) -> None:
    if path.exists():
        raise FileExistsError("refusing to overwrite an existing inventory output")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    if temporary.exists():
        raise FileExistsError("temporary inventory output already exists")
    temporary.write_bytes(_canonical_bytes(inventory))
    temporary.replace(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.environ.get("UEC_DATABASE_URL"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if not args.database_url:
        parser.error("--database-url or UEC_DATABASE_URL is required")
    try:
        # The transaction itself is marked READ ONLY before any inventory query.
        with psycopg.connect(args.database_url) as connection:
            inventory = build_inventory(connection)
        write_inventory(args.output, inventory)
    except FileExistsError:
        print(json.dumps({"status": "blocked", "reason": "output_exists"}), file=sys.stderr)
        return 2
    except psycopg.Error:
        # Driver exception text can contain connection details; do not echo it.
        print(json.dumps({"status": "blocked", "reason": "database_read_failed"}), file=sys.stderr)
        return 2
    except (OSError, ValueError):
        print(json.dumps({"status": "blocked", "reason": "inventory_validation_or_write_failed"}), file=sys.stderr)
        return 2
    print(json.dumps({
        "status": inventory["status"],
        "schema_version": SCHEMA_VERSION,
        "inventory_sha256": inventory["inventory_sha256"],
        "source_snapshots": inventory.get("source_scope", {}).get("latest_imported_source_snapshot_count", 0),
        "private_candidate_groups": inventory.get("source_scope", {}).get("private_candidate_groups", 0),
        "public_claim": "none",
    }, sort_keys=True))
    return 0 if inventory["status"] == "measured" else 2


if __name__ == "__main__":
    raise SystemExit(main())
