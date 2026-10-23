from __future__ import annotations

import unittest
import uuid
import hashlib
import re
import os
from pathlib import Path
from unittest.mock import patch

import psycopg

from pipeline.common import graph_persistence
from pipeline.common.graph_persistence import (
    _PRIVATE_GRAPH_REQUIRED_PRIVILEGES,
    _PRIVATE_GRAPH_REQUIRED_READ_PRIVILEGES,
)
from pipeline.common.graph_projection import (
    EDGE_CTES,
    PROJECTION_PLANNER_GUARD,
    PROJECTION_VERSION,
    _insert_batch,
    _insert_endpoint_batch,
    _python_endpoint_select,
    _python_edge_select,
    _python_aphis_reference_select,
    _python_organization_label_select,
    _insert_organization_label_batch,
    _insert_aphis_reference_batch,
    sanitize_signal_explanation,
)
from pipeline.common.real_private_graph import (
    D5_MATCHER_VERSION,
    D6_EDGE_RULESET_VERSION,
    SHARED_BUSINESS_NAME_RULESET_VERSION,
    GRAPH_MATERIALIZATION_FINGERPRINT,
    GRAPH_EDGE_MATERIALIZATION_VERSION,
    NATIVE_ENDPOINT_CONTRACT_VERSION,
)


class GraphProjectionTests(unittest.TestCase):
    def test_080_runtime_connection_view_matches_v3_business_qualification(self):
        migration = (Path(__file__).resolve().parents[1] / "migrations" /
                     "080_graph_public_evidence_references.sql").read_text(encoding="utf-8")
        connection_view = re.search(
            r"CREATE OR REPLACE VIEW uec\.graph_public_connections_current AS(.*?)"
            r"COMMENT ON VIEW uec\.graph_public_connections_current",
            migration, flags=re.IGNORECASE | re.DOTALL,
        )
        self.assertIsNotNone(connection_view)
        view_sql = connection_view.group(1)
        self.assertIn(f"b.projection_version='{PROJECTION_VERSION}'", view_sql)
        self.assertIn("graph_public_organization_endpoints_current eligible", view_sql)
        self.assertIn("eligible.endpoint_id=e.from_endpoint_id", view_sql)
        self.assertIn("eligible.endpoint_id=e.to_endpoint_id", view_sql)
        self.assertIn("b.suppression_generation=suppression.generation", view_sql)
        label_query, _ = _python_organization_label_select("selected-release")
        self.assertIn("business_id.source_identifier=endpoint.source_identifier", label_query)
        self.assertIn("business_name.assertion_role IN ('legal','business','operator')", EDGE_CTES)
        organization_ids = EDGE_CTES.split("AND i.identifier_type IN (", 1)[1].split(
            ")\n    AND i.organization_id", 1)[0]
        self.assertNotIn("'siret'", organization_ids)
        self.assertIn("DISTINCT ON (eligible.release_id,eligible.organization_id)", migration)
        self.assertIn("build.suppression_generation=suppression.generation", migration)
        endpoint_select, _ = _python_endpoint_select("selected-release")
        self.assertIn("FROM eligible_source_endpoints", endpoint_select)
        self.assertNotIn("graph_public_projection_edges", endpoint_select)

    @unittest.skipUnless(
        os.environ.get("UEC_GRAPH_ACCEPTANCE_DATABASE_URL"),
        "set UEC_GRAPH_ACCEPTANCE_DATABASE_URL after 080 and v3 projection are applied",
    )
    def test_post_migration_database_projection_acceptance_is_read_only(self):
        expected_database = os.environ.get("UEC_GRAPH_DATABASE_NAME", "")
        self.assertTrue(expected_database)
        with psycopg.connect(os.environ["UEC_GRAPH_ACCEPTANCE_DATABASE_URL"]) as connection:
            connection.execute("SET TRANSACTION READ ONLY")
            self.assertEqual(connection.execute("SELECT current_database()").fetchone()[0],
                             expected_database)
            view_definition = connection.execute(
                "SELECT pg_get_viewdef('uec.graph_public_connections_current'::regclass,true)"
            ).fetchone()[0]
            self.assertIn(PROJECTION_VERSION, view_definition)
            active_projection_count = connection.execute(
                """SELECT count(*) FROM uec.graph_public_projection_builds
                   WHERE active AND status='completed' AND projection_version=%s""",
                (PROJECTION_VERSION,),
            ).fetchone()[0]
            self.assertGreater(active_projection_count, 0)
            duplicate_org_labels = connection.execute(
                """SELECT count(*) FROM (
                     SELECT release_id,organization_id
                     FROM uec.graph_public_organization_labels_current
                     GROUP BY release_id,organization_id HAVING count(*)>1
                   ) duplicates"""
            ).fetchone()[0]
            duplicate_org_endpoints = connection.execute(
                """SELECT count(*) FROM (
                     SELECT release_id,endpoint_id
                     FROM uec.graph_public_organization_endpoints_current
                     GROUP BY release_id,endpoint_id HAVING count(*)>1
                   ) duplicates"""
            ).fetchone()[0]
            duplicate_connection_rows = connection.execute(
                """SELECT count(*) FROM (
                     SELECT release_id,connection_edge_id
                     FROM uec.graph_public_connections_current
                     GROUP BY release_id,connection_edge_id HAVING count(*)>1
                   ) duplicates"""
            ).fetchone()[0]
            evidence_counts = connection.execute(
                """SELECT count(*),
                          count(*) FILTER (WHERE NOT EXISTS (
                            SELECT 1 FROM uec.graph_public_projection_edges edge
                            WHERE edge.projection_id=reference.projection_id
                              AND (edge.from_endpoint_id=reference.endpoint_id
                                   OR edge.to_endpoint_id=reference.endpoint_id)
                          ))
                   FROM uec.graph_public_evidence_references_current current_ref
                   JOIN uec.graph_public_projection_evidence_refs reference
                     USING (evidence_ref_id)"""
            ).fetchone()
        self.assertEqual(duplicate_org_labels, 0)
        self.assertEqual(duplicate_org_endpoints, 0)
        self.assertEqual(duplicate_connection_rows, 0)
        if os.environ.get("UEC_GRAPH_ACCEPTANCE_REQUIRE_APHIS_EVIDENCE") == "1":
            self.assertGreater(evidence_counts[0], 0)
            self.assertGreater(evidence_counts[1], 0)

    def test_projection_selector_preserves_release_and_all_support_gates(self):
        self.assertIn("binding.release_id=$1", EDGE_CTES)
        self.assertIn("canonical_record.artifact_id=binding.artifact_id", EDGE_CTES)
        self.assertIn("private_record.artifact_id=binding.artifact_id", EDGE_CTES)
        self.assertIn("HAVING count(*)=count(record.source_record_id)", EDGE_CTES)
        self.assertIn("ambiguous_record_facilities", EDGE_CTES)
        self.assertIn("ambiguous_source_endpoints", EDGE_CTES)
        self.assertIn("asserted_facility.facility_id=rf.facility_id", EDGE_CTES)
        self.assertIn("i.identifier_type IN (", EDGE_CTES)
        self.assertIn("business_name.assertion_role IN ('legal','business','operator')", EDGE_CTES)
        self.assertNotIn("operator-name'", EDGE_CTES)
        self.assertIn("graph_source_name_assertions", EDGE_CTES)
        self.assertNotIn("fiscal_code", EDGE_CTES)
        self.assertNotIn("codice_fiscale", EDGE_CTES)

    def test_projection_selector_uses_portable_uuid_aggregate_after_uniqueness_gate(self):
        support_records = EDGE_CTES.split("release_support_records AS MATERIALIZED (", 1)[1].split(
            "),\nedge_support_refs", 1)[0]
        self.assertIn("array_agg(DISTINCT canonical_source_record_id", support_records)
        self.assertIn("ORDER BY canonical_source_record_id", support_records)
        self.assertIn("HAVING count(DISTINCT canonical_source_record_id)=1", support_records)
        self.assertNotIn("min(canonical_source_record_id)", support_records)

    def test_endpoint_ambiguity_join_qualifies_duplicate_left_side_columns(self):
        endpoint_cte = EDGE_CTES.split("eligible_source_endpoints AS MATERIALIZED (", 1)[1].split(
            "),\nedges AS", 1)[0]
        self.assertIn("ON ambiguous.source_id=target.source_id", endpoint_cte)
        self.assertIn("ambiguous.identifier_type=target.identifier_type", endpoint_cte)
        self.assertNotIn("USING (source_id, identifier_type, source_identifier, entity_type)", endpoint_cte)

    def test_projection_signal_sanitizer_only_keeps_known_codes_and_typed_values(self):
        safe = sanitize_signal_explanation({
            "group_contributions": {
                "identity": 0.7, "address": "residential address", "name": 0.2,
                "contact": True, "temporal": float("inf"),
            },
            "contradictions": [
                {"name": "conflicting_identifier", "weight": 0.4, "value": True,
                 "details": {"identifier": "private token"}},
                {"name": "address", "group": "private", "weight": 1.0},
            ],
        })
        self.assertEqual(safe, {
            "group_contributions": {"identity": 0.7},
            "contradictions": [{"name": "conflicting_identifier", "group": "contradiction",
                                "weight": 0.4, "value": True}],
        })
        self.assertNotIn("private token", str(safe))
        self.assertNotIn("residential address", str(safe))

    def test_projection_batch_uses_cursor_executemany_and_never_persists_raw_ids(self):
        edge_id, from_id, to_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        support_record, artifact_id = uuid.uuid4(), uuid.uuid4()
        anchor_from, anchor_to = uuid.uuid4(), uuid.uuid4()
        private_token = "private-endpoint-token"
        endpoint_ids = {
            ("it.synthetic", "permit", private_token, "facility", from_id): uuid.uuid4(),
            ("it.synthetic", "permit", private_token, "facility", to_id): uuid.uuid4(),
        }
        row = (edge_id, from_id, "facility", "it.synthetic", "permit", private_token,
               to_id, "facility", "it.synthetic", "permit", private_token,
               "operator", "inferred", 0.72, "medium", '{"group_contributions":{"identity":0.5}}',
               "d5-rules", "2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z", "d6-v1", False,
               [support_record], [
                   {"source_record_id": str(support_record), "source_id": "it.synthetic",
                    "artifact_id": str(artifact_id)},
               ])

        class FakeCursor:
            def __init__(self):
                self.calls = []

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def executemany(self, query, values):
                self.calls.append((query, values))

        class FakeConnection:
            def __init__(self):
                self.fake_cursor = FakeCursor()

            def cursor(self):
                return self.fake_cursor

        connection = FakeConnection()
        inserted = _insert_batch(connection, uuid.uuid4(), "release-safe", [row], endpoint_ids)
        self.assertEqual(inserted, 1)
        self.assertEqual(len(connection.fake_cursor.calls), 2)
        sql = "\n".join(query for query, _values in connection.fake_cursor.calls)
        bound_values = repr([values for _query, values in connection.fake_cursor.calls])
        self.assertIn("graph_public_projection_edges", sql)
        self.assertNotIn(private_token, bound_values)
        edge_query, edge_rows = connection.fake_cursor.calls[0]
        columns = edge_query.split("VALUES", 1)[0].rsplit("(", 1)[1].rstrip()
        values_clause = edge_query.split("VALUES", 1)[1].split(")", 1)[0]
        self.assertEqual(len(edge_rows[0]), 23)
        self.assertEqual(len(columns.split(",")), 23)
        self.assertEqual(values_clause.count("%s"), 23)
        self.assertEqual(values_clause.split(",").index("%s::jsonb"), 17)

    def test_projection_planner_guard_is_transaction_local(self):
        self.assertEqual(PROJECTION_PLANNER_GUARD, "SET LOCAL enable_nestloop=off")
        source = (Path(__file__).resolve().with_name("graph_projection.py")).read_text(encoding="utf-8")
        self.assertIn("connection.execute(PROJECTION_PLANNER_GUARD)", source)
        self.assertNotIn('connection.execute("SET enable_nestloop=off")', source)

    def test_projection_selector_uses_named_psycopg_release_binding(self):
        query, parameters = _python_edge_select("selected-release")
        self.assertNotIn("$1", query)
        self.assertEqual(query.count("%(release_id)s"), 2)
        self.assertEqual(parameters, {"release_id": "selected-release"})

    def test_aphis_reference_selector_is_exact_and_selected_release_gated(self):
        query, parameters = _python_aphis_reference_select("selected-release")
        self.assertNotIn("event.release_id", query)
        self.assertNotIn("event.storage_state", query)
        self.assertNotIn("event.publication_status", query)
        self.assertIn("link.match_method='exact_source_identifier'", query)
        self.assertIn("review.source_record_id=event.source_record_id", query)
        self.assertIn("review.maintainer_approval='approved'", query)
        self.assertIn("rights.redistribution_status='cleared'", query)
        self.assertIn("rights.artifact_sha256=artifact.sha256", query)
        self.assertIn("DISTINCT ON (source_id,profile,release_id,artifact_id)", query)
        self.assertIn("decided_at DESC,source_rights_decision_id DESC", query)
        self.assertIn("endpoint.source_id='us.aphis'", query)
        self.assertNotIn("event_payload", query)
        self.assertNotIn("raw_fields", query)
        self.assertEqual(parameters, {"release_id": "selected-release"})

    def test_public_aphis_reference_batch_uses_only_typed_allowlisted_metadata(self):
        endpoint = uuid.uuid4()
        public_id = uuid.uuid4()
        private_identifier = "APHIS-private-native-id"
        key = ("us.aphis", "aphis_certificate_number", private_identifier, "facility", public_id)
        endpoint_ids = {key: endpoint}
        annual_record = uuid.uuid4()
        inspection_record = uuid.uuid4()
        rows = [
            (*key[:4], public_id, annual_record, "us.aphis.annual-reports", "annual_reports",
             None, "2025", "2026-10-01T00:00:00Z"),
            (*key[:4], public_id, inspection_record, "us.inspections", "inspections",
             "2026-10-03", None, "2026-10-04T00:00:00Z"),
            (*key[:4], public_id, uuid.uuid4(), "us.inspections", "annual_reports",
             None, "2025", "2026-10-04T00:00:00Z"),
        ]

        class Cursor:
            def __init__(self): self.calls = []
            def __enter__(self): return self
            def __exit__(self, *_args): return False
            def executemany(self, query, values): self.calls.append((query, values))
        class Connection:
            def __init__(self): self.cursor_value = Cursor()
            def cursor(self): return self.cursor_value

        connection = Connection()
        count = _insert_aphis_reference_batch(connection, uuid.uuid4(), rows, endpoint_ids)
        self.assertEqual(count, 2)
        query, values = connection.cursor_value.calls[0]
        self.assertIn("graph_public_projection_evidence_refs", query)
        self.assertEqual(len(values[0]), 10)
        encoded = repr(values)
        self.assertNotIn(private_identifier, encoded)
        self.assertIn("research-facility-report/annual-summary", encoded)
        self.assertIn("search/inspection-reports", encoded)

    def test_materialization_fingerprint_is_explicitly_versioned(self):
        self.assertEqual(PROJECTION_VERSION, "graph-release-projection-v3")
        self.assertTrue(all((D5_MATCHER_VERSION, D6_EDGE_RULESET_VERSION,
                             SHARED_BUSINESS_NAME_RULESET_VERSION,
                             GRAPH_EDGE_MATERIALIZATION_VERSION,
                             NATIVE_ENDPOINT_CONTRACT_VERSION)))
        self.assertEqual(len(GRAPH_MATERIALIZATION_FINGERPRINT), 64)
        versions = [GRAPH_EDGE_MATERIALIZATION_VERSION, D5_MATCHER_VERSION,
                    D6_EDGE_RULESET_VERSION, SHARED_BUSINESS_NAME_RULESET_VERSION,
                    NATIVE_ENDPOINT_CONTRACT_VERSION]
        expected = hashlib.sha256("|".join(versions).encode("utf-8")).hexdigest()
        self.assertEqual(GRAPH_MATERIALIZATION_FINGERPRINT, expected)
        for index in range(len(versions)):
            changed = versions.copy()
            changed[index] += "-next"
            self.assertNotEqual(
                hashlib.sha256("|".join(changed).encode("utf-8")).hexdigest(), expected,
            )

    def test_projection_migration_grants_match_private_writer_validator(self):
        migration = (Path(__file__).resolve().parents[1] / "migrations" / "077_graph_release_projection.sql").read_text(
            encoding="utf-8",
        )
        grants = {
            "graph_edge_materialization_runs": "SELECT, INSERT, UPDATE",
            "graph_projection_generation": "SELECT",
            "graph_public_projection_builds": "SELECT, INSERT, UPDATE",
            "graph_public_projection_edges": "SELECT, INSERT",
            "graph_public_projection_edge_supports": "SELECT, INSERT",
            "graph_public_projection_endpoint_anchors": "SELECT, INSERT",
            "graph_public_projection_evidence_refs": "SELECT, INSERT",
            "graph_public_projection_org_labels": "SELECT, INSERT",
            "graph_source_name_assertions": "SELECT, INSERT",
        }
        validator = {**_PRIVATE_GRAPH_REQUIRED_PRIVILEGES,
                     **_PRIVATE_GRAPH_REQUIRED_READ_PRIVILEGES}
        for table, grant in grants.items():
            with self.subTest(table=table):
                self.assertEqual(validator[table], set(grant.split(", ")))
                grant_migration = migration if table not in {"graph_public_projection_evidence_refs", "graph_public_projection_org_labels", "graph_source_name_assertions"} else (
                    Path(__file__).resolve().parents[1] / "migrations" / "080_graph_public_evidence_references.sql"
                ).read_text(encoding="utf-8")
                self.assertIn(f"GRANT {grant} ON uec.{table}", grant_migration)
        evidence_migration = (Path(__file__).resolve().parents[1] / "migrations" / "080_graph_public_evidence_references.sql").read_text(encoding="utf-8")
        self.assertIn("CREATE OR REPLACE VIEW uec.graph_public_evidence_references_current", evidence_migration)
        self.assertIn("review.source_record_id=evidence_record.source_record_id", evidence_migration)
        self.assertIn("rights.redistribution_status='cleared'", evidence_migration)
        self.assertIn("DISTINCT ON (source_id,profile,release_id,artifact_id)", evidence_migration)
        self.assertIn("decided_at DESC,source_rights_decision_id DESC", evidence_migration)
        self.assertIn("public_access_restricted", evidence_migration)
        self.assertIn("CREATE OR REPLACE VIEW uec.graph_public_organization_labels_current", evidence_migration)
        self.assertIn("CREATE OR REPLACE VIEW uec.graph_public_organization_endpoints_current", evidence_migration)
        self.assertIn("GRANT SELECT ON uec.graph_public_organization_endpoints_current TO uec_api_runtime", evidence_migration)
        self.assertNotIn("GRANT SELECT ON uec.graph_source_name_assertions TO uec_api_runtime", evidence_migration)
        self.assertIn("build.suppression_generation=suppression.generation", evidence_migration)
        self.assertIn("DISTINCT ON (eligible.release_id,eligible.organization_id)", evidence_migration)
        self.assertIn("projection_version='graph-release-projection-v3'", evidence_migration)
        for table in ("publication_review_release_current", "source_rights_decisions", "public_access_restricted"):
            with self.subTest(review_gate=table):
                self.assertEqual(_PRIVATE_GRAPH_REQUIRED_READ_PRIVILEGES[table], {"SELECT"})
                self.assertIn(f"GRANT SELECT ON uec.{table}", evidence_migration)
        self.assertIn("label_source_record_id", evidence_migration)
        self.assertIn("rights.artifact_sha256=artifact.sha256", evidence_migration)
        normalized = (Path(__file__).resolve().parents[1] / "migrations" / "078_normalized_graph_projection_endpoints.sql").read_text(encoding="utf-8")
        self.assertIn("CREATE OR REPLACE VIEW uec.graph_public_connections_current", normalized)
        self.assertNotIn("DROP VIEW uec.graph_public_connections_current", normalized)
        migration_077 = (Path(__file__).resolve().parents[1] / "migrations" / "077_graph_release_projection.sql").read_text(encoding="utf-8")
        indexes_077 = set(re.findall(r"(?im)^CREATE\s+(?:UNIQUE\s+)?INDEX\s+([a-z_][a-z0-9_]*)", migration_077))
        indexes_078 = set(re.findall(r"(?im)^CREATE\s+(?:UNIQUE\s+)?INDEX\s+([a-z_][a-z0-9_]*)", normalized))
        self.assertTrue(indexes_077)
        self.assertTrue(indexes_078)
        self.assertTrue(indexes_077.isdisjoint(indexes_078), indexes_077 & indexes_078)
        for table in ("graph_public_projection_endpoints", "graph_public_projection_anchors"):
            self.assertEqual(validator[table], {"SELECT", "INSERT"})
        self.assertIn(f"GRANT SELECT, INSERT ON uec.{table}", normalized)

    def test_endpoint_and_anchor_rows_are_inserted_once_per_qualified_selector(self):
        projection_id = uuid.uuid4()
        public_id, record_id, facility_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        private_value = "private-token"
        rows = [
            ("source-a", "permit", private_value, "facility", public_id,
             [{"source_record_id": str(record_id), "facility_id": str(facility_id)}]),
            ("source-b", "permit", private_value, "facility", public_id,
             [{"source_record_id": str(record_id), "facility_id": str(facility_id)}]),
            ("source-a", "vat", private_value, "organization", public_id,
             [{"source_record_id": str(record_id), "facility_id": str(facility_id)}]),
        ]

        class Cursor:
            def __init__(self): self.calls = []
            def __enter__(self): return self
            def __exit__(self, *_args): return False
            def executemany(self, query, values): self.calls.append((query, values))
        class Connection:
            def __init__(self): self.cursor_value = Cursor()
            def cursor(self): return self.cursor_value

        connection = Connection()
        mapping = {}
        endpoint_count, anchor_count = _insert_endpoint_batch(connection, projection_id, rows, mapping)
        self.assertEqual((endpoint_count, anchor_count), (3, 3))
        self.assertEqual(len(mapping), 3)
        self.assertEqual(len(connection.cursor_value.calls[0][1]), 3)
        self.assertEqual(len(connection.cursor_value.calls[1][1]), 3)
        self.assertNotIn(private_value, repr(connection.cursor_value.calls))

    def test_endpoint_selector_is_separate_and_parameterized(self):
        query, parameters = _python_endpoint_select("selected-release")
        self.assertIn("FROM eligible_source_endpoints", query)
        self.assertNotIn("source_identifier", query.split("SELECT", 1)[1].split("FROM", 1)[0])
        self.assertEqual(parameters, {"release_id": "selected-release"})

    def test_organization_labels_require_source_assertions_and_use_safe_projection(self):
        query, parameters = _python_organization_label_select("selected-release")
        self.assertIn("graph_source_name_assertions", query)
        self.assertIn("business_id.identifier_id=assertion.identifier_id", query)
        self.assertIn("map_facilities_public_discovery_read_model approved", query)
        self.assertNotIn("organizations.canonical_name", query)
        self.assertEqual(parameters, {"release_id": "selected-release"})
        public_id, private_identifier = uuid.uuid4(), "business-native-identifier"
        key = ("source.sample", "company_number", private_identifier, "organization", public_id)
        endpoint_id = uuid.uuid4()
        label_source_record_id = uuid.uuid4()

        class Cursor:
            def __init__(self): self.calls = []
            def __enter__(self): return self
            def __exit__(self, *_args): return False
            def executemany(self, sql, values): self.calls.append((sql, values))
        class Connection:
            def __init__(self): self.value = Cursor()
            def cursor(self): return self.value

        connection = Connection()
        count = _insert_organization_label_batch(
            connection, uuid.uuid4(),
            [(key[0], key[1], private_identifier, key[3], public_id, label_source_record_id,
              "Example Trading Ltd", "business")],
            {key: endpoint_id},
        )
        self.assertEqual(count, 1)
        self.assertNotIn(private_identifier, repr(connection.value.calls))
        self.assertIn("graph_public_projection_org_labels", connection.value.calls[0][0])

    def test_graph_live_membership_lookup_keeps_live_view_as_eligibility_authority(self):
        migration = (Path(__file__).resolve().parents[1] / "migrations" / "079_graph_live_membership_lookup.sql").read_text(encoding="utf-8")
        sql = migration.casefold()
        self.assertIn(
            "create index if not exists public_discovery_read_model_graph_membership_idx",
            sql,
        )
        self.assertIn(
            "on uec.public_discovery_read_model_rows (release_id, source_record_id, facility_id)",
            sql,
        )
        self.assertIn("create or replace view uec.graph_public_connections_current", sql)
        self.assertNotIn("create or replace view uec.map_facilities_public_discovery_read_model", sql)
        self.assertNotIn("create view uec.map_facilities_public_discovery_read_model", sql)

        # Raw rows only enumerate facility keys. A candidate row cannot pass a
        # support or anchor gate without an exact match in the unchanged live map.
        self.assertEqual(sql.count("from uec.public_discovery_read_model_rows candidate"), 2)
        self.assertGreaterEqual(
            sql.count("from uec.map_facilities_public_discovery_read_model current_support"),
            2,
        )
        self.assertEqual(
            sql.count("from uec.map_facilities_public_discovery_read_model current_anchor"),
            2,
        )
        self.assertEqual(sql.count("offset 0"), 4)
        self.assertIn("candidate.release_id=e.release_id", sql)
        self.assertIn("candidate.source_record_id=support.source_record_id", sql)
        self.assertIn("current_support.facility_id=candidate.facility_id", sql)
        self.assertIn("current_support.source_record_id=support.source_record_id", sql)
        self.assertIn("current_anchor.facility_id=anchor.facility_id", sql)
        self.assertIn("current_anchor.source_record_id=anchor.source_record_id", sql)

        # Preserve all-support source/artifact equality and endpoint-qualified
        # anchor checks from 078; no endpoint can borrow another endpoint's anchors.
        self.assertIn("record.source_id=support.source_id", sql)
        self.assertIn("record.artifact_id=support.artifact_id", sql)
        self.assertIn("record.source_record_id is null or not exists", sql)
        self.assertIn("anchor.projection_id=e.projection_id", sql)
        self.assertIn("anchor.endpoint_id=e.from_endpoint_id", sql)
        self.assertIn("anchor.endpoint_id=e.to_endpoint_id", sql)
        for gate in (
            "b.active and b.status='completed'",
            "b.projection_version='graph-release-projection-v2'",
            "b.edge_generation=generation.generation",
            "b.release_manifest_sha256=manifest.manifest_sha256",
            "release.test_only is not true",
            "release.status='promoted' or history.release_id is not null",
        ):
            with self.subTest(gate=gate):
                self.assertIn(gate, sql)

    def test_completion_check_skips_staging_only_for_completed_matching_fingerprint(self):
        run_id = uuid.uuid4()

        class FakeConnection:
            def __init__(self, status):
                self.status = status
                self.query = None
                self.parameters = None

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def execute(self, query, parameters):
                self.query = query
                self.parameters = parameters
                return self

            def fetchone(self):
                return None if self.status is None else (
                    run_id, self.status, 3, 1, 5, 9, {"rows_staged": 8},
                )

        with patch.object(graph_persistence, "require_private_graph_target"), \
             patch.object(graph_persistence, "iter_graph_candidate_handoff",
                          return_value=({"source_id": "synthetic.graph"}, iter(()), "a" * 64, 12)), \
             patch.object(graph_persistence, "_validate_private_graph_writer"):
            connection = FakeConnection("completed")
            with patch.object(graph_persistence.psycopg, "connect", return_value=connection):
                result = graph_persistence.completed_edge_materialization(
                    "postgresql://local", ".", private_target=("safe_db", "private-graph-materialization-v1"),
                    fingerprint="b" * 64,
                )
        self.assertEqual(result["status"], "already_present")
        self.assertTrue(result["staging_skipped"])
        self.assertEqual(result["edge_count"], 9)
        self.assertEqual(result["matcher"]["rows_staged"], 8)
        self.assertIn("materialization_fingerprint=%s", connection.query)
        self.assertEqual(connection.parameters, ("synthetic.graph", "a" * 64, "b" * 64))

        for status in (None, "in_progress", "failed"):
            with self.subTest(status=status):
                incomplete = FakeConnection(status)
                with patch.object(graph_persistence, "require_private_graph_target"), \
                     patch.object(graph_persistence, "iter_graph_candidate_handoff",
                                  return_value=({"source_id": "synthetic.graph"}, iter(()), "a" * 64, 12)), \
                     patch.object(graph_persistence, "_validate_private_graph_writer"), \
                     patch.object(graph_persistence.psycopg, "connect", return_value=incomplete):
                    result = graph_persistence.completed_edge_materialization(
                        "postgresql://local", ".",
                        private_target=("safe_db", "private-graph-materialization-v1"),
                        fingerprint="b" * 64,
                    )
                self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
