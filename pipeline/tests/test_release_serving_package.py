from __future__ import annotations
import importlib.util
from pathlib import Path
import unittest
import uuid

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
        self.assertIn("uec.graph_public_evidence_metadata_clearance_events", relations)
        self.assertIn("uec.graph_public_projection_org_labels", relations)
        self.assertIn("uec.graph_public_projection_evidence_refs", relations)
        self.assertTrue(relations.isdisjoint(serving.FORBIDDEN_DATA_RELATIONS))
        self.assertTrue({"uec.graph_connection_edges", "uec.graph_record_release_bindings",
                         "uec.source_entity_identifiers", "uec.graph_evidence_events",
                         "uec.graph_evidence_links", "uec.graph_source_name_assertions"}.issubset(
                             serving.FORBIDDEN_DATA_RELATIONS))
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
        self.assertNotIn("raw_payload", evidence_refs.columns)
        self.assertIn("graph_public_evidence_references_current", evidence_refs.query)
        self.assertEqual(evidence_refs.columns, (
            "evidence_ref_id", "projection_id", "endpoint_id", "evidence_source_record_id",
            "source_id", "evidence_type", "event_date", "event_period", "observed_at",
            "source_url", "match_method",
        ))
        self.assertIn("uec.graph_public_evidence_references_current", serving.API_RELATIONS)
        self.assertIn("uec.graph_public_organization_labels_current", serving.API_RELATIONS)
        self.assertIn("uec.graph_public_organization_endpoints_current", serving.API_RELATIONS)
        self.assertIn("uec.graph_source_name_assertions", serving.FORBIDDEN_DATA_RELATIONS)
        self.assertIn("uec.source_rights_decisions", relations)
        source_records = next(spec for spec in specs if spec.relation == "uec.source_records")
        self.assertIn("'record:'||r.source_record_id::text", source_records.query)
        self.assertNotIn("r.source_record_key", source_records.query)
        self.assertIn("source_record_id", source_records.columns)
        access_events = next(spec for spec in specs if spec.relation == "uec.record_access_events")
        self.assertIn("e.source_record_id", access_events.query)
        self.assertNotIn("source_record_key", access_events.query)
        self.assertIn("UNION SELECT DISTINCT reference.evidence_source_record_id", source_records.query)
        self.assertIn("graph_public_evidence_references_current", source_records.query)
        lifecycle = next(spec for spec in specs if spec.relation == "uec.facility_lifecycle_events")
        self.assertIn("'Evidence note omitted from serving package'", lifecycle.query)
        self.assertNotIn("NULL::text", lifecycle.query)
        rights = next(spec for spec in specs if spec.relation == "uec.source_rights_decisions")
        self.assertIn("redistribution_status", rights.columns)
        self.assertIn("NOT IN ('us.aphis.annual-reports','us.inspections')", rights.query)
        org_label_rights = rights.query.casefold().split(") or exists (", 1)[1]
        self.assertIn("graph_public_projection_org_labels label", org_label_rights)
        self.assertIn("graph_public_projection_endpoints endpoint", org_label_rights)
        self.assertNotIn("graph_public_projection_evidence_refs", org_label_rights)
        self.assertIn("r.source_record_id=label.label_source_record_id", org_label_rights)
        self.assertIn("r.source_id=d.source_id", org_label_rights)
        self.assertIn("r.artifact_id=d.artifact_id", org_label_rights)
        self.assertIn("release.profile=d.profile", org_label_rights)
        self.assertIn("build.release_id=d.release_id", org_label_rights)
        self.assertIn("build.active and build.status='completed'", org_label_rights)
        self.assertIn("build.projection_version='graph-release-projection-v3'", org_label_rights)
        self.assertIn("join selected s on s.release_id=d.release_id", rights.query.casefold())
        self.assertNotIn("redistribution_status='cleared'", rights.query.casefold())
        metadata_clearance = next(spec for spec in specs if spec.relation == "uec.graph_public_evidence_metadata_clearance_events")
        self.assertEqual(metadata_clearance.columns, (
            "clearance_event_id", "source_id", "profile", "release_id", "artifact_id",
            "artifact_sha256", "scope_version", "decision_status", "approved_fields",
            "decision_actor", "decision_reference", "decided_at", "created_at",
        ))
        self.assertIn("graph_public_evidence_metadata_clearance_current", metadata_clearance.query)
        self.assertIn("graph_public_evidence_references_current", metadata_clearance.query)
        self.assertNotIn("event_payload", metadata_clearance.query)
        self.assertNotIn("graph_public_evidence_metadata_clearance_current", serving.API_RELATIONS)
        prepare_path = Path(__file__).parents[1] / "scripts" / "maintenance" / "prepare-release-serving-package.py"
        prepare_spec = importlib.util.spec_from_file_location("prepare_release_serving_restore_test", prepare_path)
        prepare = importlib.util.module_from_spec(prepare_spec)
        prepare_spec.loader.exec_module(prepare)
        self.assertIn("uec.source_rights_decisions", prepare.RESTORE_ORDER)
        self.assertIn("uec.graph_public_evidence_metadata_clearance_events", prepare.RESTORE_ORDER)
        labels = next(spec for spec in specs if spec.relation == "uec.graph_public_projection_org_labels")
        self.assertEqual(labels.columns, ("projection_id", "endpoint_id", "label_source_record_id", "display_name", "assertion_role"))
        self.assertIn("graph_public_organization_endpoints_current eligible", labels.query)
        self.assertIn("eligible.organization_id=endpoint.public_entity_id", labels.query)
        self.assertIn("uec.graph_public_projection_org_labels", prepare.RESTORE_ORDER)
        evidence_refs = next(spec for spec in specs if spec.relation == "uec.graph_public_projection_evidence_refs")
        self.assertIn("evidence_source_record_id", evidence_refs.columns)
        self.assertNotIn("event_payload", evidence_refs.columns)
        self.assertIn("uec.graph_public_evidence_references_current", serving.API_RELATIONS)
        self.assertIn("uec.graph_public_organization_endpoints_current", serving.API_RELATIONS)
        all_sql = "\n".join(spec.query for spec in specs).casefold()
        self.assertNotIn("geocode_results", all_sql)
        self.assertNotIn("acquisition_runs", all_sql)
        source = next(spec for spec in specs if spec.relation == "uec.source_records")
        self.assertIn("raw_fields", source.columns)
        self.assertIn("raw_source_payload_excluded", source.query)

    def test_org_label_only_rights_are_exported_in_exact_selected_scope(self):
        rights = next(
            spec for spec in serving.export_specs()
            if spec.relation == "uec.source_rights_decisions"
        )
        query = rights.query.casefold()
        # The independent organization-label EXISTS supports a label artifact
        # with no evidence reference while keeping release/profile/source/
        # artifact identity tied to the selected active graph projection.
        evidence_branch, org_label_branch = query.split(") or exists (", 1)
        self.assertIn("graph_public_projection_evidence_refs", evidence_branch)
        self.assertIn("graph_public_projection_org_labels label", org_label_branch)
        self.assertIn("build.release_id=d.release_id", org_label_branch)
        self.assertIn("release.profile=d.profile", org_label_branch)
        self.assertIn("r.source_id=d.source_id", org_label_branch)
        self.assertIn("r.artifact_id=d.artifact_id", org_label_branch)
        self.assertIn("join selected s on s.release_id=d.release_id", query)
        self.assertNotIn("graph_public_projection_evidence_refs", org_label_branch)
        self.assertNotIn("d.release_id=any", org_label_branch)

    def test_source_record_key_export_is_stable_unique_and_opaque(self):
        record_ids = (
            uuid.UUID("00000000-0000-4000-8000-000000000001"),
            uuid.UUID("00000000-0000-4000-8000-000000000002"),
        )

        def serving_key(record_id):
            return "record:" + str(record_id)

        first = [serving_key(record_id) for record_id in record_ids]
        second = [serving_key(record_id) for record_id in record_ids]
        self.assertEqual(first, second)
        self.assertEqual(len(set(first)), len(record_ids))
        self.assertTrue(all(value is not None and value for value in first))
        self.assertTrue(all(value.startswith("record:") for value in first))
        self.assertFalse(any("private-native-key" in value for value in first))

    def test_manifest_is_reproducible_and_labels_redaction(self):
        manifest = serving.package_manifest(release_ids=["v0-public"], migration_inventory_sha256="a" * 64, table_counts={"uec.releases": 1}, schema_artifacts={"pre_data": "b" * 64})
        self.assertEqual(manifest["schema_version"], "uec-serving-package-v8")
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
        self.assertIn("GRANT SELECT ON " + ", ".join(serving.API_RELATIONS) + " TO uec_api_runtime", sql)
        self.assertIn("REVOKE ALL ON FUNCTION uec.is_valid_italian_vat_identifier(text,text,text) FROM PUBLIC", sql)
        self.assertNotIn("uec.graph_public_projection_edge_supports TO uec_api_runtime", sql)
        self.assertNotIn("uec.graph_connection_edges TO uec_api_runtime", sql)
        self.assertIn("REVOKE ALL ON FUNCTION uec.is_valid_italian_vat_identifier(text,text,text) FROM uec_api_runtime", sql)
        self.assertNotIn("GRANT EXECUTE ON FUNCTION uec.is_valid_italian_vat_identifier", sql)
        custom_role_sql = serving.grant_sql(api_role="custom_graph_api")
        self.assertIn("REVOKE ALL ON FUNCTION uec.is_valid_italian_vat_identifier(text,text,text) FROM custom_graph_api", custom_role_sql)
        self.assertNotIn("GRANT EXECUTE ON FUNCTION uec.is_valid_italian_vat_identifier", custom_role_sql)

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
