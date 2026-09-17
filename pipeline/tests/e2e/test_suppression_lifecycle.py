"""Synthetic suppression lifecycle coverage for every controlled V2 route."""

import csv
import hashlib
import importlib.util
import io
import json
import os
import unittest
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import psycopg

try:
    from .fixture import E2EEnvironment
except ImportError:
    from fixture import E2EEnvironment


ROOT = Path(__file__).parents[2]


def load_script(path):
    spec = importlib.util.spec_from_file_location(path.stem.replace("-", "_"), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


VALIDATE = load_script(ROOT / "scripts/stages/validate-release.py")
PROMOTE = load_script(ROOT / "scripts/stages/promote-release.py")
WORKER = load_script(ROOT / "scripts/stages/geocode-worker.py")


class SuppressionLifecycleE2ETests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.environ.get("UEC_RUN_E2E") != "1":
            raise unittest.SkipTest("set UEC_RUN_E2E=1 to run Docker-backed E2E tests")
        cls.env = E2EEnvironment().start()
        cls.seed_synthetic_fixture()

    @classmethod
    def tearDownClass(cls):
        cls.env.stop()

    @classmethod
    def seed_synthetic_fixture(cls):
        now = datetime.now(timezone.utc)
        cls.private_marker = f"synthetic-private-{uuid.uuid4().hex}"
        cls.source_record_id = uuid.uuid4()
        cls.facility_id = uuid.uuid4()
        cls.observation_id = uuid.uuid4()
        artifact_id = uuid.uuid4()
        cls.case_id = uuid.uuid4()
        with psycopg.connect(cls.env.database_url) as db:
            with db.transaction():
                db.execute(
                    "INSERT INTO uec.sources (source_id,country_code,name,official_url,access_method) "
                    "VALUES ('e2e.suppression','DK','Synthetic suppression source',"
                    "'https://example.invalid/suppression','fixture')"
                )
                db.execute(
                    "INSERT INTO uec.releases (release_id,status,ruleset_version,profile,summary) "
                    "VALUES ('e2e-suppression-old','promoted','synthetic-v1','official','{}')"
                )
                manifest = {
                    "eligible_record_count": 1,
                    "manifest_version": "v1",
                    "profile": "official",
                    "release_id": "e2e-suppression-old",
                    "ruleset_version": "synthetic-v1",
                    "source_ids": ["e2e.suppression"],
                }
                encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
                db.execute(
                    "INSERT INTO uec.release_manifests (release_id,manifest,manifest_sha256) VALUES (%s,%s::jsonb,%s)",
                    ("e2e-suppression-old", encoded, hashlib.sha256(encoded.encode()).hexdigest()),
                )
                db.execute(
                    "INSERT INTO uec.raw_artifacts (artifact_id,storage_key,sha256,byte_size,retrieved_at) "
                    "VALUES (%s,'e2e/suppression/old',%s,1,%s)",
                    (artifact_id, uuid.uuid4().hex * 2, now),
                )
                db.execute(
                    "INSERT INTO uec.source_records "
                    "(source_record_id,source_id,source_record_key,artifact_id,raw_fields,parsed_at) "
                    "VALUES (%s,'e2e.suppression','same-source-key',%s,%s::jsonb,%s)",
                    (cls.source_record_id, artifact_id, json.dumps({"private": cls.private_marker}), now),
                )
                db.execute(
                    "INSERT INTO uec.facilities "
                    "(facility_id,canonical_name,country_code,street_address,postal_code,city) "
                    "VALUES (%s,'Synthetic eligible target','DK',%s,'99999','Suppressionby')",
                    (cls.facility_id, cls.private_marker),
                )
                db.execute(
                    "INSERT INTO uec.observations "
                    "(observation_id,facility_id,source_record_id,observed_at,observation,classification,"
                    "ruleset_id,rule_id,classification_category,classification_review_status,default_visible,"
                    "coordinate_review_status,first_observed_at) VALUES (%s,%s,%s,%s,'{}','{}','synthetic-v1',"
                    "'fixture','slaughter','approved',true,'approved',%s)",
                    (cls.observation_id, cls.facility_id, cls.source_record_id, now, now),
                )
                db.execute(
                    "INSERT INTO uec.release_members (release_id,facility_id,observation_id,default_visible) "
                    "VALUES ('e2e-suppression-old',%s,%s,true)",
                    (cls.facility_id, cls.observation_id),
                )
                db.execute(
                    "INSERT INTO uec.publication_review_events "
                    "(source_record_id,release_id,factual_review_status,privacy_screening_status,"
                    "maintainer_approval,publication_eligible,reviewer_role) VALUES (%s,'e2e-suppression-old',"
                    "'reviewed','passed','approved',true,'maintainer')",
                    (cls.source_record_id,),
                )
                db.execute(
                    "INSERT INTO uec.geocode_results "
                    "(source_record_id,provider_id,query,match_method,status,attempt_number,result,queried_at) "
                    "VALUES (%s,'synthetic',%s,'fixture','accepted',1,ST_SetSRID(ST_MakePoint(12,56),4326)::geography,%s)",
                    (cls.source_record_id, cls.private_marker, now),
                )
        cls.env.build_public_read_model("e2e-suppression-old")

    def get_json(self, path):
        with urllib.request.urlopen(f"http://localhost:{self.env.api_port}{path}", timeout=10) as response:
            return response.status, json.loads(response.read())

    def get_csv(self):
        with urllib.request.urlopen(
            f"http://localhost:{self.env.api_port}/api/v2/locations.csv?profile=official", timeout=10
        ) as response:
            return response.status, response.read().decode("utf-8")

    def test_fixture_is_available_before_suppression(self):
        status, body = self.get_json("/api/v2/locations?limit=100")
        self.assertEqual(status, 200)
        self.assertEqual([row["facility_id"] for row in body["data"]], [str(self.facility_id)])
        status, detail = self.get_json(f"/api/v2/locations/{self.facility_id}")
        self.assertEqual(status, 200)
        self.assertEqual(detail["data"]["facility_id"], str(self.facility_id))
        _, csv_body = self.get_csv()
        self.assertIn("Synthetic eligible target", csv_body)
        with psycopg.connect(self.env.database_url) as db:
            self.assertEqual(
                db.execute("SELECT count(*) FROM uec.map_facilities_public WHERE source_record_id=%s", (self.source_record_id,)).fetchone()[0],
                1,
            )

    def suppress(self):
        now = datetime.now(timezone.utc)
        with psycopg.connect(self.env.database_url) as db:
            with db.transaction():
                if db.execute("SELECT 1 FROM uec.suppression_cases WHERE case_id=%s", (self.case_id,)).fetchone():
                    return
                db.execute(
                    "INSERT INTO uec.suppression_cases "
                    "(case_id,status,reason_category,policy_version,actor,decision,created_at) "
                    "VALUES (%s,'active','privacy','ethics-v1','synthetic-operator','suppress',%s)",
                    (self.case_id, now),
                )
                db.execute(
                    "INSERT INTO uec.suppression_references "
                    "(case_id,source_id,source_record_key,scope) VALUES (%s,'e2e.suppression','same-source-key','whole_record')",
                    (self.case_id,),
                )

    def test_suppression_covers_api_map_facets_export_and_historical_view(self):
        self.suppress()
        status, body = self.get_json("/api/v2/locations?limit=100")
        self.assertEqual(status, 200)
        self.assertEqual(body["data"], [])
        with self.assertRaises(urllib.error.HTTPError) as detail_error:
            self.get_json(f"/api/v2/locations/{self.facility_id}")
        self.assertEqual(detail_error.exception.code, 404)
        status, facets = self.get_json("/api/v2/discovery/facets?category=slaughter")
        self.assertEqual(status, 200)
        self.assertEqual(facets["dimensions"]["category"], [])
        _, csv_body = self.get_csv()
        self.assertNotIn("Synthetic eligible target", csv_body)
        self.assertNotIn(self.private_marker, csv_body)
        with psycopg.connect(self.env.database_url) as db:
            for view in ("map_facilities_public", "map_facilities_display", "map_facilities_display_history"):
                self.assertEqual(
                    db.execute(f"SELECT count(*) FROM uec.{view} WHERE source_record_id=%s", (self.source_record_id,)).fetchone()[0],
                    0,
                )
            self.assertEqual(
                db.execute("SELECT count(*) FROM uec.public_access_restricted WHERE source_record_id=%s", (self.source_record_id,)).fetchone()[0],
                1,
            )

    def test_reimport_new_geocode_and_release_reconstruction_stay_suppressed(self):
        self.suppress()
        artifact_id, record_id, observation_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        now = datetime.now(timezone.utc) + timedelta(seconds=1)
        with psycopg.connect(self.env.database_url) as db:
            with db.transaction():
                db.execute(
                    "INSERT INTO uec.raw_artifacts (artifact_id,storage_key,sha256,byte_size,retrieved_at) VALUES (%s,'e2e/suppression/new',%s,1,%s)",
                    (artifact_id, uuid.uuid4().hex * 2, now),
                )
                db.execute(
                    "INSERT INTO uec.source_records (source_record_id,source_id,source_record_key,artifact_id,raw_fields,parsed_at) VALUES (%s,'e2e.suppression','same-source-key',%s,%s::jsonb,%s)",
                    (record_id, artifact_id, json.dumps({"private": self.private_marker}), now),
                )
                db.execute(
                    "INSERT INTO uec.observations (observation_id,facility_id,source_record_id,observed_at,observation,classification,ruleset_id,rule_id,classification_category,classification_review_status,default_visible,coordinate_review_status,first_observed_at) VALUES (%s,%s,%s,%s,'{}','{}','synthetic-v2','fixture','slaughter','approved',true,'approved',%s)",
                    (observation_id, self.facility_id, record_id, now, now),
                )
                db.execute(
                    "INSERT INTO uec.geocode_results (source_record_id,provider_id,query,match_method,status,attempt_number,result,queried_at) VALUES (%s,'synthetic',%s,'fixture','accepted',2,ST_SetSRID(ST_MakePoint(13,57),4326)::geography,%s)",
                    (record_id, self.private_marker, now),
                )
                db.execute(
                    "INSERT INTO uec.releases (release_id,status,ruleset_version,profile,summary) VALUES ('e2e-suppression-rebuilt','candidate','synthetic-v2','official','{}')"
                )
                db.execute(
                    "INSERT INTO uec.release_members (release_id,facility_id,observation_id,default_visible) VALUES ('e2e-suppression-rebuilt',%s,%s,true)",
                    (self.facility_id, observation_id),
                )
                db.execute(
                    "INSERT INTO uec.publication_review_events (source_record_id,release_id,factual_review_status,privacy_screening_status,maintainer_approval,publication_eligible,reviewer_role) VALUES (%s,'e2e-suppression-rebuilt','reviewed','passed','approved',true,'maintainer')",
                    (record_id,),
                )
                self.assertEqual(
                    db.execute("SELECT count(*) FROM uec.public_access_restricted WHERE source_record_id=%s", (record_id,)).fetchone()[0],
                    1,
                )
                self.assertEqual(
                    db.execute("SELECT count(*) FROM uec.map_facilities_display_history WHERE source_record_id=%s", (record_id,)).fetchone()[0],
                    0,
                )
                self.assertEqual(
                    db.execute("SELECT count(*) FROM uec.geocode_results WHERE source_record_id=%s", (record_id,)).fetchone()[0],
                    1,
                )
        report = VALIDATE.validate(self.env.database_url, "e2e-suppression-rebuilt", 1, False)
        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["metrics"]["active_suppression"], 1)
        with psycopg.connect(self.env.database_url) as db:
            db.execute("UPDATE uec.releases SET status='validated' WHERE release_id='e2e-suppression-rebuilt'")
        with self.assertRaisesRegex(ValueError, "active_suppression=1"):
            PROMOTE.promote(self.env.database_url, "e2e-suppression-rebuilt", [])
        status, body = self.get_json("/api/v2/locations?limit=100")
        self.assertEqual(status, 200)
        self.assertEqual(body["data"], [])

    def test_queued_geocoding_is_not_renewed_after_suppression(self):
        self.suppress()
        job_id = uuid.uuid4()
        with psycopg.connect(self.env.database_url) as db:
            with db.transaction():
                db.execute(
                    "INSERT INTO uec.geocode_jobs (job_id,source_record_id,provider_id,query) VALUES (%s,%s,'synthetic',%s)",
                    (job_id, self.source_record_id, self.private_marker),
                )
                db.execute(
                    "INSERT INTO uec.geocode_job_events (job_id,event_type,attempt_number) VALUES (%s,'queued',1)",
                    (job_id,),
                )
        class Adapter:
            calls = 0

            def geocode(self, query):
                self.calls += 1
                raise AssertionError("suppressed geocode must not be queried")

        adapter = Adapter()
        with patch.object(WORKER, "get_adapter", return_value=adapter):
            self.assertEqual(WORKER.run(self.env.database_url, "synthetic", 1, 0, 1), 0)
        self.assertEqual(adapter.calls, 0)


if __name__ == "__main__":
    unittest.main()
