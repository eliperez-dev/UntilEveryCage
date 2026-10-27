from __future__ import annotations

import json
import unittest
import urllib.parse

from pipeline.geocoding.locationiq import LocationIqAdapter


class Response:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, size=-1):
        return self.payload if size < 0 else self.payload[:size]


def result(**changes):
    value = {
        "place_id": 142, "lat": "51.5074", "lon": "-0.1278",
        "class": "building", "type": "house", "addresstype": "building",
        "display_name": "must not be retained", "importance": 0.8,
        "address": {"house_number": "12", "road": "Example Road",
                    "city": "London", "postcode": "SW1A 1AA", "country_code": "gb"},
    }
    value.update(changes)
    return value


class LocationIqUnitedKingdomTests(unittest.TestCase):
    def make(self, payload):
        seen = {}

        def opener(request, timeout):
            seen["request"] = request
            return Response(payload)

        return (LocationIqAdapter(api_key="synthetic-key", opener=opener,
                                  country_code="gb", private_source_profile=True), seen)

    def test_canonical_query_uses_only_unambiguous_numbered_road_locality_postcode(self):
        query = LocationIqAdapter.canonical_uk_query(
            ["Example Foods Ltd", "Unit 4, 12 Example Road", "Industrial Estate"],
            "London", "sw1a1aa")
        self.assertEqual(query, "12 Example Road, London, SW1A 1AA, United Kingdom")
        parsed = LocationIqAdapter._parse_gb_query(query)
        self.assertEqual(parsed, ("Example Road", "12", "London", "SW1A1AA"))

    def test_canonical_query_fails_closed_for_ambiguous_or_incomplete_source(self):
        base = (["12 Example Road"], "London", "SW1A 1AA")
        self.assertIsNone(LocationIqAdapter.canonical_uk_query(
            ["12 Example Road", "14 Example Lane"], "London", "SW1A 1AA"))
        self.assertIsNone(LocationIqAdapter.canonical_uk_query(base[0], "", base[2]))
        self.assertIsNone(LocationIqAdapter.canonical_uk_query(base[0], base[1], "invalid"))
        self.assertIsNone(LocationIqAdapter.canonical_uk_query(["Example Road"], base[1], base[2]))
        self.assertIsNone(LocationIqAdapter.canonical_uk_query(["Unit 4, Example Foods Ltd"], base[1], base[2]))

    def test_accepts_only_one_exact_gb_address_and_uses_english_gb_request(self):
        query = "12 Example Road, London, SW1A 1AA, United Kingdom"
        adapter, seen = self.make([result()])
        outcome = adapter.geocode(query)
        self.assertEqual(outcome.status, "accepted")
        self.assertEqual(outcome.acceptance, "address_components_match")
        self.assertEqual((outcome.latitude, outcome.longitude), (51.5074, -0.1278))
        self.assertEqual(outcome.precision, "locationiq_address_point")
        self.assertNotIn("display_name", str(outcome.response))
        self.assertNotIn("importance", str(outcome.response))
        params = urllib.parse.parse_qs(urllib.parse.urlsplit(seen["request"].full_url).query)
        self.assertEqual(params["countrycodes"], ["gb"])
        self.assertEqual(params["q"], [query])
        self.assertEqual(seen["request"].get_header("Accept-language"), "en")

    def test_mismatch_ambiguity_nonaddress_and_out_of_bounds_remain_review(self):
        query = "12 Example Road, London, SW1A 1AA, United Kingdom"
        variants = (
            result(address={**result()["address"], "house_number": "14"}),
            result(address={**result()["address"], "road": "Other Road"}),
            result(address={**result()["address"], "city": "Bristol"}),
            result(address={**result()["address"], "postcode": "SW1A 2AA"}),
            result(address={**result()["address"], "country_code": "ie"}),
            result(lat="54.0", lon="-10.0"),
            result(**{"class": "highway", "type": "road", "addresstype": "road"}),
        )
        for item in variants:
            with self.subTest(item=item):
                adapter, _ = self.make([item])
                outcome = adapter.geocode(query)
                self.assertEqual(outcome.status, "review_required")
                self.assertIsNone(outcome.latitude)
        adapter, _ = self.make([result(), result(place_id=143)])
        self.assertEqual(adapter.geocode(query).acceptance, "ambiguous_multiple_viable_results")

    def test_invalid_uk_query_does_not_call_provider(self):
        calls = []
        adapter = LocationIqAdapter(api_key="synthetic-key", country_code="gb",
                                    private_source_profile=True,
                                    opener=lambda *_args, **_kwargs: calls.append(True))
        outcome = adapter.geocode("12 Example Road, London, no-postcode, United Kingdom")
        self.assertEqual(outcome.acceptance, "invalid_source_address")
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
