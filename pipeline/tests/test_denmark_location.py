import unittest
from pathlib import Path

from pipeline.sources.denmark.location import (
    classify_location,
    load_local_references,
    normalize_locality,
    normalize_postal_code,
)


class DenmarkLocationTests(unittest.TestCase):
    def setUp(self):
        self.record = {
            "source_id": "dk.smiley",
            "source_record_key": "synthetic-1",
            "address": {"street": "Eksempelvej 2", "postal_code": " 0123 ", "city": "København"},
            "coordinates": {"latitude": 55.6, "longitude": 12.5, "method": "source", "review_status": "source"},
        }

    def test_unicode_and_whitespace_normalization_is_comparison_only(self):
        self.assertEqual(normalize_locality(" KØBENHAVN  "), normalize_locality("København"))
        self.assertEqual(normalize_postal_code(" 01 23 "), "0123")

    def test_source_coordinates_are_preserved_and_never_queued(self):
        result = classify_location(self.record)
        self.assertEqual(result["state"], "source_coordinates_preserved")
        self.assertTrue(result["source_coordinates_preserved"])
        self.assertFalse(result["exact_geocode_eligible"])
        self.assertIsNone(result["exact_geocode_candidate"])

    def test_unique_locality_reference_is_coarse_and_never_a_facility_point(self):
        record = {**self.record, "coordinates": {"latitude": None, "longitude": None}}
        refs = [{"country_code": "DK", "city_name": "København", "postal_code": None,
                 "reference_latitude": 55.68, "reference_longitude": 12.57,
                 "reference_source": "synthetic official reference", "source_reference_id": "synthetic-ref"}]
        result = classify_location(record, refs)
        coarse = result["coarse_display_reference"]
        self.assertEqual(result["state"], "coarse_reference_match")
        self.assertEqual(coarse["precision"], "locality_reference_coarse")
        self.assertIn("not a facility point", coarse["label"])
        self.assertFalse(result["exact_geocode_eligible"])

    def test_ambiguous_locality_is_unresolved_and_exact_candidate_held_by_default(self):
        record = {**self.record, "coordinates": {"latitude": None, "longitude": None}}
        refs = [
            {"country_code": "DK", "city_name": "København", "reference_latitude": 55.6, "reference_longitude": 12.5},
            {"country_code": "DK", "city_name": "København", "reference_latitude": 55.7, "reference_longitude": 12.6},
        ]
        result = classify_location(record, refs)
        self.assertEqual(result["state"], "ambiguous_reference")
        self.assertIsNone(result["coarse_display_reference"])
        self.assertEqual(result["exact_geocode_candidate_state"], "held_out_of_scope")
        self.assertFalse(result["exact_geocode_candidate"]["eligible"])
        self.assertEqual(result["publication_state"], "blocked")

    def test_exact_job_requires_all_three_gates_and_preserves_source_spelling(self):
        record = {**self.record, "coordinates": {"latitude": None, "longitude": None}}
        result = classify_location(record, privacy_status="eligible", dawa_terms_approved=True,
                                   dawa_profile_approved=True, source_scope_eligible=True)
        self.assertTrue(result["exact_geocode_eligible"])
        self.assertEqual(result["exact_geocode_candidate_state"], "eligible_pending_queue")
        self.assertEqual(result["exact_geocode_candidate"]["address"]["city"], "København")
        self.assertTrue(result["source_address_eligible"])
        self.assertNotIn("provider_id", result["exact_geocode_candidate"])

    def test_source_scope_can_prepare_provider_neutral_candidate_without_lookup_approval(self):
        record = {**self.record, "coordinates": {"latitude": None, "longitude": None}}
        result = classify_location(record, privacy_status="eligible", source_scope_eligible=True)
        self.assertTrue(result["source_address_eligible"])
        self.assertFalse(result["exact_geocode_eligible"])
        self.assertEqual(result["exact_geocode_candidate_state"], "source_eligible_provider_gate_pending")
        self.assertFalse(result["exact_geocode_candidate"]["eligible"])

    def test_care_of_and_explicitly_restricted_addresses_are_not_queued(self):
        record = {**self.record, "coordinates": {"latitude": None, "longitude": None},
                  "address": {**self.record["address"], "street": "C/O Example Person, Eksempelvej 2"}}
        result = classify_location(record, privacy_status="eligible", source_scope_eligible=True)
        self.assertFalse(result["source_address_eligible"])
        self.assertEqual(result["exact_geocode_candidate_state"], "held_for_explicit_address_restriction")

        restricted = {**self.record, "coordinates": {"latitude": None, "longitude": None},
                      "source_fields": {"Adressebeskyttet": "Ja"}}
        result = classify_location(restricted, privacy_status="eligible", source_scope_eligible=True)
        self.assertFalse(result["source_address_eligible"])

    def test_local_references_are_loaded_without_any_network_dependency(self):
        path = Path(__file__).parent / "fixtures" / "denmark-locality-reference.synthetic.jsonl"
        self.assertEqual(load_local_references(path)[0]["city_name"], "Testby")


if __name__ == "__main__":
    unittest.main()
