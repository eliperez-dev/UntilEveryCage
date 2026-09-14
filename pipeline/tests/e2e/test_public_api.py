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
        cls.env.seed_private_candidate_scenario()

    @classmethod
    def tearDownClass(cls):
        cls.env.stop()

    def get(self, path):
        with urllib.request.urlopen(f"http://localhost:{self.env.api_port}{path}", timeout=10) as response:
            return response.status, json.loads(response.read())

    def test_default_is_empty_before_promotion(self):
        status, body = self.get("/api/v2/locations?country_code=DK")
        self.assertEqual(status, 200); self.assertEqual(body["api_version"], "v2"); self.assertEqual(body["data"], [])

    def test_candidate_only_record_is_absent_from_every_public_surface(self):
        # A candidate can contain otherwise publishable-looking evidence, but
        # public APIs must select promoted releases only. The future private
        # preview path must remain a separate, explicitly gated interface.
        candidate = self.env.private_candidate_facility_id
        _, body = self.get("/api/v2/locations?profile=official&limit=100")
        self.assertNotIn(str(candidate), json.dumps(body))
        try:
            with urllib.request.urlopen(
                f"http://localhost:{self.env.api_port}/api/v2/locations.csv?profile=official",
                timeout=10,
            ) as response:
                self.assertNotIn("E2E private candidate", response.read().decode())
        except urllib.error.HTTPError as error:
            self.assertEqual(error.code, 404)
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.get(f"/api/v2/locations/{candidate}?profile=official")
        self.assertEqual(error.exception.code, 404)

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

    def test_facets_requires_a_promoted_release(self):
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.get('/api/v2/discovery/facets?profile=official&category=slaughter')
        self.assertEqual(error.exception.code, 404)
        self.assertEqual(json.loads(error.exception.read())['error']['code'], 'release_not_found')

    def test_unknown_controlled_filter_is_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.get('/api/v2/locations?category=arbitrary')
        self.assertEqual(error.exception.code, 400)

if __name__ == "__main__":
    unittest.main()
