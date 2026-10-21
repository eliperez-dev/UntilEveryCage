"""Build a safe, release-scoped graph serving projection from private edges."""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Iterable
import uuid

import psycopg

from pipeline.common.graph_persistence import _validate_private_graph_writer, require_private_graph_target


PROJECTION_VERSION = "graph-release-projection-v2"
PROJECTION_PLANNER_GUARD = "SET LOCAL enable_nestloop=off"
_SQL_PATH = Path(__file__).resolve().parents[1] / "sql" / "graph_public_edge_ctes.sql"
EDGE_CTES = _SQL_PATH.read_text(encoding="utf-8")
_PUBLIC_GROUPS = frozenset({"source", "identity", "location", "contact", "temporal", "contradiction"})
_PUBLIC_CONTRADICTIONS = frozenset({"conflicting_identifier", "conflicting_address", "temporal_conflict"})


def _python_edge_select(release_id: str) -> tuple[str, dict[str, str]]:
    """Bind the shared Rust `$1` selector using psycopg's named placeholder form."""
    query = f"WITH {EDGE_CTES.replace('$1', '%(release_id)s')} SELECT * FROM edges"
    return query, {"release_id": release_id}


def _python_endpoint_select(release_id: str) -> tuple[str, dict[str, str]]:
    query = (f"WITH {EDGE_CTES.replace('$1', '%(release_id)s')} "
             "SELECT source_id,identifier_type,source_identifier,entity_type,public_entity_id,anchors "
             "FROM eligible_source_endpoints")
    return query, {"release_id": release_id}


def _insert_endpoint_batch(connection: Any, projection_id: uuid.UUID,
                           rows: Iterable[Any], endpoint_ids: dict[tuple[str, str, str, str, uuid.UUID], uuid.UUID]) -> tuple[int, int]:
    endpoints: list[tuple[Any, ...]] = []
    anchors: list[tuple[Any, ...]] = []
    for row in rows:
        key = (str(row[0]), str(row[1]), str(row[2]), str(row[3]), uuid.UUID(str(row[4])))
        endpoint_id = endpoint_ids.setdefault(key, uuid.uuid4())
        endpoints.append((projection_id, endpoint_id, key[4], key[3], key[0], key[1]))
        anchors.extend((projection_id, endpoint_id, record_id, facility_id)
                       for record_id, facility_id in _anchors(row[5]))
    if endpoints:
        with connection.cursor() as cursor:
            cursor.executemany(
                """INSERT INTO uec.graph_public_projection_endpoints
                   (projection_id,endpoint_id,public_entity_id,entity_type,source_id,identifier_type)
                   VALUES (%s,%s,%s,%s,%s,%s)""", endpoints,
            )
            cursor.executemany(
                """INSERT INTO uec.graph_public_projection_anchors
                   (projection_id,endpoint_id,source_record_id,facility_id)
                   VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING""", anchors,
            )
    return len(endpoints), len(anchors)


def _json_value(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            return {}
    return value if isinstance(value, dict) else {}


def sanitize_signal_explanation(value: Any) -> dict[str, Any]:
    """Retain only allowlisted codes and numeric/boolean contributions."""
    parsed = _json_value(value)
    groups: dict[str, float] = {}
    raw_groups = parsed.get("group_contributions")
    if isinstance(raw_groups, dict):
        for group, amount in raw_groups.items():
            if group not in _PUBLIC_GROUPS or isinstance(amount, bool):
                continue
            try:
                number = float(amount)
            except (TypeError, ValueError, OverflowError):
                continue
            if math.isfinite(number) and number >= 0:
                groups[group] = number
    contradictions: list[dict[str, Any]] = []
    raw_contradictions = parsed.get("contradictions")
    if isinstance(raw_contradictions, list):
        for row in raw_contradictions:
            if not isinstance(row, dict) or row.get("name") not in _PUBLIC_CONTRADICTIONS:
                continue
            safe: dict[str, Any] = {"name": row["name"], "group": "contradiction"}
            weight = row.get("weight")
            if not isinstance(weight, bool):
                try:
                    number = float(weight)
                except (TypeError, ValueError, OverflowError):
                    number = math.nan
                if math.isfinite(number) and 0 <= number <= 1:
                    safe["weight"] = number
            if isinstance(row.get("value"), bool):
                safe["value"] = row["value"]
            contradictions.append(safe)
    return {"group_contributions": groups, "contradictions": contradictions}


def _anchors(value: Any) -> list[tuple[uuid.UUID, uuid.UUID]]:
    if isinstance(value, str):
        value = _json_value(value)
    if not isinstance(value, list):
        return []
    result: set[tuple[uuid.UUID, uuid.UUID]] = set()
    for row in value:
        if not isinstance(row, dict):
            continue
        try:
            result.add((uuid.UUID(str(row["source_record_id"])), uuid.UUID(str(row["facility_id"]))))
        except (KeyError, ValueError, TypeError):
            continue
    return sorted(result)


def _support_records(value: Any) -> list[tuple[uuid.UUID, str, uuid.UUID]]:
    if isinstance(value, str):
        value = _json_value(value)
    if not isinstance(value, list):
        return []
    result: set[tuple[uuid.UUID, str, uuid.UUID]] = set()
    for row in value:
        if not isinstance(row, dict):
            continue
        try:
            result.add((uuid.UUID(str(row["source_record_id"])), str(row["source_id"]),
                        uuid.UUID(str(row["artifact_id"]))))
        except (KeyError, ValueError, TypeError):
            continue
    return sorted(result, key=lambda item: (str(item[0]), item[1], str(item[2])))


def _insert_batch(connection: Any, projection_id: uuid.UUID, release_id: str,
                  rows: Iterable[Any], endpoint_ids: dict[tuple[str, str, str, str, uuid.UUID], uuid.UUID]) -> int:
    edge_rows: list[tuple[Any, ...]] = []
    support_rows: list[tuple[Any, ...]] = []
    for row in rows:
        edge_id = row[0]
        # Source-native identifier values at columns 5 and 10 are deliberately
        # consumed by the selector but never written to the public read model.
        from_key = (str(row[3]), str(row[4]), str(row[5]), str(row[2]), uuid.UUID(str(row[1])))
        to_key = (str(row[8]), str(row[9]), str(row[10]), str(row[7]), uuid.UUID(str(row[6])))
        from_endpoint_id, to_endpoint_id = endpoint_ids.get(from_key), endpoint_ids.get(to_key)
        if from_endpoint_id is None or to_endpoint_id is None:
            raise ValueError("graph endpoint selector and edge selector diverged")
        edge_rows.append((projection_id, release_id, edge_id, from_endpoint_id, row[1], row[2], row[3], row[4],
                          to_endpoint_id, row[6], row[7], row[8], row[9], row[11], row[12], row[13], row[14],
                          json.dumps(sanitize_signal_explanation(row[15]), sort_keys=True), row[16],
                          row[17], row[18], row[19], row[20]))
        support_rows.extend((projection_id, edge_id, record_id, source_id, artifact_id)
                            for record_id, source_id, artifact_id in _support_records(row[22]))
    if edge_rows:
        with connection.cursor() as cursor:
            cursor.executemany(
            """INSERT INTO uec.graph_public_projection_edges
               (projection_id,release_id,connection_edge_id,from_endpoint_id,from_entity_id,from_entity_type,
                from_source_id,from_identifier_type,to_endpoint_id,to_entity_id,to_entity_type,to_source_id,
                to_identifier_type,relationship_type,connection_type,confidence,confidence_band,
                signal_explanation,match_method,observed_at,computed_at,ruleset_version,conflicting)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s)""",
            edge_rows,
            )
            cursor.executemany(
                """INSERT INTO uec.graph_public_projection_edge_supports
               (projection_id,connection_edge_id,source_record_id,source_id,artifact_id)
               VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""", support_rows,
            )
    return len(edge_rows)


def build_release_projection(database_url: str, release_id: str, *,
                             private_target: tuple[str, str], batch_size: int = 500) -> dict[str, Any]:
    if batch_size < 1:
        raise ValueError("batch size must be positive")
    database_name, purpose = private_target
    require_private_graph_target(database_url, expected_database=database_name, purpose=purpose)
    projection_id = uuid.uuid4()
    with psycopg.connect(database_url) as connection:
        _validate_private_graph_writer(connection, database_name)
        release = connection.execute(
            """SELECT release.profile,release.status,release.test_only,manifest.manifest_sha256,
                      suppression.generation,generation.generation
                 FROM uec.releases release
                 JOIN uec.public_discovery_read_models model USING(release_id)
                 JOIN uec.release_manifests manifest
                   ON manifest.release_id=release.release_id
                  AND manifest.manifest_sha256=model.manifest_sha256
                 LEFT JOIN uec.public_release_history history
                   ON history.release_id=release.release_id AND history.profile=release.profile
                 CROSS JOIN uec.public_suppression_generation suppression
                 CROSS JOIN uec.graph_projection_generation generation
                WHERE release.release_id=%s AND release.profile IS NOT NULL
                  AND (release.status='promoted' OR
                       (release.status='validated' AND history.release_id IS NOT NULL))
                  AND suppression.singleton=true
                  AND generation.singleton=true""",
            (release_id,),
        ).fetchone()
        if not release or release[2]:
            raise ValueError("release is not eligible for graph projection")
        manifest_sha256 = str(release[3])
        suppression_generation = int(release[4])
        edge_generation = int(release[5])
        existing = connection.execute(
            """SELECT projection_id,edge_count FROM uec.graph_public_projection_builds
                WHERE release_id=%s AND projection_version=%s AND edge_generation=%s
                  AND release_manifest_sha256=%s AND suppression_generation=%s
                  AND status='completed' AND active""",
            (release_id, PROJECTION_VERSION, edge_generation, manifest_sha256, suppression_generation),
        ).fetchone()
        if existing:
            return {"status": "already_present", "release_id": release_id,
                    "projection_id": str(existing[0]), "edge_count": int(existing[1])}
        with connection.transaction():
            connection.execute(
                """INSERT INTO uec.graph_public_projection_builds
                   (projection_id,release_id,projection_version,edge_generation,
                    release_manifest_sha256,suppression_generation)
                   VALUES (%s,%s,%s,%s,%s,%s)""",
                (projection_id, release_id, PROJECTION_VERSION, edge_generation,
                 manifest_sha256, suppression_generation),
            )
        connection.commit()
        count = endpoint_count = anchor_count = 0
        endpoint_ids: dict[tuple[str, str, str, str, uuid.UUID], uuid.UUID] = {}
        try:
            with connection.transaction():
                # The release/support CTEs have a known severe row-count
                # underestimation under nested loops. Keep the measured hash
                # join plan override transaction-local to this one build.
                connection.execute(PROJECTION_PLANNER_GUARD)
                endpoint_cursor = connection.cursor(name="uec_graph_projection_endpoints")
                endpoint_query, endpoint_parameters = _python_endpoint_select(release_id)
                endpoint_cursor.execute(endpoint_query, endpoint_parameters)
                while batch := endpoint_cursor.fetchmany(batch_size):
                    inserted_endpoints, inserted_anchors = _insert_endpoint_batch(
                        connection, projection_id, batch, endpoint_ids,
                    )
                    endpoint_count += inserted_endpoints
                    anchor_count += inserted_anchors
                endpoint_cursor.close()
                cursor = connection.cursor(name="uec_graph_projection_source")
                query, parameters = _python_edge_select(release_id)
                cursor.execute(query, parameters)
                while batch := cursor.fetchmany(batch_size):
                    count += _insert_batch(connection, projection_id, release_id, batch, endpoint_ids)
                cursor.close()
                connection.execute(
                    "UPDATE uec.graph_public_projection_builds SET active=false WHERE release_id=%s AND active",
                    (release_id,),
                )
                connection.execute(
                    """UPDATE uec.graph_public_projection_builds
                          SET status='completed',edge_count=%s,completed_at=now(),active=true
                        WHERE projection_id=%s""",
                    (count, projection_id),
                )
        except Exception:
            with connection.transaction():
                connection.execute(
                    "UPDATE uec.graph_public_projection_builds SET status='failed',completed_at=NULL,active=false WHERE projection_id=%s",
                    (projection_id,),
                )
            raise
    return {"status": "completed", "release_id": release_id,
            "projection_id": str(projection_id), "edge_count": count,
            "projection_version": PROJECTION_VERSION,
            "endpoint_count": endpoint_count, "anchor_count": anchor_count,
            "edge_generation": edge_generation,
            "suppression_generation": suppression_generation}
