import json
import socket
import urllib.error
import urllib.parse
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).parents[1]
from pipeline.geocoding import dawa as MODULE
from pipeline.geocoding import geoapify
from pipeline.geocoding.registry import get_adapter


class FakeResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.payload


class DawaAdapterTests(unittest.TestCase):
    def test_registry_returns_provider_adapter(self):
        self.assertIsInstance(get_adapter("dawa"), MODULE.DawaAdapter)
        with self.assertRaises(ValueError):
            get_adapter("unknown-provider")
    @patch.object(MODULE.urllib.request, "urlopen")
    def test_single_match_is_accepted_and_uses_lon_lat_order(self, urlopen):
        urlopen.return_value = FakeResponse([{"id": "address-1", "x": 9.9, "y": 55.5}])
        result = MODULE.DawaAdapter().geocode("Testvej 1, 1000, København, Denmark")
        self.assertEqual(result.status, "accepted")
        self.assertEqual(result.acceptance, "accepted_single_point")
        self.assertEqual((result.latitude, result.longitude), (55.5, 9.9))
        self.assertEqual(result.provider_address_id, "address-1")

    @patch.object(MODULE.urllib.request, "urlopen")
    def test_multiple_matches_require_review(self, urlopen):
        urlopen.return_value = FakeResponse([{"x": 9.9, "y": 55.5}, {"x": 10.0, "y": 55.6}])
        result = MODULE.DawaAdapter().geocode("Testvej 1, 1000, København, Denmark")
        self.assertEqual(result.status, "review_required")
        self.assertIsNone(result.latitude)
        self.assertFalse(result.retryable)

    @patch.object(MODULE.urllib.request, "urlopen", side_effect=OSError("connection refused"))
    def test_transport_failure_is_retryable(self, _urlopen):
        result = MODULE.DawaAdapter().geocode("Testvej 1, 1000, København, Denmark")
        self.assertEqual(result.status, "failed")
        self.assertTrue(result.retryable)
        self.assertEqual(result.response, {"error": "OSError"})


class GeoapifyAdapterTests(unittest.TestCase):
    QUERY = "10 Example Road, Melbourne, VIC 3000, Australia"

    @staticmethod
    def pilot_adapter(**kwargs):
        return geoapify.GeoapifyAdapter(country_code="au", pilot_auto_display=True, **kwargs)

    @staticmethod
    def gb_private_adapter(**kwargs):
        return geoapify.GeoapifyAdapter(country_code="gb", private_source_profile=True, **kwargs)

    def test_key_is_required(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(ValueError, "GEOAPIFY_API_KEY"):
                geoapify.GeoapifyAdapter()

    def test_high_confidence_address_match_is_private_exact_candidate(self):
        payload = {"type": "FeatureCollection", "features": [{
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [12.5, 55.6]},
            "properties": {"place_id": "candidate-1", "result_type": "building",
                           "country_code": "au", "address_line1": "10 Example Road",
                           "rank": {"confidence": 0.98}},
        }]}
        opener = unittest.mock.Mock(return_value=FakeResponse(payload))
        result = self.pilot_adapter(api_key="test-secret", opener=opener).geocode(self.QUERY)
        self.assertEqual(result.status, "accepted")
        self.assertEqual(result.acceptance, "high_confidence_address_match")
        self.assertEqual((result.latitude, result.longitude), (55.6, 12.5))
        self.assertEqual(result.provider_address_id, "candidate-1")
        self.assertNotIn("test-secret", json.dumps(result.response))
        request = opener.call_args.args[0]
        query = urllib.parse.parse_qs(urllib.parse.urlparse(request.full_url).query)
        self.assertEqual(query["filter"], ["countrycode:au"])
        self.assertEqual(query["bias"], ["countrycode:none"])
        self.assertEqual(query["limit"], ["2"])

    def test_generic_geoapify_remains_unfiltered_and_review_gated(self):
        payload = {"features": [{
            "geometry": {"type": "Point", "coordinates": [12.5, 55.6]},
            "properties": {"place_id": "candidate", "result_type": "building"},
        }]}
        opener = unittest.mock.Mock(return_value=FakeResponse(payload))
        result = geoapify.GeoapifyAdapter(api_key="test-secret", opener=opener).geocode("Example address")
        self.assertEqual(result.status, "review_required")
        self.assertEqual(result.acceptance, "review_provider_candidate")
        self.assertEqual((result.latitude, result.longitude), (55.6, 12.5))
        query = urllib.parse.parse_qs(urllib.parse.urlparse(opener.call_args.args[0].full_url).query)
        self.assertNotIn("filter", query)
        self.assertNotIn("bias", query)

    def test_country_mismatch_and_address_mismatch_do_not_return_points(self):
        for country, address in (("nz", "10 Example Road"), ("au", "99 Other Street")):
            payload = {"features": [{
                "geometry": {"coordinates": [144.9, -37.8]},
                "properties": {"place_id": "candidate", "result_type": "building",
                               "country_code": country, "address_line1": address,
                               "rank": {"confidence": 0.99}},
            }]}
            result = self.pilot_adapter(
                api_key="test-secret", opener=unittest.mock.Mock(return_value=FakeResponse(payload))
            ).geocode(self.QUERY)
            self.assertEqual(result.status, "review_required")
            self.assertIsNone(result.latitude)
            self.assertIsNone(result.longitude)

    def test_low_confidence_and_ambiguous_results_do_not_return_points(self):
        feature = {"geometry": {"coordinates": [144.9, -37.8]}, "properties": {
            "result_type": "building", "country_code": "au",
            "address_line1": "10 Example Road", "rank": {"confidence": 0.89},
        }}
        for features in ([feature], [feature, feature]):
            payload = {"features": features}
            result = self.pilot_adapter(
                api_key="test-secret", opener=unittest.mock.Mock(return_value=FakeResponse(payload))
            ).geocode(self.QUERY)
            self.assertEqual(result.status, "review_required")
            self.assertIsNone(result.latitude)

    def test_private_source_profile_accepts_one_viable_match_among_weak_alternatives(self):
        good = {"geometry": {"type": "Point", "coordinates": [-2.5, 55.9]},
                "properties": {"place_id": "good", "result_type": "building", "country_code": "gb",
                               "address_line1": "10 Example Road", "rank": {"confidence": 0.96}}}
        weak = {"geometry": {"type": "Point", "coordinates": [-3, 56]},
                "properties": {"place_id": "weak", "result_type": "building", "country_code": "gb",
                               "address_line1": "Elsewhere Road", "rank": {"confidence": 0.80}}}
        query = "10 Example Road, Exampleton, AB1 2CD, United Kingdom"
        result = self.gb_private_adapter(
            api_key="test-secret", opener=unittest.mock.Mock(return_value=FakeResponse({"features": [good, weak]}))
        ).geocode(query)
        self.assertEqual(result.status, "accepted")
        self.assertEqual(result.provider_address_id, "good")
        self.assertEqual(result.response["_uec_selected_feature_index"], 0)

    def test_private_source_profile_rejects_multiple_viable_or_wrong_country(self):
        base = {"geometry": {"type": "Point", "coordinates": [-2.5, 55.9]},
                "properties": {"result_type": "building", "country_code": "gb",
                               "address_line1": "10 Example Road", "rank": {"confidence": 0.96}}}
        query = "10 Example Road, Exampleton, AB1 2CD, United Kingdom"
        duplicate = json.loads(json.dumps(base))
        outcome = self.gb_private_adapter(
            api_key="test-secret", opener=unittest.mock.Mock(return_value=FakeResponse({"features": [base, duplicate]}))
        ).geocode(query)
        self.assertEqual(outcome.status, "review_required")
        self.assertEqual(outcome.acceptance, "ambiguous_multiple_viable_results")
        wrong_country = json.loads(json.dumps(base))
        wrong_country["properties"]["country_code"] = "ie"
        outcome = self.gb_private_adapter(
            api_key="test-secret", opener=unittest.mock.Mock(return_value=FakeResponse({"features": [wrong_country]}))
        ).geocode(query)
        self.assertEqual(outcome.status, "review_required")
        self.assertIsNone(outcome.latitude)

    def test_city_point_requires_country_and_query_locality_and_is_approximate(self):
        payload = {"features": [{
            "geometry": {"coordinates": [144.9, -37.8]},
            "properties": {"result_type": "city", "country_code": "au", "city": "Melbourne",
                           "rank": {"confidence": 0.94}},
        }]}
        result = self.pilot_adapter(
            api_key="test-secret", opener=unittest.mock.Mock(return_value=FakeResponse(payload))
        ).geocode("10 Example Road, Melbourne, Australia")
        self.assertEqual(result.status, "accepted")
        self.assertEqual(result.acceptance, "approximate_locality_match")
        self.assertEqual(result.precision, "geoapify_locality_point")

        payload["features"][0]["properties"]["city"] = "Sydney"
        mismatch = self.pilot_adapter(
            api_key="test-secret", opener=unittest.mock.Mock(return_value=FakeResponse(payload))
        ).geocode("10 Example Road, Melbourne, Australia")
        self.assertEqual(mismatch.status, "review_required")
        self.assertIsNone(mismatch.latitude)

    def test_invalid_coordinates_fail_closed(self):
        payload = {"features": [{"geometry": {"coordinates": [999, 55]}, "properties": {}}]}
        result = geoapify.GeoapifyAdapter(api_key="test-secret", opener=unittest.mock.Mock(return_value=FakeResponse(payload))).geocode("Example")
        self.assertEqual(result.status, "failed")
        self.assertFalse(result.retryable)
        self.assertEqual(result.response, {"error": "invalid_provider_coordinates"})

    @patch.object(MODULE.urllib.request, "urlopen")
    def test_malformed_payload_fails_closed(self, urlopen):
        urlopen.return_value = FakeResponse({"features": []})
        result = MODULE.DawaAdapter().geocode("Testvej 1, 1000, København, Denmark")
        self.assertEqual(result.status, "failed")
        self.assertFalse(result.retryable)
        self.assertEqual(result.response, {"error": "invalid_provider_schema"})

    @patch.object(MODULE.urllib.request, "urlopen")
    def test_invalid_coordinates_are_not_accepted(self, urlopen):
        urlopen.return_value = FakeResponse([{"id": "bad", "x": 181, "y": float("nan")}])
        result = MODULE.DawaAdapter().geocode("Testvej 1, 1000, København, Denmark")
        self.assertEqual(result.status, "unresolved")
        self.assertEqual(result.acceptance, "invalid_coordinates")

    @patch.object(MODULE.urllib.request, "urlopen")
    def test_http_retry_classification_is_bounded(self, urlopen):
        for status, retryable in ((401, False), (403, False), (429, True), (500, True), (503, True)):
            urlopen.side_effect = urllib.error.HTTPError("https://example.invalid", status, "failure", {}, None)
            result = MODULE.DawaAdapter().geocode("private query")
            self.assertEqual(result.response["status"], status)
            self.assertEqual(result.retryable, retryable)
            self.assertNotIn("private query", json.dumps(result.response))

    @patch.object(MODULE.urllib.request, "urlopen", side_effect=socket.timeout("timed out private query"))
    def test_timeout_is_retryable_and_redacted(self, _urlopen):
        result = MODULE.DawaAdapter().geocode("private query")
        self.assertEqual(result.status, "failed")
        self.assertTrue(result.retryable)
        self.assertNotIn("private query", json.dumps(result.response))

    def test_registry_constructs_geoapify_from_environment(self):
        with patch.dict("os.environ", {"GEOAPIFY_API_KEY": "test-secret"}):
            self.assertIsInstance(get_adapter("geoapify"), geoapify.GeoapifyAdapter)


if __name__ == "__main__":
    unittest.main()
