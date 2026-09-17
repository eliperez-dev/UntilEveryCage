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
        with self.assertRaisesRegex(RuntimeError, "interrupted"):
            BUILDER.build(self.env.database_url, release_id, fail_after_rows=1)
        with psycopg.connect(self.env.database_url) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM uec.public_discovery_read_models WHERE release_id=%s", (release_id,)).fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT count(*) FROM uec.public_discovery_read_model_rows WHERE release_id=%s", (release_id,)).fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
