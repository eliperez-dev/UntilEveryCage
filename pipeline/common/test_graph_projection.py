from __future__ import annotations

import unittest
import uuid
import hashlib
from pathlib import Path
from unittest.mock import patch

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
    _python_edge_select,
    sanitize_signal_explanation,
)
from pipeline.common.real_private_graph import (
    D5_MATCHER_VERSION,
    D6_EDGE_RULESET_VERSION,
    GRAPH_MATERIALIZATION_FINGERPRINT,
    GRAPH_EDGE_MATERIALIZATION_VERSION,
    NATIVE_ENDPOINT_CONTRACT_VERSION,
)


class GraphProjectionTests(unittest.TestCase):
    def test_projection_selector_preserves_release_and_all_support_gates(self):
        self.assertIn("binding.release_id=$1", EDGE_CTES)
        self.assertIn("canonical_record.artifact_id=binding.artifact_id", EDGE_CTES)
        self.assertIn("private_record.artifact_id=binding.artifact_id", EDGE_CTES)
        self.assertIn("HAVING count(*)=count(record.source_record_id)", EDGE_CTES)
        self.assertIn("ambiguous_record_facilities", EDGE_CTES)
        self.assertIn("ambiguous_source_endpoints", EDGE_CTES)
        self.assertIn("asserted_facility.facility_id=rf.facility_id", EDGE_CTES)
        self.assertIn("i.identifier_type IN ('vat','vat_number','italian_vat','p_iva')", EDGE_CTES)
        self.assertNotIn("fiscal_code", EDGE_CTES)
        self.assertNotIn("codice_fiscale", EDGE_CTES)

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
        row = (
            edge_id, from_id, "facility", "it.synthetic", "permit", private_token,
            to_id, "facility", "it.synthetic", "permit", private_token,
            "operator", "inferred", 0.72, "medium", '{"group_contributions":{"identity":0.5}}',
            "d5-rules", "2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z", "d6-v1", False,
            [support_record],
            [{"source_record_id": str(support_record), "facility_id": str(anchor_from)}],
            [{"source_record_id": str(support_record), "facility_id": str(anchor_to)}],
            [{"source_record_id": str(support_record), "source_id": "it.synthetic",
              "artifact_id": str(artifact_id)}],
        )

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
        inserted = _insert_batch(connection, uuid.uuid4(), "release-safe", [row])
        self.assertEqual(inserted, 1)
        self.assertEqual(len(connection.fake_cursor.calls), 3)
        sql = "\n".join(query for query, _values in connection.fake_cursor.calls)
        bound_values = repr([values for _query, values in connection.fake_cursor.calls])
        self.assertIn("graph_public_projection_edges", sql)
        self.assertNotIn(private_token, bound_values)

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

    def test_materialization_fingerprint_is_explicitly_versioned(self):
        self.assertEqual(PROJECTION_VERSION, "graph-release-projection-v1")
        self.assertTrue(all((D5_MATCHER_VERSION, D6_EDGE_RULESET_VERSION,
                             GRAPH_EDGE_MATERIALIZATION_VERSION,
                             NATIVE_ENDPOINT_CONTRACT_VERSION)))
        self.assertEqual(len(GRAPH_MATERIALIZATION_FINGERPRINT), 64)
        versions = [GRAPH_EDGE_MATERIALIZATION_VERSION, D5_MATCHER_VERSION,
                    D6_EDGE_RULESET_VERSION, NATIVE_ENDPOINT_CONTRACT_VERSION]
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
        }
        validator = {**_PRIVATE_GRAPH_REQUIRED_PRIVILEGES,
                     **_PRIVATE_GRAPH_REQUIRED_READ_PRIVILEGES}
        for table, grant in grants.items():
            with self.subTest(table=table):
                self.assertEqual(validator[table], set(grant.split(", ")))
                self.assertIn(f"GRANT {grant} ON uec.{table}", migration)

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
