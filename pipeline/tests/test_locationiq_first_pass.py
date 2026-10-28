from __future__ import annotations

import json
import os
import unittest
import urllib.error
import urllib.parse

from pipeline.geocoding.locationiq import LocationIqAdapter
from pipeline.geocoding.private_profiles import profile_by_id, profile_for_source
from pipeline.geocoding.registry import get_adapter


class Response:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, size=-1):
        return self.payload if size < 0 else self.payload[:size]


def candidate(**changes):
    item = {
        "place_id": 42, "lat": "40.4168", "lon": "-3.7038",
        "class": "building", "type": "house", "addresstype": "building",
        "display_name": "private display text", "importance": 0.99,
        "address": {"house_number": "4", "road": "Calle Example", "city": "Madrid",
                    "state": "Comunidad de Madrid", "postcode": "28001", "country_code": "es"},
    }
    item.update(changes)
    return item


def query(address, locality="Madrid", postcode="28001", region="Comunidad de Madrid", country="ES"):
    return json.dumps({"schema_version": "uec-address-query-v1", "address": address,
                       "locality": locality, "postcode": postcode, "region": region,
                       "country_code": country}, ensure_ascii=False)


class LocationIqFirstPassTests(unittest.TestCase):
    def make(self, payload, *, country="es", private=True, query_kind="source_address_first_pass",
             allow_acceptance=True):
        seen = {}

        def opener(request, timeout):
            seen["request"] = request
            seen["timeout"] = timeout
            return Response(payload)

        return LocationIqAdapter(api_key="synthetic-secret", opener=opener, country_code=country,
                                 private_source_profile=private, query_kind=query_kind,
                                 first_pass_source=allow_acceptance), seen

    def test_profiles_register_spain_and_mark_gb_first_pass(self):
        self.assertEqual(profile_for_source("es.locations", provider_id="locationiq")["profile_id"],
                         "locationiq-es-aesan-rgseaa")
        self.assertNotIn("query_kind", profile_by_id("geoapify-es-aesan-rgseaa"))
        for source in ("fsa_approved_establishments", "fss_approved_establishments"):
            profile = profile_for_source(source, provider_id="locationiq")
            self.assertEqual(profile["query_kind"], "source_address_first_pass")
            from unittest.mock import patch
            with patch.dict(os.environ, {"LOCATIONIQ_API_KEY": "synthetic-secret"}):
                adapter = get_adapter("locationiq", private_source_profile_id=profile["profile_id"])
            self.assertEqual(adapter.query_kind, "source_address_first_pass")
        nz_profile = profile_for_source("nz.locations", provider_id="locationiq")
        self.assertEqual(nz_profile["query_kind"], "source_address_first_pass")

    def test_exact_spanish_house_road_locality_province_and_postcode_accept(self):
        adapter, seen = self.make([candidate()])
        source_query = query("Old Street, Calle Example 4, Local 2", postcode="28001")
        outcome = adapter.geocode(source_query)
        self.assertEqual((outcome.status, outcome.precision), ("accepted", "locationiq_address_point"))
        self.assertEqual((outcome.latitude, outcome.longitude), (40.4168, -3.7038))
        params = urllib.parse.parse_qs(urllib.parse.urlsplit(seen["request"].full_url).query)
        self.assertEqual(params["q"], ["Old Street, Calle Example 4, Local 2, Madrid, 28001, Comunidad de Madrid, Spain"])
        self.assertEqual(params["countrycodes"], ["es"])
        self.assertEqual(params["limit"], ["2"])

    def test_county_region_is_retained_and_can_match_and_house_nodes_are_address_results(self):
        county_candidate = candidate(address={**candidate()["address"],
                                        "state": "Different state",
                                        "county": "Comunidad de Madrid"})
        adapter, _ = self.make([county_candidate])
        self.assertEqual(adapter.geocode(query("Calle Example 4")).status, "accepted")
        outcome = adapter.geocode(query("Calle Example 4", region="Comunidad de Madrid"))
        self.assertEqual(outcome.status, "accepted")
        self.assertEqual(outcome.response["results"][0]["address"]["county"], "Comunidad de Madrid")

        house_node = candidate(**{"class": "place", "type": "house"})
        house_node.pop("addresstype")
        adapter, _ = self.make([house_node])
        self.assertEqual(adapter.geocode(query("Calle Example 4")).status, "accepted")
        for invalid in (candidate(**{"class": "place", "type": "houses", "addresstype": "houses"}),
                        candidate(**{"class": "place", "type": "road", "addresstype": "road"})):
            adapter, _ = self.make([invalid])
            self.assertEqual(adapter.geocode(query("Calle Example 4")).status, "review_required")

    def test_freeform_gb_address_without_house_parser_still_calls_provider_and_retains_candidate(self):
        item = candidate(lat="51.5074", lon="-0.1278", address={
            "road": "Example Road", "city": "London", "postcode": "SW1A 1AA", "country_code": "gb"})
        adapter, seen = self.make([item], country="gb")
        source_query = query("Example Road", locality="London", postcode="SW1A 1AA",
                             region=None, country="GB")
        outcome = adapter.geocode(source_query)
        self.assertEqual(outcome.status, "review_required")
        self.assertEqual(outcome.response["results"][0]["address"]["road"], "Example Road")
        self.assertIsNone(outcome.latitude)
        params = urllib.parse.parse_qs(urllib.parse.urlsplit(seen["request"].full_url).query)
        self.assertEqual(params["q"], ["Example Road, London, SW1A 1AA, United Kingdom"])
        self.assertEqual(params["countrycodes"], ["gb"])

    def test_structured_new_zealand_request_matches_one_comma_delimited_address_fragment(self):
        item = candidate(lat="-36.8509", lon="174.7645", address={
            "house_number": "12", "road": "Sample Road", "city": "Auckland",
            "postcode": "1010", "country_code": "nz"})
        adapter, seen = self.make([item], country="nz")
        outcome = adapter.geocode(query("Unit 2, 12 Sample Road", locality="Auckland",
                                        postcode="1010", region=None, country="NZ"))
        self.assertEqual((outcome.status, outcome.precision), ("accepted", "locationiq_address_point"))
        params = urllib.parse.parse_qs(urllib.parse.urlsplit(seen["request"].full_url).query)
        self.assertEqual(params["q"], ["Unit 2, 12 Sample Road, Auckland, 1010, New Zealand"])
        self.assertEqual(params["countrycodes"], ["nz"])
        legacy_candidate = candidate(lat="-36.8509", lon="174.7645", address={
            "house_number": "12", "road": "Sample Road", "city": "Auckland",
            "postcode": "1010", "country_code": "nz"})
        legacy_adapter, _ = self.make([legacy_candidate], country="nz")
        self.assertEqual(legacy_adapter.geocode("12 Sample Road, Auckland, 1010, New Zealand").status,
                         "accepted")

    def test_first_pass_rejects_bad_terminator_or_missing_context_before_request(self):
        calls = []
        adapter = LocationIqAdapter(api_key="synthetic-secret", country_code="es", private_source_profile=True,
                                    query_kind="source_address_first_pass",
                                    opener=lambda *_a, **_k: calls.append(True))
        invalid = ("Calle Example 4, Madrid", json.dumps({"schema_version": "wrong"}),
                   query("Calle Example 4", country="GB"),
                   query("Example Road", locality="", postcode="SW1A 1AA", region=None, country="GB"),
                   json.dumps({"schema_version": "uec-address-query-v1", "address": "x" * 1201,
                               "locality": "Madrid", "postcode": None, "region": None,
                               "country_code": "ES"}))
        for raw_query in invalid:
            self.assertEqual(adapter.geocode(raw_query).acceptance, "invalid_source_address")
        self.assertEqual(calls, [])
        region_only_adapter, seen = self.make([candidate()])
        region_only = region_only_adapter.geocode(query("Calle Example 4", locality="", postcode=None))
        self.assertEqual(region_only.status, "review_required")
        self.assertEqual(len(region_only.response["results"]), 1)
        self.assertIsNotNone(seen.get("request"))

    def test_mismatches_and_ambiguity_keep_candidates_without_coordinates(self):
        source_query = query("Calle Example 4")
        mismatches = (
            candidate(address={**candidate()["address"], "house_number": "6"}),
            candidate(address={**candidate()["address"], "road": "Other Street"}),
            candidate(address={**candidate()["address"], "city": "Seville"}),
            candidate(address={**candidate()["address"], "state": "Catalonia"}),
            candidate(address={**candidate()["address"], "postcode": "28002"}),
            candidate(address={**candidate()["address"], "country_code": "pt"}),
            candidate(lat="0", lon="0"),
        )
        for item in mismatches:
            with self.subTest(address=item["address"]):
                adapter, _ = self.make([item])
                outcome = adapter.geocode(source_query)
                self.assertEqual(outcome.status, "review_required")
                self.assertIsNone(outcome.latitude)
                self.assertEqual(len(outcome.response["results"]), 1)
        adapter, _ = self.make([candidate(), candidate(place_id=43)])
        self.assertEqual(adapter.geocode(source_query).acceptance, "ambiguous_multiple_viable_results")

    def test_unresolved_candidate_is_safely_retained_and_unprofiled_never_accepts(self):
        sparse = {"address": {"road": "Calle Example", "city": "Madrid", "country_code": "es"}}
        adapter, _ = self.make([sparse])
        outcome = adapter.geocode(query("Calle Example"))
        self.assertEqual(outcome.status, "review_required")
        self.assertEqual(outcome.response["results"], [{"address": sparse["address"]}])
        adapter, seen = self.make([candidate()], allow_acceptance=False)
        source_query = query("Calle Example 4")
        outcome = adapter.geocode(source_query)
        self.assertEqual(outcome.status, "review_required")
        self.assertEqual(len(outcome.response["results"]), 1)
        self.assertIsNotNone(seen.get("request"))

    def test_provider_schema_auth_rate_limit_and_secrets_are_sanitized(self):
        bad_schema, _ = self.make({"unexpected": True})
        self.assertEqual(bad_schema.geocode(query("Calle Example 4")).acceptance,
                         "invalid_provider_schema")
        for status, expected in ((401, "authentication_rejected"), (429, "provider_rate_limited")):
            def fail(*_args, status=status, **_kwargs):
                raise urllib.error.HTTPError("https://provider/?key=synthetic-secret", status,
                                             "synthetic-secret", {}, None)
            adapter = LocationIqAdapter(api_key="synthetic-secret", country_code="es",
                                        private_source_profile=True, query_kind="source_address_first_pass",
                                        opener=fail)
            outcome = adapter.geocode(query("Calle Example 4"))
            self.assertEqual(outcome.acceptance, expected)
            self.assertNotIn("synthetic-secret", str(outcome.response))
            self.assertNotIn("synthetic-secret", repr(outcome))
        self.assertTrue(outcome.retryable)


if __name__ == "__main__":
    unittest.main()
