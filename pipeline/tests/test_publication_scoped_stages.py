"""Rollback-only synthetic database checks for release-scoped stage gates."""

import importlib.util
import hashlib
import os
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import psycopg


ROOT = Path(__file__).parents[1]
DATABASE_URL = os.environ.get("UEC_DATABASE_URL", "postgresql://uec:uec-local-development-only@localhost:5433/uec")


def load_stage(name):
    path = ROOT / "scripts" / "stages" / name
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


VALIDATE = load_stage("validate-release.py")
PROMOTE = load_stage("promote-release.py")


class BorrowedConnection:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self.connection

    def __exit__(self, *_):
        return False


class ScopedStageDatabaseTests(unittest.TestCase):
    def test_legacy_ambiguity_and_explicit_scope(self):
        try:
            db = psycopg.connect(DATABASE_URL, connect_timeout=2)
        except psycopg.Error as error:
            self.skipTest(f"PostGIS is unavailable: {error}")
        try:
            prefix = f"test.stage.{uuid.uuid4().hex}"
            release_a, release_b = prefix + ".a", prefix + ".b"
            db.execute("INSERT INTO uec.sources (source_id,country_code,name,official_url,access_method) VALUES (%s,'DK','Synthetic','https://example.invalid','test')", (prefix,))
            artifact_id, record_id, facility_id, observation_id = (uuid.uuid4() for _ in range(4))
            db.execute("INSERT INTO uec.raw_artifacts (artifact_id,storage_key,sha256,byte_size,retrieved_at) VALUES (%s,%s,%s,1,now())", (artifact_id, prefix, uuid.uuid4().hex * 2))
            db.execute("INSERT INTO uec.source_records (source_record_id,source_id,source_record_key,artifact_id,raw_fields,parsed_at) VALUES (%s,%s,'synthetic',%s,'{}',now())", (record_id, prefix, artifact_id))
            db.execute("INSERT INTO uec.facilities (facility_id,canonical_name,country_code) VALUES (%s,'Synthetic facility','DK')", (facility_id,))
            db.execute("INSERT INTO uec.observations (observation_id,facility_id,source_record_id,observed_at,observation,classification,ruleset_id,rule_id,classification_category,classification_review_status,default_visible,first_observed_at) VALUES (%s,%s,%s,now(),'{}','{}','test','test','synthetic','approved',true,now())", (observation_id, facility_id, record_id))
            for release_id in (release_a, release_b):
                db.execute("INSERT INTO uec.releases (release_id,status,ruleset_version,profile,summary) VALUES (%s,'candidate','synthetic-v1','secondary','{}')", (release_id,))
                db.execute("INSERT INTO uec.release_members (release_id,facility_id,observation_id,default_visible) VALUES (%s,%s,%s,true)", (release_id, facility_id, observation_id))
            db.execute("INSERT INTO uec.geocode_results (source_record_id,provider_id,query,match_method,status,result,queried_at) VALUES (%s,'synthetic','synthetic','test','accepted',ST_SetSRID(ST_MakePoint(10,55),4326)::geography,now())", (record_id,))
            has_scope = db.execute("SELECT to_regclass('uec.publication_review_release_scopes')").fetchone()[0] is not None
            if not has_scope:
                db.execute("INSERT INTO uec.publication_review_events (source_record_id,factual_review_status,privacy_screening_status,maintainer_approval,publication_eligible,reviewer_role) VALUES (%s,'reviewed','passed','approved',true,'synthetic-maintainer')", (record_id,))
                db.execute((ROOT / "migrations" / "022_publication_safety_scopes.sql").read_text(encoding="utf-8"))
            with patch.object(VALIDATE.psycopg, "connect", return_value=BorrowedConnection(db)):
                before = VALIDATE.validate(DATABASE_URL, release_b, 1, False)
                self.assertEqual(before["metrics"]["publication_not_approved"], 1)
                self.assertEqual(before["status"], "blocked")
                self.assertFalse(before["marked_validated"])
            db.execute("INSERT INTO uec.publication_review_events (source_record_id,release_id,factual_review_status,privacy_screening_status,maintainer_approval,publication_eligible,reviewer_role) VALUES (%s,%s,'reviewed','passed','approved',true,'synthetic-maintainer')", (record_id, release_a))
            with patch.object(VALIDATE.psycopg, "connect", return_value=BorrowedConnection(db)):
                scoped = VALIDATE.validate(DATABASE_URL, release_a, 1, False)
                other = VALIDATE.validate(DATABASE_URL, release_b, 1, False)
                self.assertEqual(scoped["metrics"]["publication_not_approved"], 0)
                self.assertEqual(other["metrics"]["publication_not_approved"], 1)
            db.execute("UPDATE uec.releases SET status='validated' WHERE release_id IN (%s,%s)", (release_a, release_b))
            with patch.object(PROMOTE.psycopg, "connect", return_value=BorrowedConnection(db)):
                with self.assertRaisesRegex(ValueError, "publication_not_approved=1"):
                    PROMOTE.promote(DATABASE_URL, release_b, [])
                result = PROMOTE.promote(DATABASE_URL, release_a, [])
            stored = db.execute("SELECT manifest,manifest_sha256 FROM uec.release_manifests WHERE release_id=%s", (release_a,)).fetchone()
            self.assertEqual(stored[0], result["manifest"])
            self.assertEqual(stored[1], result["manifest_sha256"])
            self.assertEqual(stored[1], hashlib.sha256(PROMOTE.canonical_json(stored[0]).encode("utf-8")).hexdigest())
            self.assertIn("created_at", stored[0])
            self.assertEqual(stored[0]["distributed_artifacts"], [])
            self.assertEqual(db.execute("SELECT count(*) FROM uec.publication_release_eligible_observations WHERE release_id=%s AND source_record_id=%s", (release_a, record_id)).fetchone()[0], 1)

            # A newer B decision must neither relabel A nor make B inherit A's approval.
            db.execute("INSERT INTO uec.publication_review_events (source_record_id,release_id,factual_review_status,privacy_screening_status,maintainer_approval,publication_eligible,reviewer_role,reviewed_at) VALUES (%s,%s,'reviewed','passed','denied',false,'synthetic-maintainer',now() + interval '1 second')", (record_id, release_b))
            with patch.object(VALIDATE.psycopg, "connect", return_value=BorrowedConnection(db)):
                denied = VALIDATE.validate(DATABASE_URL, release_b, 1, False)
                self.assertEqual(denied["metrics"]["publication_not_approved"], 1)
            with patch.object(PROMOTE.psycopg, "connect", return_value=BorrowedConnection(db)):
                with self.assertRaisesRegex(ValueError, "publication_not_approved=1"):
                    PROMOTE.promote(DATABASE_URL, release_b, [])
            self.assertEqual(db.execute("SELECT count(*) FROM uec.publication_release_eligible_observations WHERE release_id=%s AND source_record_id=%s", (release_a, record_id)).fetchone()[0], 1)

            db.execute("INSERT INTO uec.publication_review_events (source_record_id,release_id,factual_review_status,privacy_screening_status,maintainer_approval,publication_eligible,reviewer_role,reviewed_at) VALUES (%s,%s,'reviewed','passed','approved',true,'synthetic-maintainer',now() + interval '2 seconds')", (record_id, release_b))
            source_keyed_event = db.execute("SELECT publication_review_event_id FROM uec.publication_review_current WHERE source_record_id=%s", (record_id,)).fetchone()[0]
            b_event = db.execute("SELECT publication_review_event_id FROM uec.publication_review_release_current WHERE source_record_id=%s AND release_id=%s", (record_id, release_b)).fetchone()[0]
            self.assertNotEqual(source_keyed_event, b_event)
            with patch.object(VALIDATE.psycopg, "connect", return_value=BorrowedConnection(db)):
                approved_b = VALIDATE.validate(DATABASE_URL, release_b, 1, False)
                self.assertEqual(approved_b["metrics"]["publication_not_approved"], 0)
                self.assertEqual(approved_b["status"], "passed")
            self.assertEqual(db.execute("SELECT count(*) FROM uec.publication_release_eligible_observations WHERE release_id=%s AND source_record_id=%s", (release_a, record_id)).fetchone()[0], 1)

            db.execute("INSERT INTO uec.record_access_events (source_record_id,action,reason_category,policy_version,maintainer) VALUES (%s,'public_access_revoked','privacy','ethics-v1','synthetic-maintainer')", (record_id,))
            with patch.object(VALIDATE.psycopg, "connect", return_value=BorrowedConnection(db)):
                restricted = VALIDATE.validate(DATABASE_URL, release_b, 1, False)
                self.assertEqual(restricted["metrics"]["active_suppression"], 1)
            with patch.object(PROMOTE.psycopg, "connect", return_value=BorrowedConnection(db)):
                with self.assertRaisesRegex(ValueError, "active_suppression=1"):
                    PROMOTE.promote(DATABASE_URL, release_b, [])
            db.execute("INSERT INTO uec.record_access_events (source_record_id,action,reason_category,policy_version,maintainer,occurred_at) VALUES (%s,'public_access_restored','privacy','ethics-v1','synthetic-maintainer',now() + interval '1 second')", (record_id,))
            with patch.object(PROMOTE.psycopg, "connect", return_value=BorrowedConnection(db)):
                promoted_b = PROMOTE.promote(DATABASE_URL, release_b, [])
                self.assertEqual(promoted_b["status"], "promoted")
            self.assertEqual(db.execute("SELECT count(*) FROM uec.publication_review_events WHERE source_record_id=%s", (record_id,)).fetchone()[0],
                             4 if not has_scope else 3)
        finally:
            db.rollback()
            db.close()


if __name__ == "__main__":
    unittest.main()
