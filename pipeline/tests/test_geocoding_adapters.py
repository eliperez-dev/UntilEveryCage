import json
import socket
import urllib.error
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
    def test_key_is_required(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(ValueError, "GEOAPIFY_API_KEY"):
                geoapify.GeoapifyAdapter()

    def test_candidate_is_stored_but_requires_review(self):
        payload = {"type": "FeatureCollection", "features": [{
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [12.5, 55.6]},
            "properties": {"place_id": "candidate-1", "result_type": "building"},
        }]}
        opener = unittest.mock.Mock(return_value=FakeResponse(payload))
        result = geoapify.GeoapifyAdapter(api_key="test-secret", opener=opener).geocode("Example address")
        self.assertEqual(result.status, "review_required")
        self.assertEqual((result.latitude, result.longitude), (55.6, 12.5))
        self.assertEqual(result.provider_address_id, "candidate-1")
        self.assertNotIn("test-secret", json.dumps(result.response))

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
