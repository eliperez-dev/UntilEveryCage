import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class GraphMigrationContractTests(unittest.TestCase):
    def read(self, name):
        return (ROOT / "migrations" / name).read_text(encoding="utf-8")

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


if __name__ == "__main__":
    unittest.main()
