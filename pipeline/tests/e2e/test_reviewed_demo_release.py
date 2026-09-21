"""Synthetic exercise of the bounded reviewed-demonstration release lane.

This test deliberately uses no Denmark rows. It proves the control sequence
that a future privately staged real Denmark sample must pass.
"""

import hashlib
import importlib.util
import json
import os
import tempfile
import unittest
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

import psycopg

try:
    from .fixture import E2EEnvironment
except ImportError:
    from fixture import E2EEnvironment


ROOT = Path(__file__).parents[2]


def load_stage(name):
    path = ROOT / "scripts" / "stages" / name
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PREPARE = load_stage("prepare-demonstration-release.py")
REVIEW = load_stage("record-demonstration-review.py")
VALIDATE = load_stage("validate-release.py")
PROMOTE = load_stage("promote-release.py")


class ReviewedDemonstrationReleaseE2ETests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.environ.get("UEC_RUN_E2E") != "1":
            raise unittest.SkipTest("set UEC_RUN_E2E=1 to run Docker-backed E2E tests")
        cls.env = E2EEnvironment().start()
        cls.seed()

    @classmethod
    def tearDownClass(cls):
        cls.env.stop()

    @classmethod
    def seed(cls):
        cls.source_id = "e2e.demo"
        cls.record_id, cls.facility_id, cls.observation_id, artifact_id = (uuid.uuid4() for _ in range(4))
        cls.artifact_sha256 = hashlib.sha256(b"synthetic demo artifact").hexdigest()
        now = datetime.now(timezone.utc)
        with psycopg.connect(cls.env.database_url) as db:
            with db.transaction():
                db.execute(
                    "INSERT INTO uec.sources(source_id,country_code,name,official_url,access_method,attribution) VALUES (%s,'DK','Synthetic demo source','https://example.invalid/demo','fixture','synthetic terms fixture')",
                    (cls.source_id,),
                )
                db.execute(
                    "INSERT INTO uec.raw_artifacts(artifact_id,storage_key,sha256,byte_size,media_type,retrieved_at) VALUES (%s,'e2e/demo',%s,22,'application/xml',%s)",
                    (artifact_id, cls.artifact_sha256, now),
                )
                db.execute(
                    "INSERT INTO uec.source_records(source_record_id,source_id,source_record_key,artifact_id,raw_fields,parsed_at) VALUES (%s,%s,'opaque-demo-key',%s,'{}',%s)",
                    (cls.record_id, cls.source_id, artifact_id, now),
                )
                db.execute(
                    "INSERT INTO uec.facilities(facility_id,canonical_name,country_code,city) VALUES (%s,'Synthetic demo facility','DK','Demoby')",
                    (cls.facility_id,),
                )
                db.execute(
                    "INSERT INTO uec.observations(observation_id,facility_id,source_record_id,observed_at,observation,classification,ruleset_id,rule_id,classification_category,classification_review_status,default_visible,coordinate_method,coordinate_precision,coordinate_review_status,first_observed_at) VALUES (%s,%s,%s,%s,'{}','{}','demo-v1','demo','slaughter','approved',true,'fixture','address_point','approved',%s)",
                    (cls.observation_id, cls.facility_id, cls.record_id, now, now),
                )
                db.execute(
                    "INSERT INTO uec.releases(release_id,status,ruleset_version,profile,test_only,summary) VALUES ('e2e-demo-source','candidate','demo-v1','official',true,'{}')"
                )
                db.execute(
                    "INSERT INTO uec.release_members(release_id,facility_id,observation_id,default_visible) VALUES ('e2e-demo-source',%s,%s,true)",
                    (cls.facility_id, cls.observation_id),
                )
                db.execute(
                    "INSERT INTO uec.geocode_results(source_record_id,provider_id,query,match_method,status,result,queried_at) VALUES (%s,'fixture','synthetic','fixture','accepted',ST_SetSRID(ST_MakePoint(10,55),4326)::geography,%s)",
                    (cls.record_id, now),
                )

    @classmethod
    def documents(cls, release_id):
        directory = tempfile.TemporaryDirectory()
        root = Path(directory.name)
        selection = {
            "selection_version": "uec-demo-selection-v1",
            "candidate_release_id": "e2e-demo-source",
            "source_id": cls.source_id,
            "source_artifact_sha256": cls.artifact_sha256,
            "record_ids": [str(cls.record_id)],
            "selection_reason": "synthetic bounded release-lane exercise",
        }
        review = {
            "review_version": "uec-demo-review-v1",
            "release_id": release_id,
            "source_id": cls.source_id,
            "source_artifact_sha256": cls.artifact_sha256,
            "rights_status": "cleared",
            "rights_reference": "synthetic fixture terms decision",
            "reviewer_role": "synthetic authorized maintainer",
            "reviewed_at": "2026-09-17T12:00:00Z",
            "decisions": [{
                "source_record_id": str(cls.record_id),
                "factual_review_status": "reviewed",
                "privacy_screening_status": "passed",
                "maintainer_approval": "approved",
                "publication_eligible": True,
                "note": "synthetic end-to-end decision",
            }],
        }
        selection_path, review_path = root / "selection.json", root / "review.json"
        selection_path.write_text(json.dumps(selection), encoding="utf-8")
        review_path.write_text(json.dumps(review), encoding="utf-8")
        return directory, selection_path, review_path

    def promote_demo(self, release_id):
        directory, selection_path, review_path = self.documents(release_id)
        self.addCleanup(directory.cleanup)
        PREPARE.prepare(self.env.database_url, selection_path, release_id, "official")
        REVIEW.record(self.env.database_url, review_path)
        validation = VALIDATE.validate(self.env.database_url, release_id, 1, True)
        self.assertEqual(validation["status"], "passed")
        result = PROMOTE.promote(self.env.database_url, release_id, [])
        self.env.build_public_read_model(release_id)
        return result

    def get_list(self):
        with urllib.request.urlopen(f"http://localhost:{self.env.api_port}/api/v2/locations?limit=100", timeout=10) as response:
            return response.status, json.loads(response.read())

    def test_review_approval_manifest_exposure_replacement_and_suppression(self):
        first = self.promote_demo("e2e-demo-first")
        self.assertIsNone(first["manifest"]["supersedes"])
        status, body = self.get_list()
        self.assertEqual(status, 200)
        self.assertEqual(len(body["data"]), 1)

        second = self.promote_demo("e2e-demo-second")
        self.assertEqual(second["manifest"]["supersedes"], "e2e-demo-first")
        with psycopg.connect(self.env.database_url) as db:
            db.execute(
                "INSERT INTO uec.record_access_events(source_record_id,action,reason_category,policy_version,maintainer) VALUES (%s,'public_access_revoked','privacy','ethics-v1','synthetic-maintainer')",
                (self.record_id,),
            )
        status, body = self.get_list()
        self.assertEqual(status, 200)
        self.assertEqual(body["data"], [])


if __name__ == "__main__":
    unittest.main()
