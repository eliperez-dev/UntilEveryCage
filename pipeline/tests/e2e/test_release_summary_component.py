"""E2E contracts for the fail-closed release summary component prototype."""

import hashlib
import importlib.util
import json
import os
import sys
import unittest
import uuid
from pathlib import Path

import psycopg

try:
    from .fixture import E2EEnvironment
except ImportError:
    from fixture import E2EEnvironment


ROOT = Path(__file__).parents[2]


def load_script(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem.replace("-", "_"), path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


LOAD = load_script(ROOT / "scripts/benchmarks/run_api_load_rehearsal.py")
BUILD = load_script(ROOT / "scripts/maintenance/build_release_summary_component.py")


class ReleaseSummaryComponentE2ETests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.environ.get("UEC_RUN_E2E") != "1":
            raise unittest.SkipTest("set UEC_RUN_E2E=1 to run Docker-backed E2E tests")
        cls.env = E2EEnvironment().start()
        with psycopg.connect(cls.env.database_url) as db:
            cls.detail_id = LOAD.seed_public_projection(db, 3)
        cls.built = BUILD.build(cls.env.database_url, "load-promoted")

    @classmethod
    def tearDownClass(cls):
        cls.env.stop()

    @staticmethod
    def manifest(release_id: str, profile: str) -> tuple[str, str]:
        value = {
            "manifest_version": "component-test-v1",
            "profile": profile,
            "release_id": release_id,
        }
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"))
        return encoded, hashlib.sha256(encoded.encode()).hexdigest()

    @classmethod
    def create_release(cls, release_id: str, profile: str, with_members: bool = False):
        encoded, digest = cls.manifest(release_id, profile)
        with psycopg.connect(cls.env.database_url) as db:
            with db.transaction():
                db.execute(
                    "INSERT INTO uec.releases (release_id,status,ruleset_version,profile,test_only,summary) VALUES (%s,'promoted','component-v1',%s,false,'{}')",
                    (release_id, profile),
                )
                db.execute(
                    "INSERT INTO uec.release_manifests (release_id,manifest,manifest_sha256) VALUES (%s,%s::jsonb,%s)",
                    (release_id, encoded, digest),
                )
                if with_members:
                    db.execute(
                        "INSERT INTO uec.release_members (release_id,facility_id,observation_id,default_visible) SELECT %s,facility_id,observation_id,default_visible FROM uec.release_members WHERE release_id='load-promoted'",
                        (release_id,),
                    )

    def test_build_is_atomic_deterministic_and_idempotent(self):
        self.assertEqual(self.built["status"], "built")
        again = BUILD.build(self.env.database_url, "load-promoted")
        self.assertEqual(again["status"], "idempotent")
        self.assertEqual(again["content_sha256"], self.built["content_sha256"])
        with psycopg.connect(self.env.database_url) as db:
            self.assertEqual(db.execute("SELECT member_count FROM uec.release_summary_components WHERE release_id='load-promoted'").fetchone()[0], 3)
            self.assertEqual(db.execute("SELECT count(*) FROM uec.release_summary_component_rows WHERE release_id='load-promoted'").fetchone()[0], 3)
            self.assertEqual(db.execute("SELECT count(*) FROM uec.public_facility_observation_summary_component_candidate WHERE release_id='load-promoted'").fetchone()[0], 3)

    def test_interrupted_build_exposes_no_partial_rows_then_recovers(self):
        release_id = "component-interrupted"
        self.create_release(release_id, "community", with_members=True)
        with self.assertRaisesRegex(RuntimeError, "interrupted"):
            BUILD.build(self.env.database_url, release_id, fail_after_rows=1)
        with psycopg.connect(self.env.database_url) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM uec.release_summary_components WHERE release_id=%s", (release_id,)).fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT count(*) FROM uec.release_summary_component_rows WHERE release_id=%s", (release_id,)).fetchone()[0], 0)
        recovered = BUILD.build(self.env.database_url, release_id)
        self.assertEqual(recovered["status"], "built")

    def test_manifest_mismatch_and_missing_current_component_fail_closed(self):
        release_id = "component-mismatch"
        self.create_release(release_id, "secondary")
        with psycopg.connect(self.env.database_url) as db:
            db.execute(
                "INSERT INTO uec.release_summary_components (release_id,manifest_sha256,content_sha256,member_count) VALUES (%s,%s,%s,0)",
                (release_id, "f" * 64, "e" * 64),
            )
        with self.assertRaisesRegex(BUILD.ComponentBlocked, "does not match"):
            BUILD.build(self.env.database_url, release_id)
        with psycopg.connect(self.env.database_url) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM uec.public_facility_observation_summary_component_candidate WHERE release_id='component-missing'").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT count(*) FROM uec.public_facility_observation_summary_component_candidate WHERE release_id=%s", (release_id,)).fetchone()[0], 0)

    def test_current_suppression_is_still_enforced_by_candidate_summary(self):
        with psycopg.connect(self.env.database_url) as db:
            before = db.execute("SELECT count(*) FROM uec.public_facility_observation_summary_component_candidate WHERE release_id='load-promoted'").fetchone()[0]
            case_id = uuid.uuid4()
            facility_id = db.execute("SELECT facility_id FROM uec.release_summary_component_rows WHERE release_id='load-promoted' ORDER BY facility_id LIMIT 1").fetchone()[0]
            db.execute(
                "INSERT INTO uec.suppression_cases (case_id,reason_category,status,policy_version,actor,decision) VALUES (%s,'privacy','active','component-test','test','revoke')",
                (case_id,),
            )
            db.execute(
                "INSERT INTO uec.suppression_references (case_id,facility_id,scope) VALUES (%s,%s,'whole_record')",
                (case_id, facility_id),
            )
            after = db.execute("SELECT count(*) FROM uec.public_facility_observation_summary_component_candidate WHERE release_id='load-promoted'").fetchone()[0]
        self.assertEqual(before, 3)
        self.assertEqual(after, 2)


if __name__ == "__main__":
    unittest.main()
