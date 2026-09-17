"""Regression contracts for the live, facility-level public discovery path."""

from pathlib import Path
import unittest


ROOT = Path(__file__).parents[1]


def _source() -> str:
    return (ROOT.parent / "src" / "lib.rs").read_text(encoding="utf-8")


class PublicDiscoveryQueryContractTests(unittest.TestCase):
    def test_list_and_facets_are_one_row_per_facility_with_stable_ordering(self):
        source = _source()
        self.assertIn("SELECT DISTINCT ON (history.facility_id)", source)
        self.assertIn("SELECT DISTINCT ON (facility_id) facility_id", source)
        self.assertIn("ORDER BY history.facility_id, history.observation_id", source)
        self.assertIn("ORDER BY facility_id, observation_id", source)

    def test_detail_uses_the_same_deterministic_observation_choice(self):
        source = _source()
        detail = source[source.index("pub async fn get_v2_location_detail_handler"):]
        self.assertIn("ORDER BY history.observation_id", detail)
        self.assertIn("LIMIT 1", detail)

    def test_public_queries_keep_live_release_review_join_and_view(self):
        source = _source()
        locations = source[source.index("pub async fn get_v2_locations_handler"):source.index("pub async fn get_v2_location_detail_handler")]
        self.assertIn("FROM uec.map_facilities_display_history AS history", locations)
        self.assertIn("JOIN uec.publication_review_release_current AS review", locations)
        self.assertIn("review.release_id = history.release_id", locations)
        self.assertIn("history.release_id = $1", locations)

    def test_planner_indexes_are_additive_and_gate_neutral(self):
        migration = (ROOT / "migrations" / "035_public_discovery_planner_indexes.sql").read_text(encoding="utf-8").lower()
        self.assertEqual(migration.count("create index if not exists"), 3)
        self.assertIn("status = 'promoted'", migration)
        self.assertIn("default_visible = true", migration)
        self.assertNotIn("drop index", migration)
        self.assertNotIn("drop table", migration)


if __name__ == "__main__":
    unittest.main()
