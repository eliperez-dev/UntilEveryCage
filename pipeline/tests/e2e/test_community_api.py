import json
import os
import unittest
import urllib.request

try:
    from .fixture import E2EEnvironment
except ImportError:
    from fixture import E2EEnvironment


class CommunityProfileE2ETests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.environ.get("UEC_RUN_E2E") != "1":
            raise unittest.SkipTest("set UEC_RUN_E2E=1 to run Docker-backed E2E tests")
        cls.env = E2EEnvironment().start()
        cls.env.seed_community_scenario()

    @classmethod
    def tearDownClass(cls):
        cls.env.stop()

    def get(self, path):
        with urllib.request.urlopen(f"http://localhost:{self.env.api_port}{path}") as response:
            return json.loads(response.read())

    def test_community_profile_is_hidden_from_official_default(self):
        response = self.get("/api/v2/locations?limit=100")
        self.assertEqual(response["meta"]["profile"], "official")
        self.assertEqual(response["data"], [])

    def test_opt_in_returns_only_screened_approved_claim(self):
        response = self.get("/api/v2/locations?profile=community&limit=100")
        self.assertEqual(response["meta"]["profile"], "community")
        self.assertEqual([row["canonical_name"] for row in response["data"]], ["E2E community eligible"])
        row = response["data"][0]
        self.assertEqual(row["source_type"], "user_submitted")
        self.assertEqual(row["provenance_source_id"], "e2e.community")
        self.assertEqual(row["provenance_source_name"], "Synthetic community source")
        self.assertEqual(row["provenance_source_url"], "https://example.invalid/community")

    def test_source_filter_cannot_bypass_publication_gate(self):
        response = self.get("/api/v2/locations?profile=community&source_type=user_submitted&limit=100")
        self.assertEqual(len(response["data"]), 1)
        self.assertEqual(response["data"][0]["canonical_name"], "E2E community eligible")


if __name__ == "__main__":
    unittest.main()
