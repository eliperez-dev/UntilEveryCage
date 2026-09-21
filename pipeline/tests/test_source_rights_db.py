"""Disposable PostGIS proof for the source-rights ledger and all four gates."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import socket
import subprocess
import tempfile
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path

import psycopg

from pipeline.common import source_rights


REPOSITORY_ROOT = Path(__file__).parents[1].parent
COMPOSE_FILE = REPOSITORY_ROOT / "docker-compose.e2e.yml"


def _load_script(name: str, relative_path: str):
    path = REPOSITORY_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


VALIDATE = _load_script("validate_release_rights_db", "pipeline/scripts/stages/validate-release.py")
PROMOTE = _load_script("promote_release_rights_db", "pipeline/scripts/stages/promote-release.py")
EXPORT = _load_script("export_release_rights_db", "pipeline/scripts/stages/export-release.py")
READ_MODEL = _load_script("read_model_rights_db", "pipeline/scripts/maintenance/build_public_discovery_read_model.py")


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class SourceRightsPostgresTests(unittest.TestCase):
    """Run only with UEC_RUN_RIGHTS_DB=1; all records are synthetic."""

    @classmethod
    def setUpClass(cls):
        if os.environ.get("UEC_RUN_RIGHTS_DB") != "1":
            raise unittest.SkipTest("set UEC_RUN_RIGHTS_DB=1 for disposable PostGIS source-rights proof")
        cls.project = f"uec-rights-{uuid.uuid4().hex[:8]}"
        cls.port = _free_port()
        cls.database_url = f"postgresql://uec:uec-e2e@localhost:{cls.port}/uec"
        cls.compose_env = {**os.environ, "UEC_E2E_DB_PORT": str(cls.port)}
        cls._compose("up", "-d", "--wait", "postgres", check=True)
        for migration in sorted((REPOSITORY_ROOT / "pipeline" / "migrations").glob("*.sql")):
            cls._compose(
                "exec", "-T", "postgres", "psql", "-v", "ON_ERROR_STOP=1", "-U", "uec", "-d", "uec",
                input_text=migration.read_text(encoding="utf-8"),
            )

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "project"):
            cls._compose("down", "-v", "--remove-orphans", check=False)

    @classmethod
    def _compose(cls, *args, input_text=None, check=False):
        command = ["docker", "compose", "-p", cls.project, "-f", str(COMPOSE_FILE), *args]
        result = subprocess.run(
            command,
            cwd=REPOSITORY_ROOT,
            env=cls.compose_env,
            input=input_text,
            text=True,
            capture_output=True,
            timeout=180,
            check=False,
        )
        if check and result.returncode:
            raise RuntimeError(f"Docker Compose failed: {' '.join(command)}\n{result.stdout}\n{result.stderr}")
        return result

    @staticmethod
    def _ids(label: str):
        suffix = uuid.uuid4().hex[:10]
        return f"rights.{label}.{suffix}", f"rights-{label}-{suffix}"

    def seed_release(self, label: str, *, status="candidate", profile="official", second_artifact=False):
        source_id, release_id = self._ids(label)
        artifact_id = uuid.uuid4()
        digest = hashlib.sha256(f"{label}-artifact".encode()).hexdigest()
        now = datetime.now(timezone.utc)
        record_id, facility_id, observation_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        with psycopg.connect(self.database_url) as db, db.transaction():
            db.execute(
                "INSERT INTO uec.sources (source_id,country_code,name,official_url,access_method,attribution) VALUES (%s,'US',%s,'https://example.invalid/rights','fixture','Synthetic attribution')",
                (source_id, f"Synthetic rights {label}"),
            )
            db.execute(
                "INSERT INTO uec.releases (release_id,status,ruleset_version,profile,test_only,summary) VALUES (%s,%s,'rights-v1',%s,false,'{}')",
                (release_id, status, profile),
            )
            db.execute(
                "INSERT INTO uec.raw_artifacts (artifact_id,storage_key,sha256,byte_size,retrieved_at) VALUES (%s,%s,%s,1,%s)",
                (artifact_id, f"synthetic/{label}/{artifact_id}", digest, now),
            )
            db.execute(
                "INSERT INTO uec.source_records (source_record_id,source_id,source_record_key,artifact_id,raw_fields,parsed_at) VALUES (%s,%s,%s,%s,'{}',%s)",
                (record_id, source_id, f"record-{label}", artifact_id, now),
            )
            db.execute(
                "INSERT INTO uec.facilities (facility_id,canonical_name,country_code,city) VALUES (%s,%s,'US','Syntheticville')",
                (facility_id, f"Synthetic facility {label}"),
            )
            db.execute(
                """INSERT INTO uec.observations
                   (observation_id,facility_id,source_record_id,observed_at,observation,
                    classification,ruleset_id,rule_id,classification_category,
                    classification_review_status,default_visible,first_observed_at)
                   VALUES (%s,%s,%s,%s,'{}','{}','rights-v1','rights','slaughter','approved',true,%s)""",
                (observation_id, facility_id, record_id, now, now),
            )
            db.execute(
                "INSERT INTO uec.release_members (release_id,facility_id,observation_id,default_visible) VALUES (%s,%s,%s,true)",
                (release_id, facility_id, observation_id),
            )
            db.execute(
                "INSERT INTO uec.geocode_results (source_record_id,provider_id,query,match_method,status,result,queried_at) VALUES (%s,'synthetic','Syntheticville','fixture','accepted',ST_SetSRID(ST_MakePoint(-100,40),4326)::geography,%s)",
                (record_id, now),
            )
            db.execute(
                "INSERT INTO uec.publication_review_events (source_record_id,release_id,factual_review_status,privacy_screening_status,maintainer_approval,publication_eligible,reviewer_role) VALUES (%s,%s,'reviewed','passed','approved',true,'synthetic')",
                (record_id, release_id),
            )
            if second_artifact:
                second_id = uuid.uuid4()
                second_digest = hashlib.sha256(f"{label}-second".encode()).hexdigest()
                db.execute(
                    "INSERT INTO uec.raw_artifacts (artifact_id,storage_key,sha256,byte_size,retrieved_at) VALUES (%s,%s,%s,1,%s)",
                    (second_id, f"synthetic/{label}/{second_id}", second_digest, now),
                )
                second_record = uuid.uuid4()
                second_observation = uuid.uuid4()
                second_facility = uuid.uuid4()
                db.execute(
                    "INSERT INTO uec.source_records (source_record_id,source_id,source_record_key,artifact_id,raw_fields,parsed_at) VALUES (%s,%s,%s,%s,'{}',%s)",
                    (second_record, source_id, f"record-{label}-second", second_id, now),
                )
                db.execute(
                    "INSERT INTO uec.facilities (facility_id,canonical_name,country_code,city) VALUES (%s,%s,'US','Syntheticville')",
                    (second_facility, f"Synthetic facility {label} second"),
                )
                db.execute(
                    """INSERT INTO uec.observations
                       (observation_id,facility_id,source_record_id,observed_at,observation,
                        classification,ruleset_id,rule_id,classification_category,
                        classification_review_status,default_visible,first_observed_at)
                       VALUES (%s,%s,%s,%s,'{}','{}','rights-v1','rights','slaughter','approved',true,%s)""",
                    (second_observation, second_facility, second_record, now, now),
                )
                db.execute(
                    "INSERT INTO uec.release_members (release_id,facility_id,observation_id,default_visible) VALUES (%s,%s,%s,true)",
                    (release_id, second_facility, second_observation),
                )
        return {
            "source_id": source_id,
            "release_id": release_id,
            "artifact_id": str(artifact_id),
            "digest": digest,
            "now": now,
        }

    def add_decision(self, seeded, status="cleared", *, release_id=None, profile="official", artifact_id=None, digest=None, decided_at=None, decision_id=None):
        with psycopg.connect(self.database_url) as db, db.transaction():
            db.execute(
                """INSERT INTO uec.source_rights_decisions
                   (source_rights_decision_id,source_id,profile,release_id,artifact_id,
                    artifact_sha256,redistribution_status,decision_actor,decision_reference,decided_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,'synthetic-owner','synthetic-rights-case',%s)""",
                (
                    decision_id or uuid.uuid4(), seeded["source_id"], profile,
                    release_id or seeded["release_id"], artifact_id or seeded["artifact_id"],
                    digest or seeded["digest"], status, decided_at or seeded["now"],
                ),
            )

    def test_exact_statuses_and_closed_world_scope(self):
        for status in ("cleared", "unknown", "restricted"):
            seeded = self.seed_release(status)
            if status != "unknown":
                self.add_decision(seeded, status)
            with psycopg.connect(self.database_url) as db:
                result = source_rights.evaluate(db, seeded["release_id"])
            self.assertEqual(result["status"], "cleared" if status == "cleared" else "blocked")
            self.assertEqual(result["requirements"][0]["status"], status if status != "unknown" else "unknown")

    def test_changed_source_version_and_out_of_scope_release_do_not_inherit(self):
        changed = self.seed_release("changed", second_artifact=True)
        self.add_decision(changed, "cleared")
        with psycopg.connect(self.database_url) as db:
            result = source_rights.evaluate(db, changed["release_id"])
        self.assertEqual(len(result["blockers"]), 1)
        self.assertEqual(result["blockers"][0]["reason"], "missing exact decision")

        scoped = self.seed_release("outofscope")
        other = self.seed_release("other-release")
        self.add_decision(scoped, "cleared", release_id=other["release_id"])
        with psycopg.connect(self.database_url) as db:
            result = source_rights.evaluate(db, scoped["release_id"])
        self.assertEqual(result["blockers"][0]["reason"], "missing exact decision")

    def test_latest_conflict_and_digest_profile_trigger_fail_closed(self):
        seeded = self.seed_release("conflict")
        timestamp = seeded["now"]
        self.add_decision(seeded, "cleared", decided_at=timestamp)
        self.add_decision(seeded, "unknown", decided_at=timestamp)
        with psycopg.connect(self.database_url) as db:
            result = source_rights.evaluate(db, seeded["release_id"])
        self.assertEqual(result["blockers"][0]["reason"], "conflicting decisions at the latest decision time")

        mismatch = self.seed_release("digest-mismatch")
        with self.assertRaises(psycopg.errors.RaiseException):
            self.add_decision(mismatch, artifact_id=mismatch["artifact_id"], digest="b" * 64)
        profile_mismatch = self.seed_release("profile-mismatch")
        with self.assertRaises(psycopg.errors.RaiseException):
            self.add_decision(profile_mismatch, profile="secondary")

    def test_all_four_runtime_boundaries_block_unknown_rights(self):
        seeded = self.seed_release("boundaries", status="candidate")
        release_id = seeded["release_id"]
        report = VALIDATE.validate(self.database_url, release_id, None, False)
        self.assertEqual(report["status"], "blocked")
        self.assertGreater(report["metrics"]["rights_not_cleared"], 0)

        with psycopg.connect(self.database_url) as db, db.transaction():
            db.execute("UPDATE uec.releases SET status='validated' WHERE release_id=%s", (release_id,))
        with self.assertRaises(source_rights.SourceRightsBlocked):
            PROMOTE.promote(self.database_url, release_id, [])

        manifest = {"manifest_version": "synthetic-rights-v1", "profile": "official", "release_id": release_id, "ruleset_version": "rights-v1"}
        encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
        with psycopg.connect(self.database_url) as db, db.transaction():
            db.execute("UPDATE uec.releases SET status='promoted' WHERE release_id=%s", (release_id,))
            db.execute(
                "INSERT INTO uec.release_manifests (release_id,manifest,manifest_sha256) VALUES (%s,%s::jsonb,%s)",
                (release_id, encoded, hashlib.sha256(encoded.encode()).hexdigest()),
            )
        with self.assertRaises(source_rights.SourceRightsBlocked):
            READ_MODEL.build(self.database_url, release_id)
        with tempfile.TemporaryDirectory() as output_dir:
            with self.assertRaises(source_rights.SourceRightsBlocked):
                EXPORT.export_release(self.database_url, release_id, "official", Path(output_dir))


if __name__ == "__main__":
    unittest.main()
