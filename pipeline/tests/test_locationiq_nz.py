"""Synthetic New Zealand LocationIQ matching tests; no provider calls."""
from __future__ import annotations

import json
import urllib.parse
import unittest

from pipeline.geocoding.locationiq import LocationIqAdapter


class Response:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def read(self, size=-1):
        return self.payload if size < 0 else self.payload[:size]


def result(**changes):
    value = {
        "place_id": 8123, "lat": "-36.8509", "lon": "174.7645",
        "class": "building", "type": "house", "addresstype": "building",
        "importance": 0.99, "display_name": "private display text",
        "address": {"house_number": "12", "road": "Sample Road", "postcode": "1010",
                    "city": "Auckland", "suburb": "Newmarket", "country_code": "nz"},
    }
    value.update(changes)
    return value


class LocationIqNewZealandTests(unittest.TestCase):
    def make(self, payload):
        seen = {}

        def opener(request, timeout):
            seen["request"] = request
            seen["timeout"] = timeout
            return Response(payload)

        adapter = LocationIqAdapter(api_key="test-secret", opener=opener,
                                    country_code="nz", private_source_profile=True)
        return adapter, seen

    def test_accepts_exact_road_number_town_and_optional_postcode(self):
        for query in ("12 Sample Road, Newmarket, New Zealand",
                      "Sample Road 12, Newmarket 1010, New Zealand",
                      "12 Sample Road, 1010 Newmarket, New Zealand"):
            with self.subTest(query=query):
                adapter, seen = self.make([result()])
                outcome = adapter.geocode(query)
                self.assertEqual(outcome.status, "accepted")
                self.assertEqual(outcome.acceptance, "address_components_match")
                self.assertEqual(outcome.precision, "locationiq_address_point")
                self.assertEqual(outcome.match_method, "locationiq_forward")
                self.assertEqual((outcome.latitude, outcome.longitude), (-36.8509, 174.7645))
                self.assertNotIn("importance", str(outcome.response))
                params = urllib.parse.parse_qs(urllib.parse.urlsplit(seen["request"].full_url).query)
                self.assertEqual(params["countrycodes"], ["nz"])
                self.assertEqual(seen["request"].get_header("Accept-language"), "en")

    def test_exact_match_rejects_wrong_country_bounds_street_number_locality_or_postcode(self):
        cases = (
            (result(address={**result()["address"], "country_code": "au"}), "12 Sample Road, Newmarket, New Zealand"),
            (result(lat="-33.86", lon="151.21", address={**result()["address"], "country_code": "nz"}),
             "12 Sample Road, Newmarket, New Zealand"),
            (result(address={**result()["address"], "road": "Other Road"}),
             "12 Sample Road, Newmarket, New Zealand"),
            (result(address={**result()["address"], "house_number": "14"}),
             "12 Sample Road, Newmarket, New Zealand"),
            (result(address={**result()["address"], "suburb": "Parnell"}),
             "12 Sample Road, Newmarket, New Zealand"),
            (result(address={**result()["address"], "postcode": "1020"}),
             "12 Sample Road, Newmarket 1010, New Zealand"),
            (result(address={key: value for key, value in result()["address"].items()
                             if key not in {"city", "town", "municipality", "village", "suburb"}}),
             "12 Sample Road, Newmarket, New Zealand"),
        )
        for payload, query in cases:
            with self.subTest(address=payload["address"], query=query):
                adapter, _ = self.make([payload])
                outcome = adapter.geocode(query)
                self.assertEqual(outcome.status, "review_required")
                self.assertIsNone(outcome.latitude)
                self.assertIsNone(outcome.longitude)

    def test_accepts_nominatim_place_house_address_node_only_for_nz(self):
        for addresstype in (None, "house", "building"):
            address_node = result(**{"class": "place", "type": "house"})
            if addresstype is None:
                address_node.pop("addresstype")
            else:
                address_node["addresstype"] = addresstype
            adapter, _ = self.make([address_node])
            outcome = adapter.geocode("12 Sample Road, Newmarket, New Zealand")
            with self.subTest(addresstype=addresstype):
                self.assertEqual(outcome.status, "accepted")
                self.assertEqual(outcome.precision, "locationiq_address_point")

    def test_rejects_place_city_and_interpolated_houses(self):
        for candidate in (
            result(**{"class": "place", "type": "city", "addresstype": "city"}),
            result(**{"class": "place", "type": "houses", "addresstype": "houses"}),
        ):
            with self.subTest(class_type=(candidate["class"], candidate["type"])):
                adapter, _ = self.make([candidate])
                outcome = adapter.geocode("12 Sample Road, Newmarket, New Zealand")
                self.assertEqual(outcome.status, "review_required")
                self.assertIsNone(outcome.latitude)

    def test_requires_physical_address_and_town_and_rejects_ambiguous_matches(self):
        for query in ("Sample Road, Newmarket, New Zealand",
                      "12 Sample Road, New Zealand",
                      "Auckland, New Zealand",
                      "12 Sample Road, Newmarket, Australia"):
            adapter, _ = self.make([result()])
            self.assertEqual(adapter.geocode(query).acceptance, "invalid_source_address")

        adapter, _ = self.make([result(), result(place_id=8124)])
        outcome = adapter.geocode("12 Sample Road, Newmarket, New Zealand")
        self.assertEqual(outcome.status, "review_required")
        self.assertEqual(outcome.acceptance, "ambiguous_multiple_viable_results")

    def test_parser_is_country_specific_and_german_parser_interface_is_unchanged(self):
        self.assertEqual(LocationIqAdapter._parse_nz_query(
            "12 Sample Road, Newmarket 1010, New Zealand"),
            ("Sample Road", "12", "Newmarket", "1010"))
        self.assertEqual(LocationIqAdapter._parse_query(
            "Musterstraße 12, 12345, Berlin, Berlin, Germany"),
            ("Musterstraße 12", "12345", "Berlin", "Berlin"))


if __name__ == "__main__":
    unittest.main()
