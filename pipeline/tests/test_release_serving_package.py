from __future__ import annotations
import importlib.util
from pathlib import Path
import unittest

from pipeline.common import release_serving as serving


class ReleaseServingPackageTests(unittest.TestCase):
    def test_explicit_column_closure_excludes_private_payload_relations(self):
        specs = serving.export_specs()
        relations = {spec.relation for spec in specs}
        self.assertIn("uec.public_discovery_read_model_rows", relations)
        self.assertIn("uec.publication_review_events", relations)
        self.assertIn("uec.record_access_events", relations)
        self.assertIn("uec.observation_taxonomy_assignments", relations)
        self.assertIn("uec.graph_public_projection_builds", relations)
        self.assertIn("uec.graph_public_projection_edges", relations)
        self.assertIn("uec.graph_public_projection_edge_supports", relations)
        self.assertIn("uec.graph_public_projection_endpoints", relations)
        self.assertIn("uec.graph_public_projection_anchors", relations)
        self.assertIn("uec.graph_public_projection_evidence_refs", relations)
        self.assertIn("uec.graph_public_projection_evidence_refs", relations)
        self.assertTrue(relations.isdisjoint(serving.FORBIDDEN_DATA_RELATIONS))
        self.assertTrue({"uec.graph_connection_edges", "uec.graph_record_release_bindings",
                         "uec.source_entity_identifiers"}.issubset(serving.FORBIDDEN_DATA_RELATIONS))
        graph_edges = next(spec for spec in specs if spec.relation == "uec.graph_public_projection_edges")
        self.assertNotIn("source_identifier", graph_edges.columns)
        self.assertNotIn("source_record_id", graph_edges.columns)
        self.assertNotIn("from_source_identifier", graph_edges.query)
        self.assertIn("from_endpoint_id", graph_edges.columns)
        endpoints = next(spec for spec in specs if spec.relation == "uec.graph_public_projection_endpoints")
        self.assertNotIn("source_identifier", endpoints.columns)
        anchors = next(spec for spec in specs if spec.relation == "uec.graph_public_projection_anchors")
        self.assertIn("endpoint_id", anchors.columns)
        self.assertNotIn("connection_edge_id", anchors.columns)
        evidence_refs = next(spec for spec in specs if spec.relation == "uec.graph_public_projection_evidence_refs")
        self.assertIn("evidence_source_record_id", evidence_refs.columns)
        self.assertNotIn("event_payload", evidence_refs.columns)
        self.assertIn("uec.graph_public_evidence_references_current", serving.API_RELATIONS)
        self.assertIn("uec.source_rights_decisions", relations)
        source_records = next(spec for spec in specs if spec.relation == "uec.source_records")
        self.assertIn("NULL::text", source_records.query)
        self.assertIn("UNION SELECT DISTINCT reference.evidence_source_record_id", source_records.query)
        rights = next(spec for spec in specs if spec.relation == "uec.source_rights_decisions")
        self.assertIn("redistribution_status", rights.columns)
        prepare_path = Path(__file__).parents[1] / "scripts" / "maintenance" / "prepare-release-serving-package.py"
        prepare_spec = importlib.util.spec_from_file_location("prepare_release_serving_restore_test", prepare_path)
        prepare = importlib.util.module_from_spec(prepare_spec)
        prepare_spec.loader.exec_module(prepare)
        self.assertIn("uec.source_rights_decisions", prepare.RESTORE_ORDER)
        evidence_refs = next(spec for spec in specs if spec.relation == "uec.graph_public_projection_evidence_refs")
        self.assertIn("evidence_source_record_id", evidence_refs.columns)
        self.assertNotIn("event_payload", evidence_refs.columns)
        self.assertIn("uec.graph_public_evidence_references_current", serving.API_RELATIONS)
        all_sql = "\n".join(spec.query for spec in specs).casefold()
        self.assertNotIn("geocode_results", all_sql)
        self.assertNotIn("acquisition_runs", all_sql)
        source = next(spec for spec in specs if spec.relation == "uec.source_records")
        self.assertIn("raw_fields", source.columns)
        self.assertIn("raw_source_payload_excluded", source.query)

    def test_manifest_is_reproducible_and_labels_redaction(self):
        manifest = serving.package_manifest(release_ids=["v0-public"], migration_inventory_sha256="a" * 64, table_counts={"uec.releases": 1}, schema_artifacts={"pre_data": "b" * 64})
        self.assertEqual(manifest["schema_version"], "uec-serving-package-v6")
        self.assertEqual(manifest["package_state"], "selected_public_serving_derivative")
        self.assertEqual(manifest["package_sha256"], serving.canonical_sha256({key: value for key, value in manifest.items() if key != "package_sha256"}))
        self.assertIn("redacted", manifest["redaction_notice"])
        self.assertEqual(manifest["serving_schema_derivative"]["artifacts_sha256"]["pre_data"], "b" * 64)
        self.assertEqual(len(manifest["serving_schema_derivative"]["post_data_omissions"]), 2)
        self.assertNotIn("password", str(manifest).casefold())

    def test_restore_target_must_be_empty_except_zero_generation_singletons(self):
        path = Path(__file__).parents[1] / "scripts" / "maintenance" / "prepare-release-serving-package.py"
        spec = importlib.util.spec_from_file_location("prepare_release_serving_package_test", path)
        package = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(package)

        class Cursor:
            def __init__(self, populated=None, singleton_rows=None):
                self.populated = populated
                self.singleton_rows = singleton_rows or [(True, 0)]
                self.result = None

            def execute(self, query):
                relation = query.rsplit(" ", 1)[-1]
                if query.startswith("SELECT count(*)"):
                    self.result = (1 if relation == self.populated or relation in {
                        "uec.public_suppression_generation", "uec.graph_projection_generation"
                    } else 0,)
                else:
                    self.result = self.singleton_rows

            def fetchone(self):
                return self.result

            def fetchall(self):
                return self.result

        specs = serving.export_specs()
        package._assert_empty_target(Cursor(), specs)
        with self.assertRaisesRegex(ValueError, "not empty"):
            package._assert_empty_target(Cursor(populated="uec.releases"), specs)
        with self.assertRaisesRegex(ValueError, "singleton"):
            package._assert_empty_target(Cursor(singleton_rows=[(True, 1)]), specs)

    def test_api_grants_are_exact_and_read_only(self):
        sql = serving.grant_sql()
        self.assertIn("REVOKE ALL ON ALL TABLES", sql)
        self.assertIn("GRANT SELECT ON", sql)
        self.assertNotIn("GRANT ALL", sql)
        self.assertNotIn("DEFAULT PRIVILEGES", sql)
        self.assertNotIn("raw_artifacts", sql)
        self.assertIn("uec.schema_migrations", sql)
        self.assertIn("uec.map_facilities_display_history", sql)
        self.assertIn("uec.publication_review_release_current", sql)
        self.assertIn("uec.graph_public_connections_current", sql)
        self.assertNotIn("uec.graph_public_projection_edge_supports TO uec_api_runtime", sql)
        self.assertNotIn("uec.graph_connection_edges TO uec_api_runtime", sql)

    def test_invalid_release_or_digest_fails_closed(self):
        with self.assertRaises(ValueError): serving.package_manifest(release_ids=[], migration_inventory_sha256="a" * 64)
        with self.assertRaises(ValueError): serving.package_manifest(release_ids=["v0", "v0"], migration_inventory_sha256="a" * 64)
        with self.assertRaises(ValueError): serving.package_manifest(release_ids=["v0"], migration_inventory_sha256="A" * 64)
        with self.assertRaises(ValueError): serving.package_manifest(release_ids=["v0"], migration_inventory_sha256="a" * 64, schema_artifacts={"pre": "B" * 64})

    def test_export_requires_exact_public_release_and_matching_read_model(self):
        path = Path(__file__).parents[1] / "scripts" / "maintenance" / "prepare-release-serving-package.py"
        spec = importlib.util.spec_from_file_location("prepare_release_serving_package_gate_test", path)
        package = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(package)
        eligible = [("release-x", False, "promoted", False, "a" * 64, "a" * 64)]
        package._validate_selected_releases(["release-x"], eligible)
        for rows in (
            [],
            [("release-x", True, "promoted", False, "a" * 64, "a" * 64)],
            [("release-x", False, "candidate", False, "a" * 64, "a" * 64)],
            [("release-x", False, "promoted", False, "a" * 64, "b" * 64)],
        ):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                package._validate_selected_releases(["release-x"], rows)


if __name__ == "__main__": unittest.main()
