import json
import os
import unittest
import urllib.request
import uuid
from datetime import datetime, timezone
import psycopg

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

    def test_z_denied_and_factually_rejected_claims_stay_private(self):
        now = datetime.now(timezone.utc)
        with psycopg.connect(self.env.database_url) as db:
            for name, factual_status, approval in (("denied", "unreviewed", "denied"), ("rejected", "rejected", "pending")):
                record, facility, observation, artifact = (uuid.uuid4() for _ in range(4))
                db.execute("INSERT INTO uec.raw_artifacts (artifact_id,storage_key,sha256,byte_size,retrieved_at) VALUES (%s,%s,%s,1,%s)", (artifact, f'e2e-community/{name}', uuid.uuid4().hex * 2, now))
                db.execute("INSERT INTO uec.source_records (source_record_id,source_id,source_record_key,artifact_id,raw_fields,parsed_at) VALUES (%s,'e2e.community',%s,%s,'{}',%s)", (record, name, artifact, now))
                db.execute("INSERT INTO uec.facilities (facility_id,canonical_name,country_code,city) VALUES (%s,%s,'DK','Communityby')", (facility, f'E2E community {name}'))
                db.execute("INSERT INTO uec.observations (observation_id,facility_id,source_record_id,observed_at,observation,classification,ruleset_id,rule_id,classification_category,classification_review_status,default_visible,first_observed_at) VALUES (%s,%s,%s,%s,'{}','{}','community-v1','e2e','slaughter','approved',true,%s)", (observation, facility, record, now, now))
                db.execute("INSERT INTO uec.release_members (release_id,facility_id,observation_id,default_visible) VALUES ('e2e-community',%s,%s,true)", (facility, observation))
                db.execute("INSERT INTO uec.publication_review_events (source_record_id,factual_review_status,privacy_screening_status,maintainer_approval,publication_eligible,reviewer_role) VALUES (%s,%s,'passed',%s,true,'maintainer')", (record, factual_status, approval))
        names = {row['canonical_name'] for row in self.get('/api/v2/locations?profile=community&limit=100')['data']}
        self.assertNotIn('E2E community denied', names)
        self.assertNotIn('E2E community rejected', names)


if __name__ == "__main__":
    unittest.main()
