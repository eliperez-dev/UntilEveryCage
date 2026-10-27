import json
import unittest
import urllib.error
import urllib.parse

from pipeline.geocoding.locationiq import LocationIqAdapter


QUERY = "Musterstraße 12, 12345, Berlin, Berlin, Germany"


def row(**changes):
    value = {
        "place_id": 123, "lat": "52.5200", "lon": "13.4050", "class": "building",
        "type": "house", "addresstype": "building", "display_name": "private POI name",
        "address": {"house_number": "12", "road": "Musterstraße", "postcode": "12345",
                    "city": "Berlin", "state": "Berlin", "state_code": "BE", "country_code": "de"},
        "importance": 0.99, "extra_secret": "do not retain",
    }
    value.update(changes)
    return value


class Response:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def read(self, size=-1):
        return self.payload if size < 0 else self.payload[:size]


class LocationIqAdapterTests(unittest.TestCase):
    def make(self, payload, **kwargs):
        seen = {}

        def opener(request, timeout):
            seen["request"] = request
            seen["timeout"] = timeout
            return Response(payload)

        country_code = kwargs.pop("country_code", "de")
        private_source_profile = kwargs.pop("private_source_profile", True)
        adapter = LocationIqAdapter(api_key="test-secret", opener=opener,
                                    country_code=country_code, private_source_profile=private_source_profile, **kwargs)
        return adapter, seen

    def test_accepts_exact_components_and_builds_bounded_german_request(self):
        adapter, seen = self.make([row()])
        outcome = adapter.geocode(QUERY)
        self.assertEqual(outcome.status, "accepted")
        self.assertEqual((outcome.latitude, outcome.longitude), (52.52, 13.405))
        self.assertEqual(outcome.precision, "locationiq_address_point")
        self.assertEqual(outcome.acceptance, "address_components_match")
        self.assertEqual(outcome.response["_uec_selected_result_index"], 0)
        self.assertNotIn("display_name", str(outcome.response))
        self.assertNotIn("importance", str(outcome.response))
        self.assertNotIn("extra_secret", str(outcome.response))
        request = seen["request"]
        self.assertTrue(request.full_url.startswith("https://eu1.locationiq.com/v1/search?"))
        params = urllib.parse.parse_qs(urllib.parse.urlsplit(request.full_url).query)
        self.assertEqual(params, {"key": ["test-secret"], "q": [QUERY], "format": ["json"],
                                  "countrycodes": ["de"], "addressdetails": ["1"],
                                  "normalizeaddress": ["1"], "normalizecity": ["1"],
                                  "statecode": ["1"], "limit": ["2"]})
        self.assertEqual(request.get_header("Accept-language"), "de")

    def test_rejects_redirects_and_road_result_even_with_address_components(self):
        self.assertIsNone(LocationIqAdapter._NoRedirect().redirect_request(None, None, 302, "Found", {}, "https://other.example/"))
        item = row(addresstype="road")
        adapter, _ = self.make([item])
        self.assertEqual(adapter.geocode(QUERY).status, "review_required")

    def test_accepts_number_before_road_and_legacy_query(self):
        adapter, _ = self.make([row(address={**row()["address"], "road": "Musterstraße", "house_number": "12"})])
        self.assertEqual(adapter.geocode("12 Musterstraße, 12345 Berlin, Germany").status, "accepted")
        self.assertEqual(adapter.geocode("Musterstraße 12, 12345, Berlin, Germany").status, "accepted")

    def test_requires_matching_postcode_locality_and_state(self):
        for key, value in (("postcode", "54321"), ("city", "Potsdam"), ("state", "Bayern")):
            with self.subTest(key=key):
                item = row()
                item["address"][key] = value
                adapter, _ = self.make([item])
                result = adapter.geocode(QUERY)
                self.assertEqual(result.status, "review_required")
                self.assertIsNone(result.latitude)

    def test_ambiguity_and_road_or_city_only_remain_review(self):
        adapter, _ = self.make([row(), row(place_id=456)])
        self.assertEqual(adapter.geocode(QUERY).acceptance, "ambiguous_multiple_viable_results")
        for address in ({"road": "Musterstraße", "postcode": "12345", "city": "Berlin", "country_code": "de"},
                        {"city": "Berlin", "postcode": "12345", "country_code": "de"}):
            adapter, _ = self.make([row(address=address)])
            self.assertEqual(adapter.geocode(QUERY).status, "review_required")

    def test_invalid_coordinates_or_schema_never_accept(self):
        for coords in (("NaN", "13.4"), ("52.5", "Infinity"), ("91", "13.4"), ("52.5", "181"), (True, "13.4")):
            with self.subTest(coords=coords):
                adapter, _ = self.make([row(lat=coords[0], lon=coords[1])])
                self.assertEqual(adapter.geocode(QUERY).status, "review_required")
        adapter, _ = self.make({"oops": "not an array"})
        self.assertEqual(adapter.geocode(QUERY).acceptance, "invalid_provider_schema")

    def test_non_german_profile_cannot_autoaccept_and_empty_or_invalid_query_skips_network(self):
        adapter, _ = self.make([row()], country_code="nl")
        self.assertEqual(adapter.geocode(QUERY).status, "review_required")
        calls = []
        adapter = LocationIqAdapter(api_key="test-secret", country_code="de", private_source_profile=True,
                                    opener=lambda *a, **k: calls.append(a))
        self.assertEqual(adapter.geocode("  ").acceptance, "empty_query")
        self.assertEqual(adapter.geocode("person@example.com").acceptance, "invalid_source_address")
        self.assertEqual(calls, [])

    def test_http_failure_classes_and_transport_redact_details(self):
        for code, retryable, acceptance in ((401, False, "authentication_rejected"), (403, False, "authentication_rejected"),
                                            (429, True, "provider_rate_limited"), (503, True, "provider_http_error"),
                                            (404, False, "no_results")):
            def opener(*_args, **_kwargs):
                raise urllib.error.HTTPError("https://host/?key=test-secret", code, "body test-secret", {}, None)
            result = LocationIqAdapter(api_key="test-secret", opener=opener).geocode(QUERY)
            self.assertEqual((result.acceptance, result.retryable), (acceptance, retryable))
            self.assertNotIn("test-secret", str(result.response))
        result = LocationIqAdapter(api_key="test-secret", opener=lambda *_a, **_k: (_ for _ in ()).throw(OSError("test-secret"))).geocode(QUERY)
        self.assertTrue(result.retryable)
        self.assertNotIn("test-secret", str(result.response))

    def test_missing_key_fails_fast(self):
        from unittest.mock import patch
        with patch.dict("os.environ", {"LOCATIONIQ_API_KEY": ""}):
            with self.assertRaisesRegex(ValueError, "LOCATIONIQ_API_KEY"):
                LocationIqAdapter(api_key="", opener=lambda *_a, **_k: None)
        with self.assertRaisesRegex(ValueError, "country_code"):
            LocationIqAdapter(api_key="ok", country_code="DE")


if __name__ == "__main__":
    unittest.main()
