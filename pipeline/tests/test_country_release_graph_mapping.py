"""Synthetic controls for names and identifiers in the new country release."""
import unittest

from pipeline.common.d5_connection_analysis import (
    _observed_from_row, iter_shared_business_name_candidates,
)
from pipeline.common.graph_candidate import build_graph_candidate
from pipeline.common.graph_source_mapping import name_assertions, source_identifier


class CountryReleaseGraphMappingTests(unittest.TestCase):
    SOURCES = {
        "de.locations": "bltu_approval_number",
        "es.locations": "rgseaa_registration_number",
        "fr.georisques.icpe.animal": "georisques_aiot",
        "mx.locations": "denue_establishment_id",
        "nz.locations": "mpi_risk_measure_id",
    }

    def candidate(self, source):
        return build_graph_candidate({
            "source_id": source, "source_record_key": "synthetic-key",
            "source_row": 1, "source_values": {"synthetic": True},
            "normalized": {"establishment_id": "synthetic-permit",
                           "facility_display_name": "Synthetic Orchard Products"},
        }, artifact_sha256="a" * 64, observed_at="2026-10-27T00:00:00Z")

    def test_native_identifiers_remain_typed_and_source_qualified(self):
        for source, expected in self.SOURCES.items():
            with self.subTest(source=source):
                identifier = source_identifier(source, {"establishment_id": "synthetic-permit"})
                self.assertEqual(identifier["identifier_type"], expected)
                self.assertEqual(identifier["id_namespace"], source)
                self.assertEqual(identifier["identity_scope"], "source_scoped")
                self.assertIsNone(source_identifier(source, {"name": "No identifier"}))

    def test_bridge_business_labels_reach_the_existing_cross_source_matcher(self):
        rows = []
        for source in self.SOURCES:
            candidate = self.candidate(source)
            self.assertEqual(candidate["name_assertions"], [{
                "value": "Synthetic Orchard Products",
                "source_field": "facility_display_name", "role": "business",
            }])
            rows.append(_observed_from_row(candidate))
        generated, counters = iter_shared_business_name_candidates(rows)
        edges = list(generated)
        self.assertEqual(len(edges), 10)
        self.assertEqual(counters["pairs_emitted"], 10)
        self.assertEqual({s for edge in edges for s in edge["source_pair"]}, set(self.SOURCES))
        self.assertTrue(all(edge["relationship_type"] == "shared_business_name" for edge in edges))

    def test_names_do_not_create_ownership_or_publication_claims(self):
        for source in self.SOURCES:
            with self.subTest(source=source):
                candidate = self.candidate(source)
                self.assertEqual(candidate["organizations"], [])
                self.assertEqual(candidate["relationships"], [])
                self.assertEqual(candidate["publication"]["publication_status"], "not_eligible")
                self.assertIsNone(candidate["publication"]["release_id"])
                self.assertEqual(name_assertions(source, {"contact_name": "Synthetic Contact"}), [])

    def test_mpi_programme_is_not_inferred_to_be_a_unique_operating_site(self):
        candidate = self.candidate("nz.locations")
        self.assertEqual(candidate["location_role"], "unknown")
        self.assertEqual(candidate["facilities"][0]["source_identifier"]["identifier_type"], "mpi_risk_measure_id")


if __name__ == "__main__":
    unittest.main()
