"""Append-only taxonomy persistence for canonical and private preview records."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from psycopg.types.json import Jsonb

from pipeline.taxonomy.contract import (
    TAXONOMY_VERSION,
    TaxonomyAssignment,
    canonical_assignments,
    choose_display_category,
    crosswalk_sha256,
    validate_crosswalk,
)


_COLUMNS = (
    "assignment_ordinal", "primary_key", "leaf_key", "leaf_label",
    "source_code_reference", "source_label_reference", "source_code", "source_label",
    "mapping_method", "mapping_status",
)


def _canonical_rows(
    observation_id: str,
    source_record_id: str,
    artifact_id: str,
    document: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
) -> tuple[TaxonomyAssignment, ...]:
    validate_crosswalk(dict(document))
    converted = [TaxonomyAssignment(
        observation_id=str(observation_id),
        source_record_id=str(source_record_id),
        artifact_id=str(artifact_id),
        taxonomy_version=TAXONOMY_VERSION,
        crosswalk_version=str(document["crosswalk_version"]),
        ruleset_version=str(document["ruleset_version"]),
        primary_key=str(row["primary_key"]),
        leaf_key=row.get("leaf_key"),
        leaf_label=row.get("leaf_label"),
        source_code_reference=row.get("source_code_reference"),
        source_label_reference=row.get("source_label_reference"),
        source_code=row.get("source_code"),
        source_label=row.get("source_label"),
        method=str(row["mapping_method"]),
        status=str(row["mapping_status"]),
    ) for row in rows]
    return canonical_assignments(converted)


def _insert_crosswalk(connection: Any, schema: str, document: Mapping[str, Any]) -> str:
    validated = validate_crosswalk(dict(document))
    digest = crosswalk_sha256(validated)
    table = f"{schema}.taxonomy_crosswalks" if schema == "uec" else f"{schema}.taxonomy_crosswalks"
    connection.execute(
        f"""INSERT INTO {table}
            (source_id,taxonomy_version,crosswalk_version,ruleset_version,definition,definition_sha256)
            VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (source_id,crosswalk_version) DO NOTHING""",
        (validated["source_id"], validated["taxonomy_version"], validated["crosswalk_version"],
         validated["ruleset_version"], Jsonb(validated), digest),
    )
    existing = connection.execute(
        f"SELECT definition_sha256 FROM {table} WHERE source_id=%s AND crosswalk_version=%s",
        (validated["source_id"], validated["crosswalk_version"]),
    ).fetchone()
    if existing is None or existing[0].strip() != digest:
        raise ValueError("crosswalk version already exists with different content")
    return digest


def _insert_rows(connection: Any, table: str, assignment_set_id: Any, rows: Sequence[TaxonomyAssignment]) -> None:
    expected = []
    for ordinal, row in enumerate(rows):
        expected.append((
            ordinal, row.primary_key, row.leaf_key, row.leaf_label,
            row.source_code_reference, row.source_label_reference, row.source_code,
            row.source_label, row.method, row.status,
        ))
    found = connection.execute(
        f"SELECT {', '.join(_COLUMNS)} FROM {table} WHERE assignment_set_id=%s ORDER BY assignment_ordinal",
        (assignment_set_id,),
    ).fetchall()
    if found:
        if [tuple(row) for row in found] != expected:
            raise ValueError("idempotency key already has a different taxonomy assignment set")
        return
    sql = f"""INSERT INTO {table} (assignment_set_id,{', '.join(_COLUMNS)})
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"""
    for row in expected:
        connection.execute(sql, (assignment_set_id, *row))


def persist_uec_assignment_set(
    connection: Any,
    *,
    observation_id: str,
    source_record_id: str,
    artifact_id: str,
    document: Mapping[str, Any],
    assignment_rows: Sequence[Mapping[str, Any]],
) -> Any:
    """Persist one assignment set with genuine uec observation lineage."""
    digest = _insert_crosswalk(connection, "uec", document)
    rows = _canonical_rows(observation_id, source_record_id, artifact_id, document, assignment_rows)
    display = choose_display_category(rows)
    first = rows[0]
    inserted = connection.execute(
        """INSERT INTO uec.observation_taxonomy_assignment_sets
            (observation_id,source_record_id,source_id,artifact_id,taxonomy_version,crosswalk_version,ruleset_version,display_category)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (observation_id,taxonomy_version,crosswalk_version,ruleset_version) DO NOTHING
            RETURNING assignment_set_id""",
        (observation_id, source_record_id, document["source_id"], artifact_id, TAXONOMY_VERSION,
         document["crosswalk_version"], document["ruleset_version"], display),
    ).fetchone()
    set_row = inserted or connection.execute(
        """SELECT assignment_set_id,source_record_id,artifact_id,display_category
             FROM uec.observation_taxonomy_assignment_sets
            WHERE observation_id=%s AND taxonomy_version=%s AND crosswalk_version=%s AND ruleset_version=%s""",
        (observation_id, TAXONOMY_VERSION, document["crosswalk_version"], document["ruleset_version"]),
    ).fetchone()
    if set_row is None or (not inserted and (str(set_row[1]) != str(source_record_id) or str(set_row[2]) != str(artifact_id) or set_row[3] != display)):
        raise ValueError("taxonomy assignment set idempotency key has conflicting lineage or display category")
    assignment_set_id = set_row[0] if inserted else set_row[0]
    _insert_rows(connection, "uec.observation_taxonomy_assignments", assignment_set_id, rows)
    return assignment_set_id


def persist_preview_candidate_assignment_set(
    connection: Any,
    *,
    candidate_id: str,
    representative_observation_id: str,
    snapshot_sha256: str,
    source_id: str,
    document: Mapping[str, Any],
    assignment_rows: Sequence[Mapping[str, Any]],
) -> Any:
    """Persist one assignment set against real_preview's own candidate lineage."""
    if document.get("source_id") != source_id:
        raise ValueError("preview crosswalk source does not match candidate source")
    _insert_crosswalk(connection, "real_preview", document)
    # The canonical contract validator needs UUID-shaped lineage. Preview ids
    # are UUIDs too, but intentionally never enter the uec observation tables.
    rows = _canonical_rows(representative_observation_id, candidate_id, snapshot_sha256, document, assignment_rows)
    display = choose_display_category(rows)
    inserted = connection.execute(
        """INSERT INTO real_preview.candidate_taxonomy_assignment_sets
            (candidate_id,representative_observation_id,snapshot_sha256,source_id,taxonomy_version,crosswalk_version,ruleset_version,display_category)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (candidate_id,taxonomy_version,crosswalk_version,ruleset_version) DO NOTHING
            RETURNING assignment_set_id""",
        (candidate_id, representative_observation_id, snapshot_sha256, source_id, TAXONOMY_VERSION,
         document["crosswalk_version"], document["ruleset_version"], display),
    ).fetchone()
    set_row = inserted or connection.execute(
        """SELECT assignment_set_id,representative_observation_id,snapshot_sha256,source_id,display_category
             FROM real_preview.candidate_taxonomy_assignment_sets
            WHERE candidate_id=%s AND taxonomy_version=%s AND crosswalk_version=%s AND ruleset_version=%s""",
        (candidate_id, TAXONOMY_VERSION, document["crosswalk_version"], document["ruleset_version"]),
    ).fetchone()
    expected_lineage = (str(representative_observation_id), snapshot_sha256, source_id, display)
    if set_row is None or (not inserted and tuple(str(value) for value in set_row[1:]) != tuple(str(value) for value in expected_lineage)):
        raise ValueError("preview taxonomy idempotency key has conflicting lineage or display category")
    _insert_rows(connection, "real_preview.candidate_taxonomy_assignments", set_row[0], rows)
    return set_row[0]
