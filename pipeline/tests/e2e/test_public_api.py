import json
import os
import unittest
import urllib.error
import urllib.request

try:
    from .fixture import E2EEnvironment
except ImportError:
    from fixture import E2EEnvironment

class PublicApiE2ETests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.environ.get("UEC_RUN_E2E") != "1":
            raise unittest.SkipTest("set UEC_RUN_E2E=1 to run Docker-backed E2E tests")
        cls.env = E2EEnvironment().start()

    @classmethod
    def tearDownClass(cls):
        cls.env.stop()

    def get(self, path):
        with urllib.request.urlopen(f"http://localhost:{self.env.api_port}{path}", timeout=10) as response:
            return response.status, json.loads(response.read())

    def test_default_is_empty_before_promotion(self):
        status, body = self.get("/api/v2/locations?country_code=DK")
        self.assertEqual(status, 200); self.assertEqual(body["api_version"], "v2"); self.assertEqual(body["data"], [])

    def test_filters_do_not_bypass_publication_gate(self):
        for path in ("?category=retail_and_prepared_food", "?display_precision=city", "?lifecycle_status=explicitly_closed"):
            _, body = self.get("/api/v2/locations" + path)
            self.assertEqual(body["data"], [])

    def test_invalid_pagination_is_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.get("/api/v2/locations?limit=invalid")
        self.assertEqual(error.exception.code, 400)

    def test_profile_is_explicit_and_mismatch_does_not_leak_records(self):
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.get("/api/v2/locations?profile=invalid")
        self.assertEqual(error.exception.code, 400)
        status, body = self.get("/api/v2/locations?profile=community")
        self.assertEqual(status, 200)
        self.assertEqual(body["data"], [])
        self.assertEqual(body["meta"]["profile"], "community")

    def test_cursor_and_offset_cannot_be_combined(self):
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.get("/api/v2/locations?cursor=00000000-0000-0000-0000-000000000000&offset=1")
        self.assertEqual(error.exception.code, 400)

    def test_filter_metadata_is_versioned_and_allowlisted(self):
        status, body = self.get("/api/v2/discovery/filters")
        self.assertEqual(status, 200)
        self.assertEqual(body["api_version"], "v2")
        self.assertIn("community", body["dimensions"]["profile"]["values"])
        self.assertNotIn("address", body["dimensions"])

    def test_facets_apply_filters_and_never_include_restricted_record(self):
        status, body = self.get('/api/v2/discovery/facets?profile=official&category=slaughter')
        self.assertEqual(status, 200)
        self.assertEqual(body['meta']['release_id'], 'e2e-promoted')
        self.assertEqual(body['dimensions']['category'], [{'value': 'slaughter', 'count': 1}])
        self.assertNotIn('restricted', json.dumps(body))
        status, empty = self.get('/api/v2/discovery/facets?country_code=ZZ')
        self.assertEqual(status, 200)
        self.assertEqual(empty['dimensions']['category'], [])

    def test_combination_filters_and_zero_result_are_deterministic(self):
        rows = self.get('/api/v2/locations?country_code=DK&category=slaughter&display_precision=exact&limit=10')['data']
        self.assertEqual(len(rows), 1)
        restricted = self.get('/api/v2/locations?country_code=DK&category=retail_and_prepared_food&limit=10')['data']
        self.assertEqual(restricted, [])
        empty = self.get('/api/v2/locations?country_code=ZZ&limit=10')
        self.assertEqual(empty['data'], [])

    def test_unknown_controlled_filter_is_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.get('/api/v2/locations?category=arbitrary')
        self.assertEqual(error.exception.code, 400)

if __name__ == "__main__":
    unittest.main()
