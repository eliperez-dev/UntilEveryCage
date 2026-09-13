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
        with urllib.request.urlopen(f"http://localhost:{self.env.api_port}{path}", timeout=10) as response:
            return json.loads(response.read())

    def test_community_profile_is_hidden_from_official_default(self):
        response = self.get("/api/v2/locations?limit=100")
        self.assertEqual(response["meta"]["profile"], "official")
        self.assertEqual(response["data"], [])

    def test_opt_in_returns_screened_approved_and_unreviewed_claims(self):
        response = self.get("/api/v2/locations?profile=community&limit=100")
        self.assertEqual(response["meta"]["profile"], "community")
        rows = {row["canonical_name"]: row for row in response["data"]}
        self.assertEqual(set(rows), {"E2E community eligible", "E2E community screened-unreviewed"})
        row = rows["E2E community eligible"]
        self.assertEqual(row["source_type"], "user_submitted")
        self.assertEqual(row["publication_profile"], "community")
        self.assertEqual(row["factual_review_status"], "reviewed")
        self.assertEqual(row["privacy_screening_status"], "passed")
        self.assertEqual(row["project_approval"], "approved")
        self.assertEqual(row["provenance_source_id"], "e2e.community")
        self.assertEqual(row["provenance_source_name"], "Synthetic community source")
        self.assertEqual(row["provenance_source_url"], "https://example.invalid/community")
        unreviewed = rows["E2E community screened-unreviewed"]
        self.assertEqual(unreviewed["factual_review_status"], "unreviewed")
        self.assertEqual(unreviewed["privacy_screening_status"], "passed")
        self.assertEqual(unreviewed["project_approval"], "pending")
        self.assertEqual(unreviewed["publication_warning"], "Unreviewed community claim — not verified by Until Every Cage")

    def test_source_filter_cannot_bypass_publication_gate(self):
        response = self.get("/api/v2/locations?profile=community&source_type=user_submitted&limit=100")
        self.assertEqual({row["canonical_name"] for row in response["data"]}, {"E2E community eligible", "E2E community screened-unreviewed"})

    def test_screened_unreviewed_detail_retains_warning(self):
        response = self.get("/api/v2/locations?profile=community&limit=100")
        row = next(row for row in response["data"] if row["canonical_name"] == "E2E community screened-unreviewed")
        detail = self.get(f"/api/v2/locations/{row['facility_id']}?profile=community")
        self.assertEqual(detail["data"]["facility_id"], row["facility_id"])
        self.assertEqual(detail["data"]["publication_warning"], "Unreviewed community claim — not verified by Until Every Cage")

    def test_unscreened_claim_never_becomes_public(self):
        response = self.get("/api/v2/locations?profile=community&limit=100")
        self.assertNotIn("E2E community unscreened", {row["canonical_name"] for row in response["data"]})


if __name__ == "__main__":
    unittest.main()
