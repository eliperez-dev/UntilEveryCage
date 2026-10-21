"""Build a safe, release-scoped graph serving projection from private edges."""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Iterable
import uuid

import psycopg

from pipeline.common.graph_persistence import _validate_private_graph_writer, require_private_graph_target


PROJECTION_VERSION = "graph-release-projection-v1"
_SQL_PATH = Path(__file__).resolve().parents[1] / "sql" / "graph_public_edge_ctes.sql"
EDGE_CTES = _SQL_PATH.read_text(encoding="utf-8")
_PUBLIC_GROUPS = frozenset({"source", "identity", "location", "contact", "temporal", "contradiction"})
_PUBLIC_CONTRADICTIONS = frozenset({"conflicting_identifier", "conflicting_address", "temporal_conflict"})


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
                  rows: Iterable[Any]) -> int:
    edge_rows: list[tuple[Any, ...]] = []
    support_rows: list[tuple[Any, ...]] = []
    anchor_rows: list[tuple[Any, ...]] = []
    for row in rows:
        edge_id = row[0]
        # Source-native identifier values at columns 5 and 10 are deliberately
        # consumed by the selector but never written to the public read model.
        edge_rows.append((projection_id, release_id, edge_id, row[1], row[2], row[3], row[4],
                          row[6], row[7], row[8], row[9], row[11], row[12], row[13], row[14],
                          json.dumps(sanitize_signal_explanation(row[15]), sort_keys=True), row[16],
                          row[17], row[18], row[19], row[20]))
        support_rows.extend((projection_id, edge_id, record_id, source_id, artifact_id)
                            for record_id, source_id, artifact_id in _support_records(row[24]))
        anchor_rows.extend((projection_id, edge_id, side, record_id, facility_id)
                           for side, raw in (("from", row[22]), ("to", row[23]))
                           for record_id, facility_id in _anchors(raw))
    if edge_rows:
        connection.executemany(
            """INSERT INTO uec.graph_public_projection_edges
               (projection_id,release_id,connection_edge_id,from_entity_id,from_entity_type,
                from_source_id,from_identifier_type,to_entity_id,to_entity_type,to_source_id,
                to_identifier_type,relationship_type,connection_type,confidence,confidence_band,
                signal_explanation,match_method,observed_at,computed_at,ruleset_version,conflicting)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s)""",
            edge_rows,
        )
        connection.executemany(
            """INSERT INTO uec.graph_public_projection_edge_supports
               (projection_id,connection_edge_id,source_record_id,source_id,artifact_id)
               VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""", support_rows,
        )
        connection.executemany(
            """INSERT INTO uec.graph_public_projection_endpoint_anchors
               (projection_id,connection_edge_id,endpoint_side,source_record_id,facility_id)
               VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""", anchor_rows,
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
        count = 0
        try:
            with connection.transaction():
                cursor = connection.cursor(name="uec_graph_projection_source")
                cursor.execute(f"WITH {EDGE_CTES} SELECT * FROM edges", (release_id,))
                while batch := cursor.fetchmany(batch_size):
                    count += _insert_batch(connection, projection_id, release_id, batch)
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
            "edge_generation": edge_generation,
            "suppression_generation": suppression_generation}
