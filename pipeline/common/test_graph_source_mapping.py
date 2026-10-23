import unittest

from pipeline.common.graph_candidate import build_graph_candidate
from pipeline.common.graph_source_mapping import FACILITY_IDENTIFIERS, name_assertions, source_identifier
from pipeline.contracts.graph_candidate_handoff import validate_graph_candidate


class GraphSourceMappingTests(unittest.TestCase):
    def test_mapping_covers_released_ids_and_retained_private_families(self):
        released = {
            "au.npi.facilities", "au.sa.epa.licensed-activities", "be.locations",
            "br.sif.registered", "ca.ontario.meat-plants", "dk.smiley",
            "es.cat.feed-sandach", "fsa_approved_establishments",
            "fss_approved_establishments", "it.1069-2009", "it.853-2004",
            "nl.nvwa.approved-food", "us.aphis", "us.fsis",
        }
        retained_facilities = {
            "fr.dgal.section-i", "fr.dgal.section-ii", "fr.georisques.icpe.animal",
            "gb.scot.marine.aquaculture",
        }
        retained_evidence = {"us.aphis.annual-reports", "us.inspections"}
        self.assertTrue(released.issubset(FACILITY_IDENTIFIERS))
        self.assertTrue(retained_facilities.issubset(FACILITY_IDENTIFIERS))
        self.assertTrue(retained_evidence.isdisjoint(FACILITY_IDENTIFIERS))

    def test_typed_ids_names_and_location_role_are_private_and_role_qualified(self):
        record = {
            "source_id": "au.npi.facilities", "source_record_key": "fixture-1", "source_row": 1,
            "source_values": {"fixture": "synthetic"},
            "normalized": {
                "facility_id": "NPI-1", "facility_name": "Synthetic Plant",
                "registered_business_name": "Synthetic Foods Pty Ltd",
                "location_role": "source-reported-facility-location",
                "address": "synthetic only", "coordinates": None,
            },
        }
        candidate = build_graph_candidate(record, artifact_sha256="a" * 64, observed_at="2026-10-01T00:00:00Z")
        validate_graph_candidate(candidate)
        self.assertEqual(candidate["facilities"][0]["source_identifier"], {
            "identifier_type": "npi_facility_id", "id_namespace": "au.npi.facilities",
            "value": "NPI-1", "identity_scope": "source_scoped",
        })
        self.assertEqual({item["role"] for item in candidate["name_assertions"]}, {"legal", "business"})
        self.assertEqual(candidate["location_role"], "operating")
        self.assertEqual(candidate["normalized_values"], record["normalized"])
        self.assertEqual(candidate["relationships"], [])

    def test_aphis_event_does_not_become_facility_identity(self):
        self.assertIsNone(source_identifier("us.aphis", {
            "establishment_id": None, "event_type": "inspection",
            "source_native_ids": {"certificate_number": "private"},
        }))

    def test_aphis_facility_identifier_type_is_not_an_event_or_certificate_id(self):
        self.assertEqual(source_identifier("us.aphis", {"establishment_id": "A-1"}), {
            "identifier_type": "aphis_establishment_id", "id_namespace": "us.aphis",
            "value": "A-1", "identity_scope": "source_scoped",
        })

    def test_ambiguous_or_generic_fields_do_not_become_business_names(self):
        self.assertEqual(name_assertions("unregistered.source", {
            "name": "person or placeholder", "account_name": "generic account",
            "government_url": "https://example.invalid",
        }), [])

    def test_retained_source_typed_business_names_are_mapped_but_not_generic_names(self):
        self.assertEqual(name_assertions("it.853-2004", {
            "facility_display_name": "Synthetic Establishment", "name": "Synthetic Establishment",
        }), [
            {"value": "Synthetic Establishment", "source_field": "name", "role": "legal"},
            {"value": "Synthetic Establishment", "source_field": "facility_display_name", "role": "business"},
        ])
        self.assertEqual(name_assertions("br.sif.registered", {"facility_display_name": "Not mapped"}), [])

    def test_recognized_establishment_location_is_not_asserted_as_operating(self):
        from pipeline.common.graph_source_mapping import location_role
        self.assertEqual(location_role("it.853-2004", {"location_role": "recognized-establishment-location"}), "unknown")

    def test_only_concrete_source_premises_address_gets_operating_role(self):
        from pipeline.common.graph_source_mapping import location_role
        self.assertEqual(location_role("dk.smiley", {
            "private_location_evidence": {"city": "Synthetic City", "postal_code": "0000"},
        }), "city_reference")
        self.assertEqual(location_role("dk.smiley", {
            "private_location_evidence": {"address_lines": ["Synthetic Street 1"], "city": "Synthetic City"},
        }), "operating")
        self.assertEqual(location_role("us.aphis", {
            "address_state": "mailing_city_state_only_not_operating_site",
            "private_location_evidence": {"city": "Synthetic City"},
        }), "mailing")

    def test_source_values_street_is_used_without_copying_or_relabeling_context(self):
        from pipeline.common.graph_source_mapping import location_role
        source_values = {"street": "Synthetic Street 2", "postal_code": "0000"}
        self.assertEqual(location_role("us.fsis", {}, source_values), "operating")


if __name__ == "__main__":
    unittest.main()
