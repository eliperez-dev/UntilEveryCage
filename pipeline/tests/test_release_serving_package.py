from __future__ import annotations
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
        self.assertIn("uec.graph_public_projection_endpoint_anchors", relations)
        self.assertTrue(relations.isdisjoint(serving.FORBIDDEN_DATA_RELATIONS))
        self.assertTrue({"uec.graph_connection_edges", "uec.graph_record_release_bindings",
                         "uec.source_entity_identifiers"}.issubset(serving.FORBIDDEN_DATA_RELATIONS))
        graph_edges = next(spec for spec in specs if spec.relation == "uec.graph_public_projection_edges")
        self.assertNotIn("source_identifier", graph_edges.columns)
        self.assertNotIn("source_record_id", graph_edges.columns)
        self.assertNotIn("from_source_identifier", graph_edges.query)
        all_sql = "\n".join(spec.query for spec in specs).casefold()
        self.assertNotIn("geocode_results", all_sql)
        self.assertNotIn("acquisition_runs", all_sql)
        source = next(spec for spec in specs if spec.relation == "uec.source_records")
        self.assertIn("raw_fields", source.columns)
        self.assertIn("raw_source_payload_excluded", source.query)

    def test_manifest_is_reproducible_and_labels_redaction(self):
        manifest = serving.package_manifest(release_ids=["v0-public"], migration_inventory_sha256="a" * 64, table_counts={"uec.releases": 1}, schema_artifacts={"pre_data": "b" * 64})
        self.assertEqual(manifest["schema_version"], "uec-serving-package-v3")
        self.assertEqual(manifest["package_sha256"], serving.canonical_sha256({key: value for key, value in manifest.items() if key != "package_sha256"}))
        self.assertIn("redacted", manifest["redaction_notice"])
        self.assertEqual(manifest["serving_schema_derivative"]["artifacts_sha256"]["pre_data"], "b" * 64)
        self.assertEqual(len(manifest["serving_schema_derivative"]["post_data_omissions"]), 2)
        self.assertNotIn("password", str(manifest).casefold())

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


if __name__ == "__main__": unittest.main()
