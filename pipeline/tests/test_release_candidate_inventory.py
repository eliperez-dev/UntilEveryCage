from __future__ import annotations

import unittest
from datetime import datetime, timezone

from pipeline.scripts.diagnostics import build_release_candidate_inventory as inventory


class _Result:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0]


class _ReadOnlyConnection:
    def __init__(self, *, available=(), now=None):
        self.available = set(available)
        self.now = now or datetime(2026, 10, 4, tzinfo=timezone.utc)
        self.statements = []

    def execute(self, query, parameters=()):
        self.statements.append(query)
        if query.startswith("SET TRANSACTION"):
            return _Result([])
        if "SELECT transaction_timestamp()" in query:
            return _Result([(self.now,)])
        if "release-candidate-inventory: relation availability" in query:
            return _Result([(name, name in self.available) for name in parameters[0]])
        if "release-candidate-inventory: latest private source snapshots" in query:
            return _Result([])
        if "release-candidate-inventory: taxonomy coverage" in query:
            return _Result([])
        if "release-candidate-inventory: taxonomy mapping" in query:
            return _Result([])
        if "release-candidate-inventory: crosswalk hashes" in query:
            return _Result([])
        if "release-candidate-inventory: source geometry" in query:
            return _Result([])
        if "release-candidate-inventory: current source-private" in query:
            return _Result([])
        if "release-candidate-inventory: release counts only" in query:
            return _Result([])
        if "release-candidate-inventory: physical release" in query:
            return _Result([(0, 0, 0, 0)])
        if "release-candidate-inventory: private graph counts" in query:
            return _Result([])
        if query.lstrip().startswith("SELECT count(*) FROM uec."):
            return _Result([(0,)])
        raise AssertionError(f"unexpected query in unit test: {query[:90]}")


class ReleaseCandidateInventoryTests(unittest.TestCase):
    def test_read_only_transaction_is_first_and_no_snapshot_is_not_called_measured_zero(self):
        available = set(inventory.REQUIRED_RELATIONS)
        connection = _ReadOnlyConnection(available=available)
        report = inventory.build_inventory(connection)
        self.assertTrue(connection.statements[0].startswith("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        self.assertEqual(report["status"], "no_latest_private_snapshots")
        self.assertEqual(report["source_scope"]["latest_imported_source_snapshot_count"], 0)
        self.assertEqual(report["candidate_release"]["release_id"], None)
        self.assertEqual(report["candidate_release"]["member_rows"], 0)
        self.assertFalse(report["publication"]["authorized"])

    def test_repeatable_content_hash_excludes_read_clock_and_has_no_payload_fields(self):
        available = set(inventory.REQUIRED_RELATIONS)
        first = inventory.build_inventory(_ReadOnlyConnection(available=available))
        second = inventory.build_inventory(_ReadOnlyConnection(
            available=available,
            now=datetime(2026, 10, 4, 0, 1, tzinfo=timezone.utc),
        ))
        self.assertEqual(first["inventory_sha256"], second["inventory_sha256"])
        text = inventory._canonical_bytes(first).decode("utf-8").casefold()
        for forbidden in ('"address"', '"name"', '"latitude"', '"longitude"', '"source_identifier"', '"raw_fields"'):
            self.assertNotIn(forbidden, text)

    def test_missing_schema_is_explicit_and_does_not_invent_zero_counts(self):
        report = inventory.build_inventory(_ReadOnlyConnection())
        self.assertEqual(report["status"], "blocked_schema_incomplete")
        self.assertIn("real_preview.candidates", report["schema"]["missing_required_relations"])
        self.assertNotIn("source_scope", report)

    def test_source_report_keeps_only_aggregate_safe_provenance_and_flags(self):
        counts = {
            key: 2 for key in (
                "input_count", "accepted_count", "quarantined_count", "out_of_scope_count",
                "imported_observation_count", "facility_count", "numeric_coordinate_count",
                "coarse_placeable_count", "unmapped_count", "api_listable_count", "map_visible_count",
                "public_rows", "physical_observation_count", "physical_candidate_count",
                "source_coordinate_candidates", "coarse_location_candidates",
                "display_coordinate_candidates", "unmapped_observations",
            )
        }
        row = {
            "source_id": "test.source",
            "snapshot_sha256": "a" * 64,
            "source_artifact_sha256": "b" * 64,
            "normalized_sha256": "c" * 64,
            "source_url": "https://example.gov/data.csv?token=not-copied",
            "retrieved_at": datetime(2026, 10, 4, tzinfo=timezone.utc),
            "adapter_version": "adapter-v1",
            "schema_version": "schema-v1",
            "manifest_artifact_sha256": "b" * 64,
            "manifest_normalized_sha256": "c" * 64,
            "manifest_normalized_rows": 2,
            "manifest_source_url": "https://example.gov/data.csv?other-query-is-not-copied",
            "manifest_retrieved_at": datetime(2026, 10, 4, tzinfo=timezone.utc),
            "manifest_code_version": "code-v1",
            "manifest_config_version": "config-v1",
            "idempotent_replay": False,
            "runtime_details": {
                "fresh_live_run": False,
                "processing_mode": "archived_replay",
                "source_specific_counts": {
                    "rejected_rows": 1,
                    "activity_counts": {"source facility name": 1},
                    "coordinate_quarantine_reasons": {"invalid_range": 1, "private name": 99},
                },
                "quarantine_reasons": {"invalid_date": 1, "source facility name": 3},
                "source_rows": [{"name": "private facility", "address": "secret"}],
            },
            **counts,
        }
        report = inventory._source_report(
            row,
            taxonomy=[],
            crosswalks=[],
            geography={},
            enrichment={},
            providers={},
            display_providers={},
        )
        self.assertEqual(report["snapshot"]["source_host"], "example.gov")
        self.assertTrue(report["snapshot"]["manifest_reconciliation"]["raw_hash_matches_run"])
        self.assertEqual(report["snapshot"]["handoff_code_version"], "code-v1")
        self.assertEqual(report["snapshot"]["processing_flags"], {"fresh_live_run": False, "processing_mode": "archived_replay"})
        self.assertEqual(report["exclusions"]["quarantine_reason_counts"], {"invalid_date": 1})
        self.assertEqual(report["exclusions"]["source_specific_aggregate_flags"], {
            "coordinate_quarantine_reason_counts": {"invalid_range": 1},
            "rejected_rows": 1,
        })
        encoded = inventory._canonical_bytes(report).decode("utf-8")
        self.assertNotIn("not-copied", encoded)
        self.assertNotIn("private facility", encoded)
        self.assertNotIn("secret", encoded)
        self.assertNotIn("source facility name", encoded)

    def test_invalid_hash_or_non_public_provenance_url_fails_closed(self):
        for digest in ("", "z" * 64):
            with self.assertRaises(ValueError):
                inventory._safe_hash(digest, "test")
        for url in ("file:///private/path", "https://user:password@example.gov/data", "not-a-url"):
            with self.assertRaises(ValueError):
                inventory._safe_source_url(url)

    def test_geometry_origin_aggregate_groups_the_classified_bucket(self):
        sql = inventory._GEOGRAPHY_SQL
        self.assertIn("END AS geometry_source", sql)
        self.assertIn("FROM categorized", sql)
        self.assertIn("ON display.candidate_id = candidate.candidate_id", sql)
        self.assertIn("ON latest.source_id = candidate.source_id", sql)
        self.assertNotIn("JOIN latest USING (source_id, snapshot_sha256)", sql)
        self.assertIn("GROUP BY source_id, geometry_source", sql)
        self.assertIn("candidate.coordinate_method IN ('address_geocode', 'geoapify_forward') THEN 'provider_derived'", sql)
        self.assertIn("candidate.location_class = 'numeric_source_coordinate' THEN 'source_coordinate'", sql)
        self.assertIn("AND candidate.location_class = 'city_postal' THEN 'coarse_reference'", sql)
        self.assertIn("THEN 'source_coordinate_fallback'", sql)
        self.assertIn("count(*) FILTER (WHERE served_by_private_map)", sql)

    def test_current_map_geometry_is_not_compared_with_import_time_counters(self):
        row = {
            "source_id": "test.source",
            "snapshot_sha256": "a" * 64,
            "source_artifact_sha256": "b" * 64,
            "normalized_sha256": "c" * 64,
            "source_url": "https://example.gov/data.csv",
            "retrieved_at": datetime(2026, 10, 4, tzinfo=timezone.utc),
            "adapter_version": "adapter-v1",
            "schema_version": "schema-v1",
            "manifest_artifact_sha256": None,
            "manifest_normalized_sha256": None,
            "manifest_normalized_rows": None,
            "manifest_source_url": None,
            "manifest_retrieved_at": None,
            "manifest_code_version": None,
            "manifest_config_version": None,
            "runtime_details": {},
            "idempotent_replay": False,
            **{key: 1 for key in (
                "input_count", "accepted_count", "quarantined_count", "out_of_scope_count",
                "imported_observation_count", "facility_count", "numeric_coordinate_count",
                "coarse_placeable_count", "unmapped_count", "api_listable_count", "map_visible_count",
                "public_rows", "physical_observation_count", "physical_candidate_count",
                "source_coordinate_candidates", "coarse_location_candidates",
                "display_coordinate_candidates", "unmapped_observations",
            )},
        }
        report = inventory._source_report(
            row, taxonomy=[], crosswalks=[], geography={}, enrichment={}, providers={}, display_providers={},
        )
        checks = report["physical_reconciliation"]
        self.assertTrue(checks["observations_match_import_counter"])
        self.assertTrue(checks["import_time_map_counters_not_compared_to_current_geometry"])
        self.assertNotIn("display_point_groups_match_map_visible_counter", checks)
        self.assertNotIn("unmapped_groups_match_unmapped_counter", checks)


if __name__ == "__main__":
    unittest.main()
