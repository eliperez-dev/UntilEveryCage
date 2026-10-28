"""Synthetic format and contradiction checks for Spanish address recovery."""
from __future__ import annotations

import unittest

from pipeline.geocoding import spanish_addresses as s
from pipeline.tests import test_locationiq_first_pass as fixtures

candidate, query = fixtures.candidate, fixtures.query


class SpanishAddressTests(unittest.TestCase):
    def test_punctuation_abbreviations_and_explicit_units(self):
        for address in ("Calle Example, 12", "C/ Example 12", "C. Example, 12",
                        "Carrer Example 12 Nave 3", "Calle Example 12, Local 5",
                        "12 Calle Example", "Calle Example núm. 12"):
            with self.subTest(address=address):
                self.assertTrue(s.street_matches(address, "Calle Example", "12"))
        self.assertTrue(s.street_matches("Avda. Example, 12-A", "Avenida Example", "12A"))
        self.assertTrue(s.street_matches("Ctra. Example 12", "Carretera Example", "12"))

    def test_different_names_numbers_types_and_unlabeled_tails_do_not_match(self):
        for address in ("Calle Different 12", "Calle Example 13", "Calle Example 12-14",
                        "Calle Example 12/14", "Avenida Example 12", "Calle Example",
                        "Calle Example 12 Industrial Zone", "Calle Example 12A",
                        "Calle Example 12 Nave Calle Other 8"):
            with self.subTest(address=address):
                self.assertFalse(s.street_matches(address, "Calle Example", "12"))
        for number in (None, True, "", "12;14", "12-14"):
            self.assertFalse(s.street_matches("Calle Example 12", "Calle Example", number))

    def test_provider_query_removes_clutter_only_for_one_explicit_road(self):
        self.assertEqual(s.provider_address("Industrial estate, C/ Example, 12, Nave 3"), "calle example 12")
        ambiguous = "Calle Example 12, Calle Other 14"
        self.assertEqual(s.provider_address(ambiguous), ambiguous)
        for source in ("Industrial estate, Plot 12", "Calle Example s/n", "Calle Example 12 Unknown Tail"):
            self.assertEqual(s.provider_address(source), source)

    def test_locality_articles_accents_and_province_aliases(self):
        self.assertEqual(s.locality_key("Example (La)"), s.locality_key("La Example"))
        self.assertEqual(s.locality_key("Éxample, La"), s.locality_key("La Example"))
        self.assertEqual(s.province_key("Provincia de Girona"), s.province_key("Gerona"))

    def test_region_hierarchy_never_overrides_explicit_conflicts(self):
        self.assertTrue(s.province_matches({"state": "Cataluña", "state_code": "CT"}, "Girona", None))
        self.assertTrue(s.province_matches({"state": "Catalonia", "province": "Gerona"}, "Girona", None))
        self.assertFalse(s.province_matches({"state": "Catalonia", "province": "Barcelona"}, "Girona", None))
        self.assertFalse(s.province_matches({"state": "Catalonia", "state_code": "MD"}, "Girona", None))
        self.assertFalse(s.province_matches({"state": "Catalonia", "postcode": "28001"}, "Madrid", "28001"))
        self.assertFalse(s.province_matches({"postcode": "28001"}, "Madrid", "28001"))
        self.assertTrue(s.province_matches({"state": "Andalucía", "state_code": "AN"}, "ANDALUCIA", None))
        self.assertTrue(s.province_matches({"province": "Granada"}, "Andalucía", None))
        self.assertFalse(s.province_matches({"province": "Barcelona"}, "Andalucía", None))

    def test_full_adapter_keeps_address_checks_and_ambiguity(self):
        factory = fixtures.LocationIqFirstPassTests().make
        for source in ("C/ Example, 4", "Calle Example 4 Nave 2"):
            adapter, _ = factory([candidate()])
            self.assertEqual(adapter.geocode(query(source)).status, "accepted")
        adapter, _ = factory([candidate(), candidate(place_id=43)])
        self.assertEqual(adapter.geocode(query("C/ Example, 4")).status, "review_required")
        adapter, _ = factory([candidate(type="houses", addresstype="houses")])
        self.assertEqual(adapter.geocode(query("C/ Example, 4")).status, "review_required")
        for changes in ({"province": "Barcelona"}, {"city": "Elsewhere"},
                        {"house_number": "5"}, {"postcode": "28002"}):
            adapter, _ = factory([candidate(address={**candidate()["address"], **changes})])
            self.assertEqual(adapter.geocode(query("C/ Example, 4")).status, "review_required")

    def test_raw_spanish_administrative_fields_preserved_but_poi_text_omitted(self):
        import urllib.parse
        factory = fixtures.LocationIqFirstPassTests().make
        item = candidate(address={**candidate()["address"], "province": "Madrid",
                                  "state_district": "Madrid", "contact": "omit", "name": "omit"})
        adapter, seen = factory([item])
        outcome = adapter.geocode(query("Calle Example 4"))
        retained = outcome.response["results"][0]["address"]
        self.assertEqual(retained["province"], "Madrid")
        self.assertEqual(retained["state_district"], "Madrid")
        self.assertNotIn("contact", retained)
        self.assertNotIn("name", retained)
        params = urllib.parse.parse_qs(urllib.parse.urlsplit(seen["request"].full_url).query)
        self.assertEqual(params["normalizeaddress"], ["0"])


if __name__ == "__main__":
    unittest.main()
