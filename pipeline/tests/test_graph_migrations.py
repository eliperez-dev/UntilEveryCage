import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class GraphMigrationContractTests(unittest.TestCase):
    def read(self, name):
        return (ROOT / "migrations" / name).read_text(encoding="utf-8")

    def test_087_keyed_connection_view_keeps_live_and_release_gates(self):
        migrations = sorted(path.name for path in (ROOT / "migrations").glob("*.sql"))
        migration_name = "087_keyed_public_graph_connection_eligibility.sql"
        self.assertIn(migration_name, migrations)
        sql = self.read(migration_name).casefold()
        self.assertIn("create or replace view uec.graph_public_connections_current as", sql)
        self.assertNotIn("drop view uec.graph_public_connections_current", sql)
        self.assertNotIn("graph_public_projection_endpoint_anchors", sql)
        self.assertNotIn("graph_connection_edges", sql)
        for gate in (
            "b.active and b.status='completed'",
            "b.projection_version='graph-release-projection-v3'",
            "b.edge_generation=generation.generation",
            "b.suppression_generation=suppression.generation",
            "b.release_manifest_sha256=manifest.manifest_sha256",
            "release.test_only is not true",
            "release.status='promoted' or history.release_id is not null",
            "record.source_id=support.source_id",
            "record.artifact_id=support.artifact_id",
            "candidate.release_id=e.release_id",
            "current_support.facility_id=candidate.facility_id",
            "current_anchor.facility_id=anchor.facility_id",
            "current_anchor.source_record_id=anchor.source_record_id",
            "graph_public_organization_label_candidates_current org",
            "org.organization_id=e.from_entity_id",
            "org.organization_id=e.to_entity_id",
        ):
            with self.subTest(gate=gate):
                self.assertIn(gate, sql)
        canonical = self.read("085_graph_live_anchor_keys.sql").casefold()
        self.assertIn("rights.redistribution_status='cleared'", canonical)
        self.assertIn("restricted.source_record_id=label.label_source_record_id", canonical)
        self.assertIn("restricted.source_record_id=anchor.source_record_id", canonical)
        self.assertEqual(sql.count("exists ("), 14)
        self.assertEqual(sql.count("not exists ("), 2)

    def test_088_page_candidate_view_exposes_only_keys_and_keeps_release_gates(self):
        sql = self.read("088_public_graph_connection_page_candidates.sql").casefold()
        self.assertIn("create or replace view uec.graph_public_connection_page_candidates_current as", sql)
        for gate in (
            "b.active and b.status='completed'",
            "b.projection_version='graph-release-projection-v3'",
            "b.edge_generation=generation.generation",
            "b.suppression_generation=suppression.generation",
            "b.release_manifest_sha256=manifest.manifest_sha256",
            "release.test_only is not true",
            "release.status='promoted' or history.release_id is not null",
        ):
            with self.subTest(gate=gate):
                self.assertIn(gate, sql)
        select_list = sql.split("as\nselect", 1)[1].split("from", 1)[0]
        self.assertEqual(select_list.strip(), "e.release_id,e.connection_edge_id")
        self.assertIn("grant select on uec.graph_public_connection_page_candidates_current to uec_api_runtime", sql)
        for forbidden in ("from_entity_id", "to_entity_id", "source_id", "display_name", "signal_explanation"):
            self.assertNotIn(forbidden, select_list)

    def test_089_page_candidates_add_only_opaque_routing_keys(self):
        sql = self.read("089_public_graph_connection_routing_keys.sql").casefold()
        self.assertIn("create or replace view uec.graph_public_connection_page_candidates_current as", sql)
        self.assertIn("e.from_entity_id,e.to_entity_id,e.from_source_id,e.to_source_id", sql)
        self.assertNotIn("display_name", sql)
        self.assertNotIn("signal_explanation", sql)
        self.assertNotIn("facility_id", sql)
        self.assertNotIn("source_record_id", sql)
        for gate in (
            "b.active and b.status='completed'",
            "b.edge_generation=generation.generation",
            "b.suppression_generation=suppression.generation",
            "release.test_only is not true",
            "release.status='promoted' or history.release_id is not null",
        ):
            with self.subTest(gate=gate):
                self.assertIn(gate, sql)

    def test_reserved_migrations_are_present_and_ordered(self):
        migrations = sorted(path.name for path in (ROOT / "migrations").glob("*.sql"))
        graph_migrations = [
            "026_graph_entities_crosswalks.sql",
            "027_graph_relationship_observations.sql",
            "028_graph_claims_support.sql",
            "029_graph_publication_projections.sql",
        ]
        positions = [migrations.index(name) for name in graph_migrations]
        self.assertEqual(positions, sorted(positions))
        self.assertEqual([migrations[position] for position in positions], graph_migrations)
        expected_graph_suffix = [
            "026_graph_entities_crosswalks.sql",
            "027_graph_relationship_observations.sql",
            "028_graph_claims_support.sql",
            "029_graph_publication_projections.sql",
            "030_discovery_projection_support_indexes.sql",
            "031_public_release_read_path_indexes.sql",
            "032_flatten_public_history_view.sql",
            "033_release_summary_component.sql",
            "034_public_eligibility_join_indexes.sql",
            "035_public_discovery_planner_indexes.sql",
            "036_public_facility_discovery_view.sql",
            "037_public_discovery_read_model.sql",
            "038_graph_regulatory_authority_relationship.sql",
            "039_private_graph_query_indexes.sql",
            "040_geocode_worker_durability.sql",
            "041_source_rights_decisions.sql",
            "042_private_graph_ingest.sql",
            "043_identity_candidate_review_lineage.sql",
            "044_graph_connection_edges.sql",
        ]
        graph_start = migrations.index(expected_graph_suffix[0])
        graph_end = migrations.index(expected_graph_suffix[-1]) + 1
        self.assertEqual(migrations[graph_start:graph_end], expected_graph_suffix)

    def test_d4_migration_numbers_are_unique_and_ordered(self):
        migrations = sorted(path.name for path in (ROOT / "migrations").glob("*.sql"))
        d4 = [name for name in migrations if name.startswith(("042_", "043_"))]
        self.assertEqual(d4, [
            "042_private_graph_ingest.sql",
            "043_identity_candidate_review_lineage.sql",
        ])

    def test_d6_connection_edges_are_thin_private_and_typed(self):
        migrations = sorted(path.name for path in (ROOT / "migrations").glob("*.sql"))
        self.assertIn("044_graph_connection_edges.sql", migrations)
        self.assertGreater(migrations.index("044_graph_connection_edges.sql"), migrations.index("043_identity_candidate_review_lineage.sql"))
        sql = self.read("044_graph_connection_edges.sql")
        self.assertIn("CREATE TABLE uec.graph_connection_edges", sql)
        self.assertIn("connection_type TEXT NOT NULL CHECK (connection_type IN ('exact', 'inferred'))", sql)
        self.assertIn("from_entity_type TEXT NOT NULL", sql)
        self.assertIn("to_entity_type TEXT NOT NULL", sql)
        self.assertIn("ruleset_version TEXT NOT NULL", sql)
        self.assertIn("publication_status TEXT NOT NULL DEFAULT 'not_eligible'", sql)
        self.assertIn("storage_state TEXT NOT NULL DEFAULT 'private'", sql)
        self.assertNotIn("review_state", sql)

    def test_entities_are_distinct_and_crosswalk_is_scoped(self):
        sql = self.read("026_graph_entities_crosswalks.sql")
        self.assertIn("CREATE TABLE uec.organizations", sql)
        self.assertIn("entity_type TEXT NOT NULL CHECK (entity_type IN ('facility', 'organization'))", sql)
        self.assertIn("identity_scope TEXT NOT NULL DEFAULT 'source_scoped'", sql)
        self.assertIn("CHECK (identity_scope = 'source_scoped')", sql)
        self.assertIn("source_entity_crosswalks_append_only", sql)

    def test_relationships_and_claims_preserve_uncertainty_and_state_separation(self):
        relationship = self.read("027_graph_relationship_observations.sql")
        claims = self.read("028_graph_claims_support.sql")
        for sql in (relationship, claims):
            for field in ("observed_at", "confidence", "review_state", "storage_state", "privacy_status", "publication_status"):
                self.assertIn(field, sql)
            self.assertIn("append_only", sql)
        self.assertIn("assertion_status = 'unknown'", relationship)
        self.assertIn("unknown_reason", relationship)
        self.assertIn("support_role", claims)
        self.assertIn("contradicting", claims)
        self.assertIn("regulatory_authority_for", (ROOT / "migrations" / "038_graph_regulatory_authority_relationship.sql").read_text(encoding="utf-8"))

    def test_public_projections_are_release_and_suppression_aware(self):
        sql = self.read("029_graph_publication_projections.sql")
        self.assertIn("release.status = 'promoted'", sql)
        self.assertIn("relationship.privacy_status = 'passed'", sql)
        self.assertIn("claim.privacy_status = 'passed'", sql)
        self.assertIn("uec.public_access_restricted", sql)
        self.assertIn("graph_publication_safety", sql)

    def test_083_retires_stale_graph_projection_generation(self):
        migrations = sorted(path.name for path in (ROOT / "migrations").glob("*.sql"))
        self.assertIn("083_source_backed_organization_labels.sql", migrations)
        sql = self.read("083_source_backed_organization_labels.sql").casefold()
        self.assertIn("update uec.graph_public_projection_builds", sql)
        self.assertIn("set active=false", sql)
        self.assertIn("update uec.graph_projection_generation", sql)
        self.assertIn("set generation=generation+1", sql)
        self.assertNotIn("graph_connection_edges", sql)

    def test_084_bounds_live_evidence_anchor_lookup_without_dropping_gates(self):
        migrations = sorted(path.name for path in (ROOT / "migrations").glob("*.sql"))
        migration = "084_bound_aphis_evidence_anchor_lookup.sql"
        self.assertIn(migration, migrations)
        sql = self.read(migration).casefold()
        self.assertEqual(sql.count("join lateral ("), 2)
        self.assertIn("limit 1", sql)
        for gate in (
            "graph_public_evidence_metadata_clearance_current",
            "graph_projection_generation",
            "public_suppression_generation",
            "publication_review_release_current",
            "map_facilities_public_discovery_read_model",
            "release_manifests",
            "public_access_restricted",
            "release_members",
            "source_rights_decisions",
        ):
            self.assertIn(gate, sql)
        self.assertIn("current_anchor.source_record_id=anchor.source_record_id", sql)
        self.assertIn("current_anchor.facility_id=anchor.facility_id", sql)

    def test_085_factors_map_eligibility_once_and_reuses_it_for_graph_keys(self):
        migrations = sorted(path.name for path in (ROOT / "migrations").glob("*.sql"))
        migration = "085_graph_live_anchor_keys.sql"
        self.assertIn(migration, migrations)
        sql = self.read(migration).casefold()
        self.assertIn("create or replace view uec.public_discovery_live_eligible_rows", sql)
        self.assertIn("create or replace view uec.map_facilities_public_discovery_read_model", sql)
        self.assertIn("from uec.public_discovery_live_eligible_rows eligible", sql)
        self.assertIn("create or replace view uec.graph_public_live_facility_anchors_current", sql)
        self.assertIn("from uec.public_discovery_live_eligible_rows", sql)
        self.assertIn("create or replace view uec.graph_public_organization_label_candidates_current", sql)
        candidates = sql.split(
            "create or replace view uec.graph_public_organization_label_candidates_current as", 1
        )[1].split("create or replace view uec.graph_public_connections_current as", 1)[0]
        for gate in (
            "review.publication_eligible=true",
            "review.privacy_screening_status='passed'",
            "review.factual_review_status<>'rejected'",
            "review.maintainer_approval='approved'",
            "rights.redistribution_status='cleared'",
            "build.release_manifest_sha256=manifest.manifest_sha256",
            "build.suppression_generation=suppression.generation",
            "restricted.source_record_id=label.label_source_record_id",
            "restricted.source_record_id=anchor.source_record_id",
        ):
            with self.subTest(organization_candidate_gate=gate):
                self.assertIn(gate, candidates)
        for gate in (
            "release.status='promoted'",
            "release.test_only is not true",
            "manifest.manifest_sha256=metadata.manifest_sha256",
            "review.publication_eligible=true",
            "review.privacy_screening_status='passed'",
            "review.factual_review_status<>'rejected'",
            "review.maintainer_approval='approved'",
            "public_access_revoked",
            "suppression_case_current",
            "case_record.status in ('active','review','closed','expired')",
            "min(eligible.first_observed_at) over facility_history",
            "max(eligible.observed_at) over facility_history",
            "facility_lifecycle_current",
        ):
            with self.subTest(gate=gate):
                self.assertIn(gate, sql)
        connections = sql.split(
            "create or replace view uec.graph_public_connections_current as", 1
        )[1].split("create or replace view uec.graph_public_organization_endpoints_current as", 1)[0]
        self.assertIn("live_anchors as materialized", connections)
        self.assertIn("from uec.public_discovery_live_eligible_rows eligible", connections)
        self.assertIn("eligible_supports as materialized", connections)
        self.assertIn("support_status as materialized", connections)
        self.assertIn("eligible_endpoints as materialized", connections)
        self.assertIn("organization_candidates as materialized", connections)
        self.assertIn("eligible_organizations as materialized", connections)
        self.assertIn("from uec.graph_public_organization_label_candidates_current candidate", connections)
        self.assertIn("from organization_candidates candidate", connections)
        self.assertIn("support.support_count=support.eligible_support_count", connections)
        self.assertIn("support_build.active and support_build.status='completed'", connections)
        self.assertIn("from uec.graph_public_projection_anchors anchor", connections)
        self.assertNotIn("graph_public_projection_endpoint_anchors", connections)
        self.assertIn("join live_anchors live", connections)
        self.assertIn("public_suppression_generation", connections)
        self.assertIn("release_manifests", connections)
        self.assertIn("public_release_history", connections)
        self.assertNotIn("map_facilities_public_discovery_read_model", connections)
        for view_name, next_view in (
            ("graph_public_organization_endpoints_current", "graph_public_evidence_references_current"),
            ("graph_public_evidence_references_current", "graph_public_projection_edges_release_page_idx"),
        ):
            view_body = sql.split(f"create or replace view uec.{view_name} as", 1)[1].split(
                next_view if next_view.startswith("graph_public_projection")
                else f"create or replace view uec.{next_view} as", 1
            )[0]
            self.assertIn("graph_public_live_facility_anchors_current", view_body)
            self.assertNotIn("map_facilities_public_discovery_read_model current_anchor", view_body)
        self.assertIn("graph_public_projection_edges_release_page_idx", sql)
        self.assertIn("graph_public_projection_edges_release_from_idx", sql)
        self.assertIn("graph_public_projection_edges_release_to_idx", sql)
        self.assertNotIn("grant select on uec.public_discovery_live_eligible_rows", sql)
        self.assertNotIn("grant select on uec.graph_public_live_facility_anchors_current", sql)

    def test_085_restriction_resolver_uses_indexed_routes_without_changing_lifecycle_gates(self):
        sql = self.read("085_graph_live_anchor_keys.sql").casefold()
        restriction = sql.split(
            "create or replace view uec.public_access_restricted as", 1
        )[1].split(
            "create or replace view uec.public_discovery_live_eligible_rows as", 1
        )[0]
        self.assertEqual(restriction.count("select record.source_record_id"), 3)
        self.assertIn("from uec.record_access_current", restriction)
        self.assertIn("where action='public_access_revoked'", restriction)
        self.assertIn("join uec.facility_source_links link", restriction)
        self.assertIn("link.facility_id=ref.facility_id", restriction)
        self.assertIn("join uec.observations observation", restriction)
        self.assertIn("observation.facility_id=ref.facility_id", restriction)
        self.assertIn("ref.source_id=record.source_id", restriction)
        self.assertIn("ref.source_record_key=record.source_record_key", restriction)
        self.assertIn("current_case.event_type='suppressed'", restriction)
        self.assertIn("case_record.status in ('active','review','closed','expired')", restriction)
        self.assertEqual(restriction.count("\nunion\n"), 3)
        self.assertNotIn("join uec.source_records record on (", restriction)
        self.assertNotIn("or exists (select 1 from uec.facility_source_links", restriction)


if __name__ == "__main__":
    unittest.main()
