"""E2E contracts for atomic activation and fail-closed public reads."""

import hashlib
import importlib.util
import json
import os
import unittest
import urllib.error
import urllib.request
from pathlib import Path

import psycopg

try:
    from .fixture import E2EEnvironment
except ImportError:
    from fixture import E2EEnvironment


ROOT = Path(__file__).parents[2]
SPEC = importlib.util.spec_from_file_location(
    "build_public_discovery_read_model",
    ROOT / "scripts" / "maintenance" / "build_public_discovery_read_model.py",
)
BUILDER = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(BUILDER)

PROMOTE_SPEC = importlib.util.spec_from_file_location(
    "promote_release",
    ROOT / "scripts" / "stages" / "promote-release.py",
)
PROMOTER = importlib.util.module_from_spec(PROMOTE_SPEC)
assert PROMOTE_SPEC.loader
PROMOTE_SPEC.loader.exec_module(PROMOTER)


class PublicDiscoveryReadModelE2ETests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.environ.get("UEC_RUN_E2E") != "1":
            raise unittest.SkipTest("set UEC_RUN_E2E=1 to run Docker-backed E2E tests")
        cls.env = E2EEnvironment().start()
        cls.env.seed_official_scenario()

    @classmethod
    def tearDownClass(cls):
        cls.env.stop()

    def get_public(self):
        request = urllib.request.Request(
            f"http://localhost:{self.env.api_port}/api/v2/locations?profile=official&limit=100",
            headers={"Accept": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read())

    def create_release_without_model(self, release_id, profile="secondary"):
        manifest = {
            "eligible_record_count": 0,
            "manifest_version": "read-model-e2e-v1",
            "profile": profile,
            "release_id": release_id,
            "ruleset_version": "read-model-e2e-v1",
        }
        serialized = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
        with psycopg.connect(self.env.database_url) as db:
            with db.transaction():
                db.execute(
                    "INSERT INTO uec.releases (release_id,status,ruleset_version,profile,summary) VALUES (%s,'promoted','read-model-e2e-v1',%s,'{}')",
                    (release_id, profile),
                )
                db.execute(
                    "INSERT INTO uec.release_manifests (release_id,manifest,manifest_sha256) VALUES (%s,%s::jsonb,%s)",
                    (release_id, serialized, hashlib.sha256(serialized.encode()).hexdigest()),
                )

    def create_validated_copy(self, release_id):
        with psycopg.connect(self.env.database_url) as db:
            with db.transaction():
                db.execute(
                    "INSERT INTO uec.releases (release_id,status,ruleset_version,profile,test_only,summary) VALUES (%s,'validated','e2e-v1','official',false,'{}')",
                    (release_id,),
                )
                db.execute(
                    """INSERT INTO uec.release_members (release_id,facility_id,observation_id,default_visible)
                       SELECT %s,member.facility_id,member.observation_id,member.default_visible
                       FROM uec.release_members member
                       JOIN uec.observations observation USING (observation_id)
                       JOIN uec.publication_review_release_current review
                         ON review.source_record_id=observation.source_record_id
                        AND review.release_id=member.release_id
                       WHERE member.release_id='e2e-promoted'
                         AND review.publication_eligible=true
                         AND review.privacy_screening_status='passed'
                         AND review.maintainer_approval='approved'
                         AND NOT EXISTS (SELECT 1 FROM uec.public_access_restricted restricted
                                         WHERE restricted.source_record_id=observation.source_record_id)""",
                    (release_id,),
                )
                db.execute(
                    """INSERT INTO uec.publication_review_events
                       (source_record_id,release_id,factual_review_status,privacy_screening_status,
                        maintainer_approval,publication_eligible,reviewer_role,reviewed_at)
                       SELECT source_record_id,%s,factual_review_status,privacy_screening_status,
                              maintainer_approval,publication_eligible,reviewer_role,reviewed_at
                       FROM uec.publication_review_release_current WHERE release_id='e2e-promoted'""",
                    (release_id,),
                )
        self.env._seed_synthetic_rights_decisions(release_id)

    def promote(self, release_id, fail_after_read_model_rows=None, artifacts=None):
        return PROMOTER.promote(
            self.env.database_url,
            release_id,
            artifacts or [],
            _fail_after_read_model_rows=fail_after_read_model_rows,
        )

    def test_api_uses_activated_model_and_missing_latest_model_fails_closed(self):
        status, body = self.get_public()
        self.assertEqual(status, 200)
        self.assertEqual(len(body["data"]), 3)
        self.create_release_without_model("e2e-read-model-missing")
        with self.assertRaises(urllib.error.HTTPError) as error:
            request = urllib.request.Request(
                f"http://localhost:{self.env.api_port}/api/v2/locations?profile=secondary&limit=100",
                headers={"Accept": "application/json"},
            )
            urllib.request.urlopen(request, timeout=10)
        self.assertEqual(error.exception.code, 503)
        self.assertEqual(json.loads(error.exception.read())["error"]["code"], "read_model_unavailable")

    def test_interrupted_activation_leaves_no_rows_or_metadata(self):
        release_id = "e2e-read-model-interrupted"
        self.create_release_without_model(release_id, profile="community")
        with psycopg.connect(self.env.database_url) as db:
            with db.transaction():
                db.execute(
                    "INSERT INTO uec.release_members (release_id,facility_id,observation_id,default_visible) SELECT %s,facility_id,observation_id,default_visible FROM uec.release_members WHERE release_id='e2e-promoted'",
                    (release_id,),
                )
                db.execute(
                    """INSERT INTO uec.publication_review_events
                       (source_record_id,release_id,factual_review_status,privacy_screening_status,
                        maintainer_approval,publication_eligible,reviewer_role,reviewed_at)
                       SELECT source_record_id,%s,factual_review_status,privacy_screening_status,
                              maintainer_approval,publication_eligible,reviewer_role,reviewed_at
                       FROM uec.publication_review_release_current
                       WHERE release_id='e2e-promoted'""",
                    (release_id,),
                )
        self.env._seed_synthetic_rights_decisions(release_id)
        with self.assertRaisesRegex(RuntimeError, "interrupted"):
            BUILDER.build(self.env.database_url, release_id, fail_after_rows=1)
        with psycopg.connect(self.env.database_url) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM uec.public_discovery_read_models WHERE release_id=%s", (release_id,)).fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT count(*) FROM uec.public_discovery_read_model_rows WHERE release_id=%s", (release_id,)).fetchone()[0], 0)

    def test_failed_replacement_activation_preserves_the_previous_release(self):
        release_id = "e2e-atomic-replacement"
        self.create_validated_copy(release_id)

        with self.assertRaisesRegex(RuntimeError, "interrupted"):
            self.promote(release_id, fail_after_read_model_rows=1)
        with psycopg.connect(self.env.database_url) as db:
            self.assertEqual(db.execute("SELECT status FROM uec.releases WHERE release_id='e2e-promoted'").fetchone()[0], "promoted")
            self.assertEqual(db.execute("SELECT status FROM uec.releases WHERE release_id=%s", (release_id,)).fetchone()[0], "validated")
            self.assertEqual(db.execute("SELECT count(*) FROM uec.public_discovery_read_models WHERE release_id=%s", (release_id,)).fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT count(*) FROM uec.release_manifests WHERE release_id=%s", (release_id,)).fetchone()[0], 0)
        status, body = self.get_public()
        self.assertEqual(status, 200)
        self.assertEqual(body["meta"]["release_id"], "e2e-promoted")

    def test_repromotion_reuses_immutable_manifest_for_a_b_a(self):
        release_a, release_b = "e2e-activation-a", "e2e-activation-b"
        self.create_validated_copy(release_a)
        self.create_validated_copy(release_b)
        first_a = self.promote(release_a)
        self.promote(release_b)
        with psycopg.connect(self.env.database_url) as db:
            manifest_before = db.execute(
                "SELECT manifest::text,manifest_sha256 FROM uec.release_manifests WHERE release_id=%s",
                (release_a,),
            ).fetchone()
        second_a = self.promote(release_a)
        with psycopg.connect(self.env.database_url) as db:
            manifest_after = db.execute(
                "SELECT manifest::text,manifest_sha256 FROM uec.release_manifests WHERE release_id=%s",
                (release_a,),
            ).fetchone()
            self.assertEqual(db.execute("SELECT status FROM uec.releases WHERE release_id=%s", (release_a,)).fetchone()[0], "promoted")
            self.assertEqual(db.execute("SELECT status FROM uec.releases WHERE release_id=%s", (release_b,)).fetchone()[0], "validated")
        self.assertEqual(manifest_after, manifest_before)
        self.assertEqual(second_a["manifest_sha256"], first_a["manifest_sha256"])
        self.assertEqual(second_a["read_model"]["status"], "idempotent")

    def test_repromotion_rejects_changed_artifacts_and_stale_suppression(self):
        release_a, release_b = "e2e-activation-stale-a", "e2e-activation-stale-b"
        self.create_validated_copy(release_a)
        self.create_validated_copy(release_b)
        self.promote(release_a)
        self.promote(release_b)
        changed = [{"name": "changed.csv", "sha256": "0" * 64, "byte_size": 1}]
        with self.assertRaisesRegex(ValueError, "immutable manifest does not match"):
            self.promote(release_a, artifacts=changed)
        with psycopg.connect(self.env.database_url) as db:
            with db.transaction():
                db.execute("UPDATE uec.public_suppression_generation SET generation=generation+1")
        with self.assertRaisesRegex(ValueError, "immutable manifest does not match"):
            self.promote(release_a)
        with psycopg.connect(self.env.database_url) as db:
            self.assertEqual(db.execute("SELECT status FROM uec.releases WHERE release_id=%s", (release_b,)).fetchone()[0], "promoted")
            self.assertEqual(db.execute("SELECT status FROM uec.releases WHERE release_id=%s", (release_a,)).fetchone()[0], "validated")


if __name__ == "__main__":
    unittest.main()
