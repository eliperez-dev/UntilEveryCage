import json
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).parents[1]
from pipeline.geocoding import dawa as MODULE
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
        self.assertIn("connection refused", result.response["error"])


if __name__ == "__main__":
    unittest.main()
