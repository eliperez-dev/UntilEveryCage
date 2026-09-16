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

    def test_private_candidate_preview_requires_auth_and_is_explicitly_labeled(self):
        endpoint = f"http://localhost:{self.env.api_port}/api/dev/preview/candidates?limit=10"
        missing = urllib.request.Request(endpoint)
        with self.assertRaises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(missing, timeout=10)
        self.assertEqual(error.exception.code, 401)
        wrong = urllib.request.Request(endpoint, headers={"X-UEC-Dev-Preview-Token": "wrong"})
        with self.assertRaises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(wrong, timeout=10)
        self.assertEqual(error.exception.code, 401)
        request = urllib.request.Request(endpoint, headers={"X-UEC-Dev-Preview-Token": self.env.dev_preview_token})
        with urllib.request.urlopen(request, timeout=10) as response:
            body = json.loads(response.read())
        self.assertEqual(body["api_version"], "dev-preview-v1")
        self.assertEqual(body["meta"]["test_only"], True)
        self.assertEqual(body["data"][0]["release_status"], "candidate")
        self.assertEqual(body["data"][0]["project_approval"], False)
        self.assertIn("not project-approved", body["data"][0]["preview_label"])
        self.assertEqual(len(body["data"]), 1)
        self.assertEqual(body["data"][0]["canonical_name"], "E2E private candidate")

    def test_filters_do_not_bypass_publication_gate(self):
        for path in ("?category=retail_and_prepared_food", "?display_precision=city", "?lifecycle_status=explicitly_closed"):
            _, body = self.get("/api/v2/locations" + path)
            self.assertEqual(body["data"], [])

    def test_invalid_pagination_is_rejected(self):
        for query in ("limit=invalid", "offset=invalid"):
            with self.subTest(query=query), self.assertRaises(urllib.error.HTTPError) as error:
                self.get(f"/api/v2/locations?{query}")
            self.assertEqual(error.exception.code, 400)

    def test_incomplete_or_conflicting_spatial_queries_are_rejected(self):
        for query in (
            "latitude=55",
            "min_lat=54&min_lon=10&max_lat=53&max_lon=11",
            "latitude=55&longitude=10&radius_km=0",
        ):
            with self.subTest(query=query), self.assertRaises(urllib.error.HTTPError) as error:
                self.get(f"/api/v2/locations?{query}")
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
