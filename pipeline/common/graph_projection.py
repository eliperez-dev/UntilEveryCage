"""Build a safe, release-scoped graph serving projection from private edges."""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Iterable
import uuid

import psycopg

from pipeline.common.graph_persistence import _validate_private_graph_writer, require_private_graph_target


PROJECTION_VERSION = "graph-release-projection-v3"
PROJECTION_PLANNER_GUARD = "SET LOCAL enable_nestloop=off"
STAGED_ANCHOR_RELATION = "pg_temp.uec_selected_release_facility_anchors"
_SQL_PATH = Path(__file__).resolve().parents[1] / "sql" / "graph_public_edge_ctes.sql"
EDGE_CTES = _SQL_PATH.read_text(encoding="utf-8")
# Evidence handoffs use compact field names while persisted facility aliases
# use the documented APHIS namespace. Normalize only this exact source/type
# pair; values and identifiers remain exact and source-qualified.
_APHIS_EVIDENCE_LINK_IDENTIFIER_TYPE_SQL = (
    "CASE WHEN endpoint.source_id='us.aphis' THEN "
    "CASE endpoint.identifier_type "
    "WHEN 'aphis_certificate_number' THEN 'certificate_number' "
    "WHEN 'aphis_customer_number' THEN 'customer_number' "
    "ELSE endpoint.identifier_type END "
    "ELSE endpoint.identifier_type END"
)
_PUBLIC_GROUPS = frozenset({"source", "identity", "location", "contact", "temporal", "contradiction"})
_PUBLIC_CONTRADICTIONS = frozenset({"conflicting_identifier", "conflicting_address", "temporal_conflict"})


def _staged_anchor_query(query: str) -> str:
    return query.replace("uec.graph_public_live_facility_anchors_current", STAGED_ANCHOR_RELATION)


def _python_edge_select(release_id: str) -> tuple[str, dict[str, str]]:
    """Bind the shared Rust `$1` selector using psycopg's named placeholder form."""
    query = f"WITH {EDGE_CTES.replace('$1', '%(release_id)s')} SELECT * FROM edges"
    return query, {"release_id": release_id}


def _python_endpoint_select(release_id: str) -> tuple[str, dict[str, str]]:
    query = (f"WITH {EDGE_CTES.replace('$1', '%(release_id)s')} "
             "SELECT source_id,identifier_type,source_identifier,entity_type,public_entity_id,anchors "
             "FROM eligible_source_endpoints")
    return query, {"release_id": release_id}


def _python_organization_label_select(release_id: str) -> tuple[str, dict[str, str]]:
    # The exact eligible endpoints and their safe release anchors have already
    # been selected/staged by the endpoint cursor. Reusing that bounded set
    # avoids re-running the expensive whole-edge CTE just to attach labels.
    # Name assertions remain private, and only the final allowlisted label is
    # inserted into the safe projection.
    query = ("WITH approved_assertions AS MATERIALIZED ("
             " SELECT assertion.name_assertion_id,assertion.source_id,assertion.source_record_id,"
             "        assertion.organization_id,assertion.identifier_id,assertion.assertion_role,"
             "        assertion.assertion_value "
             " FROM uec.graph_source_name_assertions assertion "
             " WHERE assertion.assertion_role IN ('legal','business','operator') "
             "   AND lower(regexp_replace(assertion.source_field,'^.*[.]','')) IN "
             "    ('legal_name','business_name','registered_business_name','company_name','organization_name',"
             "     'organisation_name','operator_name','operator_company_name','raison_sociale','ragione_sociale','registered_name') "
             "   AND btrim(assertion.assertion_value)<>''), "
             "release_facilities AS MATERIALIZED ("
             " SELECT source_record_id,(array_agg(DISTINCT facility_id ORDER BY facility_id))[1] AS facility_id "
             " FROM uec.graph_public_live_facility_anchors_current "
             " WHERE release_id=%(release_id)s GROUP BY source_record_id "
             " HAVING count(DISTINCT facility_id)=1), "
             "direct_support AS ("
             " SELECT assertion.name_assertion_id,assertion.source_id,assertion.source_record_id,"
             "        record.artifact_id,record.source_record_id AS canonical_source_record_id,approved.facility_id "
             " FROM approved_assertions assertion "
             " JOIN uec.source_records record ON record.source_record_id=assertion.source_record_id "
             "  AND record.source_id=assertion.source_id "
             " JOIN release_facilities approved ON approved.source_record_id=record.source_record_id), "
             "bound_support AS ("
             " SELECT assertion.name_assertion_id,assertion.source_id,assertion.source_record_id,"
             "        binding.artifact_id,binding.canonical_source_record_id,binding.facility_id "
             " FROM approved_assertions assertion "
             " JOIN uec.graph_record_release_bindings binding "
             "  ON binding.release_id=%(release_id)s AND binding.source_id=assertion.source_id "
             " AND binding.private_source_record_id=assertion.source_record_id "
             " JOIN uec.source_records private_record "
             "  ON private_record.source_record_id=assertion.source_record_id "
             " AND private_record.source_id=assertion.source_id AND private_record.artifact_id=binding.artifact_id "
             " JOIN uec.source_records canonical_record "
             "  ON canonical_record.source_record_id=binding.canonical_source_record_id "
             " AND canonical_record.source_id=assertion.source_id AND canonical_record.artifact_id=binding.artifact_id "
             " JOIN release_facilities unambiguous "
             "  ON unambiguous.source_record_id=binding.canonical_source_record_id "
             " AND unambiguous.facility_id=binding.facility_id), "
             "name_support AS (SELECT * FROM direct_support UNION ALL SELECT * FROM bound_support) "
             "SELECT DISTINCT ON (endpoint.endpoint_id) endpoint.source_id,endpoint.identifier_type,"
             " endpoint.source_identifier,'organization'::text,endpoint.public_entity_id,"
             " support.canonical_source_record_id,assertion.assertion_value,assertion.assertion_role "
             "FROM pg_temp.uec_selected_organization_anchors endpoint "
             "JOIN approved_assertions assertion ON assertion.source_id=endpoint.source_id "
             " AND assertion.organization_id=endpoint.public_entity_id "
             "JOIN uec.source_entity_identifiers business_id "
             " ON business_id.identifier_id=assertion.identifier_id AND business_id.source_id=assertion.source_id "
             " AND business_id.source_record_id=assertion.source_record_id "
             " AND business_id.entity_type='organization' "
             " AND business_id.organization_id=endpoint.public_entity_id "
             " AND business_id.identifier_type=endpoint.identifier_type "
             " AND business_id.source_identifier=endpoint.source_identifier "
             "JOIN name_support support ON support.name_assertion_id=assertion.name_assertion_id "
             " AND support.source_id=assertion.source_id "
             " AND support.source_record_id=assertion.source_record_id "
             " AND support.canonical_source_record_id=endpoint.source_record_id "
             " AND support.facility_id=endpoint.facility_id "
             "WHERE uec.is_valid_italian_vat_identifier(endpoint.source_id,endpoint.identifier_type,endpoint.source_identifier) "
             "ORDER BY endpoint.endpoint_id,CASE assertion.assertion_role "
             " WHEN 'legal' THEN 0 WHEN 'business' THEN 1 ELSE 2 END,assertion.assertion_value")
    return query, {"release_id": release_id}


def _python_aphis_reference_select(release_id: str) -> tuple[str, dict[str, str]]:
    """Select typed APHIS refs through release review and narrow metadata clearance.

    The event payload and source-native identifiers are used only to establish
    the exact source-scoped match. Neither is part of the selected output.
    This clearance authorizes only the frozen APHIS reference DTO; full source
    and report publication remain behind the independent rights gates.
    """
    query = (f"WITH {EDGE_CTES.replace('$1', '%(release_id)s')} "
             "SELECT DISTINCT ON (endpoint.public_entity_id,event.source_record_id) "
             "endpoint.source_id,endpoint.identifier_type,endpoint.source_identifier,"
             "endpoint.entity_type,endpoint.public_entity_id,event.source_record_id,event.source_id,"
             "event.event_type,event.event_date,event.event_period,event.observed_at "
             "FROM eligible_source_endpoints endpoint "
             "JOIN uec.graph_evidence_links link "
             "  ON link.target_source_id=endpoint.source_id "
             f" AND link.target_identifier_type={_APHIS_EVIDENCE_LINK_IDENTIFIER_TYPE_SQL} "
             " AND link.target_source_identifier=endpoint.source_identifier "
             " AND link.match_method='exact_source_identifier' "
             "JOIN uec.graph_evidence_events event ON event.evidence_event_id=link.evidence_event_id "
             "JOIN uec.source_records evidence_record "
             "  ON evidence_record.source_record_id=event.source_record_id "
             " AND evidence_record.source_id=event.source_id "
             "JOIN uec.publication_review_release_current review "
             "  ON review.source_record_id=event.source_record_id "
             " AND review.release_id=%(release_id)s "
             "JOIN uec.raw_artifacts artifact ON artifact.artifact_id=evidence_record.artifact_id "
             "JOIN uec.graph_public_evidence_metadata_clearance_current clearance "
             " ON clearance.source_id=event.source_id "
             " AND clearance.profile=(SELECT profile FROM uec.releases WHERE release_id=%(release_id)s) "
             " AND clearance.release_id=%(release_id)s AND clearance.artifact_id=artifact.artifact_id "
             " AND clearance.artifact_sha256=artifact.sha256 "
             " AND clearance.scope_version='aphis-public-reference-metadata-v1' "
             " AND clearance.approved_fields=ARRAY["
             " 'source_id','evidence_type','event_date','event_period','observed_at','source_url','match_method'"
             "]::text[] "
             "WHERE endpoint.source_id='us.aphis' AND endpoint.entity_type='facility' "
             "  AND link.identity_scope='source_scoped' "
             "  AND review.publication_eligible=true AND review.privacy_screening_status='passed' "
             "  AND review.factual_review_status<>'rejected' AND review.maintainer_approval='approved' "
             "  AND NOT EXISTS (SELECT 1 FROM uec.public_access_restricted restricted "
             "                  WHERE restricted.source_record_id=event.source_record_id) "
             "  AND ((event.source_id='us.aphis.annual-reports' "
             "        AND event.event_type='annual_reports' "
             "        AND event.event_period ~ '^[0-9]{4}$') "
             "    OR (event.source_id='us.inspections' AND event.event_type='inspections' "
             "        AND event.event_date IS NOT NULL)) "
             "  AND NOT EXISTS (SELECT 1 FROM uec.observations observation "
             "                  JOIN uec.release_members member USING(observation_id) "
             "                  WHERE member.release_id=%(release_id)s "
             "                    AND observation.source_record_id=event.source_record_id) "
             "ORDER BY endpoint.public_entity_id,event.source_record_id,endpoint.identifier_type")
    return query, {"release_id": release_id}


def _insert_endpoint_batch(connection: Any, projection_id: uuid.UUID,
                           rows: Iterable[Any], endpoint_ids: dict[tuple[str, str, str, str, uuid.UUID], uuid.UUID],
                           organization_anchor_rows: list[tuple[Any, ...]] | None = None) -> tuple[int, int]:
    endpoints: list[tuple[Any, ...]] = []
    anchors: list[tuple[Any, ...]] = []
    for row in rows:
        key = (str(row[0]), str(row[1]), str(row[2]), str(row[3]), uuid.UUID(str(row[4])))
        endpoint_id = endpoint_ids.setdefault(key, uuid.uuid4())
        endpoints.append((projection_id, endpoint_id, key[4], key[3], key[0], key[1]))
        endpoint_anchors = _anchors(row[5])
        anchors.extend((projection_id, endpoint_id, record_id, facility_id)
                       for record_id, facility_id in endpoint_anchors)
        if organization_anchor_rows is not None and key[3] == "organization":
            organization_anchor_rows.extend(
                (endpoint_id, key[0], key[1], key[2], key[4], record_id, facility_id)
                for record_id, facility_id in endpoint_anchors
            )
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


def _insert_organization_label_batch(connection: Any, projection_id: uuid.UUID,
                                      rows: Iterable[Any],
                                      endpoint_ids: dict[tuple[str, str, str, str, uuid.UUID], uuid.UUID]) -> int:
    labels: list[tuple[Any, ...]] = []
    for row in rows:
        key = (str(row[0]), str(row[1]), str(row[2]), str(row[3]), uuid.UUID(str(row[4])))
        endpoint_id = endpoint_ids.get(key)
        source_record_id, display_name, role = uuid.UUID(str(row[5])), row[6], row[7]
        if endpoint_id is None or not isinstance(display_name, str) or not display_name.strip():
            continue
        labels.append((projection_id, endpoint_id, source_record_id, display_name.strip(), str(role)))
    if labels:
        with connection.cursor() as cursor:
            cursor.executemany(
                """INSERT INTO uec.graph_public_projection_org_labels
                   (projection_id,endpoint_id,label_source_record_id,display_name,assertion_role)
                   VALUES (%s,%s,%s,%s,%s) ON CONFLICT (projection_id,endpoint_id) DO NOTHING""",
                labels,
            )
    return len(labels)


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


def _aphis_reference_url(source_id: str, event_type: str) -> str | None:
    if source_id == "us.aphis.annual-reports" and event_type == "annual_reports":
        return "https://direct.aphis.usda.gov/awa/research-facility-report/annual-summary"
    if source_id == "us.inspections" and event_type == "inspections":
        return "https://direct.aphis.usda.gov/awa/search/inspection-reports"
    return None


def _insert_aphis_reference_batch(connection: Any, projection_id: uuid.UUID,
                                  rows: Iterable[Any],
                                  endpoint_ids: dict[tuple[str, str, str, str, uuid.UUID], uuid.UUID]) -> int:
    values: list[tuple[Any, ...]] = []
    for row in rows:
        endpoint_key = (str(row[0]), str(row[1]), str(row[2]), str(row[3]), uuid.UUID(str(row[4])))
        endpoint_id = endpoint_ids.get(endpoint_key)
        source_record_id = uuid.UUID(str(row[5]))
        source_id = str(row[6])
        event_type = str(row[7])
        source_url = _aphis_reference_url(source_id, event_type)
        if endpoint_id is None or source_url is None:
            continue
        event_date, event_period = row[8], row[9]
        if event_type == "annual_reports" and (not event_period or len(str(event_period)) != 4 or not str(event_period).isdigit()):
            continue
        if event_type == "inspections" and event_date is None:
            continue
        values.append((projection_id, endpoint_id, source_record_id, source_id,
                       event_type, event_date, event_period, row[10], source_url,
                       "exact_source_identifier"))
    if values:
        with connection.cursor() as cursor:
            cursor.executemany(
                """INSERT INTO uec.graph_public_projection_evidence_refs
                   (projection_id,endpoint_id,evidence_source_record_id,source_id,evidence_type,
                    event_date,event_period,observed_at,source_url,match_method)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                values,
            )
    return len(values)


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
        count = endpoint_count = anchor_count = evidence_reference_count = organization_label_count = 0
        endpoint_ids: dict[tuple[str, str, str, str, uuid.UUID], uuid.UUID] = {}
        try:
            with connection.transaction():
                # Resolve live release eligibility once, before the graph join
                # planner guard. Every cursor below uses the same key set.
                connection.execute(
                    "CREATE TEMP TABLE uec_selected_release_facility_anchors ON COMMIT DROP AS "
                    "SELECT DISTINCT release_id,source_record_id,facility_id "
                    "FROM uec.graph_public_live_facility_anchors_current WHERE release_id=%s",
                    (release_id,),
                )
                connection.execute(
                    "CREATE INDEX ON pg_temp.uec_selected_release_facility_anchors "
                    "(source_record_id,facility_id)"
                )
                connection.execute("ANALYZE pg_temp.uec_selected_release_facility_anchors")
                # The release/support CTEs have a known severe row-count
                # underestimation under nested loops. Keep the measured hash
                # join plan override transaction-local to this one build.
                connection.execute(PROJECTION_PLANNER_GUARD)
                connection.execute(
                    """CREATE TEMP TABLE uec_selected_organization_anchors (
                           endpoint_id UUID NOT NULL, source_id TEXT NOT NULL,
                           identifier_type TEXT NOT NULL, source_identifier TEXT NOT NULL,
                           public_entity_id UUID NOT NULL, source_record_id UUID NOT NULL,
                           facility_id UUID NOT NULL,
                           PRIMARY KEY (endpoint_id,source_record_id,facility_id)) ON COMMIT DROP"""
                )
                organization_anchor_rows: list[tuple[Any, ...]] = []
                endpoint_cursor = connection.cursor(name="uec_graph_projection_endpoints")
                endpoint_query, endpoint_parameters = _python_endpoint_select(release_id)
                endpoint_cursor.execute(_staged_anchor_query(endpoint_query), endpoint_parameters)
                while batch := endpoint_cursor.fetchmany(batch_size):
                    inserted_endpoints, inserted_anchors = _insert_endpoint_batch(
                        connection, projection_id, batch, endpoint_ids, organization_anchor_rows,
                    )
                    endpoint_count += inserted_endpoints
                    anchor_count += inserted_anchors
                endpoint_cursor.close()
                if organization_anchor_rows:
                    with connection.cursor() as cursor:
                        cursor.executemany(
                            """INSERT INTO pg_temp.uec_selected_organization_anchors
                               (endpoint_id,source_id,identifier_type,source_identifier,
                                public_entity_id,source_record_id,facility_id)
                               VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                            organization_anchor_rows,
                        )
                    organization_anchor_rows.clear()
                connection.execute("ANALYZE pg_temp.uec_selected_organization_anchors")
                label_cursor = connection.cursor(name="uec_graph_projection_organization_labels")
                label_query, label_parameters = _python_organization_label_select(release_id)
                label_cursor.execute(_staged_anchor_query(label_query), label_parameters)
                while batch := label_cursor.fetchmany(batch_size):
                    organization_label_count += _insert_organization_label_batch(
                        connection, projection_id, batch, endpoint_ids,
                    )
                label_cursor.close()
                evidence_cursor = connection.cursor(name="uec_graph_projection_aphis_references")
                evidence_query, evidence_parameters = _python_aphis_reference_select(release_id)
                evidence_cursor.execute(_staged_anchor_query(evidence_query), evidence_parameters)
                while batch := evidence_cursor.fetchmany(batch_size):
                    evidence_reference_count += _insert_aphis_reference_batch(
                        connection, projection_id, batch, endpoint_ids,
                    )
                evidence_cursor.close()
                cursor = connection.cursor(name="uec_graph_projection_source")
                query, parameters = _python_edge_select(release_id)
                cursor.execute(_staged_anchor_query(query), parameters)
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
            "aphis_evidence_reference_count": evidence_reference_count,
            "organization_label_count": organization_label_count,
            "edge_generation": edge_generation,
            "suppression_generation": suppression_generation}
