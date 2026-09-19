"""Synthetic HTTP checks for community export parity and legacy availability."""

import csv
import hashlib
import io
import json
import os
import unittest
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone

import psycopg

try:
    from .fixture import E2EEnvironment
except ImportError:
    from fixture import E2EEnvironment


class PublicSurfaceSafetyE2ETests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.environ.get("UEC_RUN_E2E") != "1":
            raise unittest.SkipTest("set UEC_RUN_E2E=1 to run Docker-backed E2E tests")
        cls.env = E2EEnvironment().start()
        cls.env.seed_community_scenario()

    @classmethod
    def tearDownClass(cls):
        cls.env.stop()

    def fetch(self, path):
        with urllib.request.urlopen(
            f"http://localhost:{self.env.api_port}{path}", timeout=10
        ) as response:
            return response.headers, response.read()

    def export_rows(self, profile):
        headers, body = self.fetch(f"/api/v2/locations.csv?profile={profile}")
        return headers, list(csv.DictReader(io.StringIO(body.decode("utf-8"))))

    def test_community_csv_matches_api_and_current_suppression(self):
        _, api_body = self.fetch("/api/v2/locations?profile=community&limit=100")
        api_rows = json.loads(api_body)["data"]
        headers, rows = self.export_rows("community")
        self.assertEqual(headers["X-Uec-Export-Profile"], "community")
        self.assertIn("uec-v2-community-locations.csv", headers["Content-Disposition"])
        self.assertEqual(
            {row["facility_id"] for row in rows},
            {row["facility_id"] for row in api_rows},
        )
        self.assertEqual(
            {row["canonical_name"] for row in rows},
            {"E2E community eligible", "E2E community screened-unreviewed"},
        )
        unreviewed = next(
            row for row in rows if row["canonical_name"] == "E2E community screened-unreviewed"
        )
        self.assertEqual(unreviewed["release_profile"], "community")
        self.assertEqual(unreviewed["factual_review_status"], "unreviewed")
        self.assertEqual(unreviewed["privacy_screening_status"], "passed")
        self.assertEqual(unreviewed["project_approval"], "pending")
        self.assertEqual(unreviewed["source_type"], "user_submitted")
        self.assertEqual(unreviewed["reviewer_role"], "")
        self.assertEqual(
            unreviewed["publication_warning"],
            "Unreviewed community claim — not verified by Until Every Cage",
        )
        self.assertIn("Opt-in community profile", unreviewed["profile_notice"])
        self.assertTrue(all(row["profile_notice"] == unreviewed["profile_notice"] for row in rows))
        self.assertFalse(any("unscreened" in row["canonical_name"] for row in rows))

        official_headers, official_rows = self.export_rows("official")
        self.assertIn("uec-v2-official-locations.csv", official_headers["Content-Disposition"])
        self.assertEqual(official_rows, [])

        with psycopg.connect(self.env.database_url) as db:
            db.execute(
                """INSERT INTO uec.record_access_events
                   (source_record_id, action, reason_category, policy_version, maintainer)
                   SELECT source_record_id, 'public_access_revoked', 'privacy', 'ethics-v1', 'e2e'
                   FROM uec.source_records
                   WHERE source_id='e2e.community' AND source_record_key='screened-unreviewed'"""
            )

        _, api_body = self.fetch("/api/v2/locations?profile=community&limit=100")
        _, rows = self.export_rows("community")
        expected = {"E2E community eligible"}
        self.assertEqual({row["canonical_name"] for row in json.loads(api_body)["data"]}, expected)
        self.assertEqual({row["canonical_name"] for row in rows}, expected)

    def test_legacy_locations_route_remains_available(self):
        # No reviewed identity crosswalk exists between these embedded rows and V2.
        # This checks compatibility only; it does not claim suppression propagation.
        _, body = self.fetch("/api/locations?country_code=dk")
        rows = json.loads(body)
        self.assertTrue(rows)
        self.assertTrue(all(row["country"] == "dk" for row in rows))
        self.assertTrue(all("establishment_id" in row for row in rows))


class ReleaseScopedReviewE2ETests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.environ.get("UEC_RUN_E2E") != "1":
            raise unittest.SkipTest("set UEC_RUN_E2E=1 to run Docker-backed E2E tests")
        cls.env = E2EEnvironment().start()
        cls.seed_shared_record()
        cls.env.build_public_read_model("e2e-release-a")
        cls.env.build_public_read_model("e2e-release-b")

    @classmethod
    def tearDownClass(cls):
        cls.env.stop()

    @classmethod
    def seed_shared_record(cls):
        now = datetime.now(timezone.utc)
        cls.record_id = uuid.uuid4()
        cls.facility_id = uuid.uuid4()
        observation_id = uuid.uuid4()
        artifact_id = uuid.uuid4()
        with psycopg.connect(cls.env.database_url) as db:
            db.execute(
                "INSERT INTO uec.sources (source_id,country_code,name,official_url,access_method) "
                "VALUES ('e2e.shared','DK','Synthetic shared source','https://example.invalid/shared','fixture')"
            )
            for release_id, profile in (("e2e-release-a", "official"), ("e2e-release-b", "secondary")):
                db.execute(
                    "INSERT INTO uec.releases (release_id,status,ruleset_version,profile,summary) "
                    "VALUES (%s,'promoted','e2e-v1',%s,'{}')",
                    (release_id, profile),
                )
                manifest = {
                    "eligible_record_count": 1,
                    "manifest_version": "v1",
                    "profile": profile,
                    "release_id": release_id,
                    "ruleset_version": "e2e-v1",
                    "source_ids": ["e2e.shared"],
                }
                serialized = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
                db.execute(
                    "INSERT INTO uec.release_manifests (release_id,manifest,manifest_sha256) "
                    "VALUES (%s,%s::jsonb,%s)",
                    (release_id, serialized, hashlib.sha256(serialized.encode()).hexdigest()),
                )
            db.execute(
                "INSERT INTO uec.raw_artifacts (artifact_id,storage_key,sha256,byte_size,retrieved_at) "
                "VALUES (%s,'e2e/shared',%s,1,%s)",
                (artifact_id, uuid.uuid4().hex * 2, now),
            )
            db.execute(
                "INSERT INTO uec.source_records "
                "(source_record_id,source_id,source_record_key,artifact_id,raw_fields,parsed_at) "
                "VALUES (%s,'e2e.shared','shared',%s,'{}',%s)",
                (cls.record_id, artifact_id, now),
            )
            db.execute(
                "INSERT INTO uec.facilities (facility_id,canonical_name,country_code,city) "
                "VALUES (%s,'E2E shared facility','DK','Testby')",
                (cls.facility_id,),
            )
            db.execute(
                "INSERT INTO uec.observations "
                "(observation_id,facility_id,source_record_id,observed_at,observation,classification,"
                "ruleset_id,rule_id,classification_category,classification_review_status,"
                "default_visible,first_observed_at) "
                "VALUES (%s,%s,%s,%s,'{}','{}','e2e-v1','e2e','slaughter','approved',true,%s)",
                (observation_id, cls.facility_id, cls.record_id, now, now),
            )
            for release_id in ("e2e-release-a", "e2e-release-b"):
                db.execute(
                    "INSERT INTO uec.release_members "
                    "(release_id,facility_id,observation_id,default_visible) VALUES (%s,%s,%s,true)",
                    (release_id, cls.facility_id, observation_id),
                )
                db.execute(
                    "INSERT INTO uec.publication_review_events "
                    "(source_record_id,release_id,factual_review_status,privacy_screening_status,"
                    "maintainer_approval,publication_eligible,reviewer_role,reviewed_at) "
                    "VALUES (%s,%s,'reviewed','passed','approved',true,'maintainer',%s)",
                    (cls.record_id, release_id, now),
                )

    def get_json(self, path):
        with urllib.request.urlopen(f"http://localhost:{self.env.api_port}{path}", timeout=10) as response:
            return json.loads(response.read())

    def get_csv(self, profile):
        with urllib.request.urlopen(
            f"http://localhost:{self.env.api_port}/api/v2/locations.csv?profile={profile}",
            timeout=10,
        ) as response:
            return list(csv.DictReader(io.StringIO(response.read().decode("utf-8"))))

    def test_other_promoted_profile_denial_cannot_relabel_or_remove_official_record(self):
        for profile in ("official", "secondary"):
            listed = self.get_json(f"/api/v2/locations?profile={profile}&limit=100")["data"]
            self.assertEqual([row["facility_id"] for row in listed], [str(self.facility_id)])
            self.assertEqual(listed[0]["project_approval"], "approved")
            self.assertEqual([row["facility_id"] for row in self.get_csv(profile)], [str(self.facility_id)])

        with psycopg.connect(self.env.database_url) as db:
            db.execute(
                "INSERT INTO uec.publication_review_events "
                "(source_record_id,release_id,factual_review_status,privacy_screening_status,"
                "maintainer_approval,publication_eligible,reviewer_role,reviewed_at) "
                "VALUES (%s,'e2e-release-b','rejected','failed','denied',false,'maintainer',%s)",
                (self.record_id, datetime.now(timezone.utc) + timedelta(seconds=1)),
            )
            db.commit()
            eligible = dict(db.execute(
                "SELECT release_id, count(*) FROM uec.map_facilities_display_history "
                "GROUP BY release_id"
            ).fetchall())
        self.assertEqual(eligible, {"e2e-release-a": 1})

        official = self.get_json("/api/v2/locations?profile=official&limit=100")["data"]
        self.assertEqual([row["facility_id"] for row in official], [str(self.facility_id)])
        self.assertEqual(official[0]["factual_review_status"], "reviewed")
        self.assertEqual(official[0]["privacy_screening_status"], "passed")
        self.assertEqual(official[0]["project_approval"], "approved")
        detail = self.get_json(f"/api/v2/locations/{self.facility_id}?profile=official")["data"]
        self.assertEqual(detail["project_approval"], "approved")
        self.assertEqual(detail["privacy_screening_status"], "passed")
        official_csv = self.get_csv("official")
        self.assertEqual([row["facility_id"] for row in official_csv], [str(self.facility_id)])
        self.assertEqual(official_csv[0]["project_approval"], "approved")
        self.assertEqual(self.get_json("/api/v2/locations?profile=secondary")["data"], [])
        self.assertEqual(self.get_csv("secondary"), [])


if __name__ == "__main__":
    unittest.main()
