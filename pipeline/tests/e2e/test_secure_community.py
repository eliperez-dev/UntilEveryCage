"""Opt-in ciphertext-relay acceptance on the assigned disposable v0 copy.

Opaque framing fixtures test the relay, not cryptography. The frontend's real
OpenPGP browser acceptance separately tests encryption/signatures/recovery.
No source, release, frozen-reference, or production rows are changed.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import time
import unittest
import urllib.error
import urllib.request
import uuid
from urllib.parse import urlsplit

import psycopg
from psycopg import sql

from pipeline.scripts.release_baseline import load_contract, verify_connection, _migration_checksums

ROOT = Path(__file__).resolve().parents[3]
MIGRATION = ROOT / "pipeline/migrations/099_community_encrypted_inbox.sql"
DATABASE = "uec_launch_sources_test_20261025"
PUBLIC_KEY = "-----BEGIN PGP PUBLIC KEY BLOCK-----\nsynthetic-relay-framing-only\n-----END PGP PUBLIC KEY BLOCK-----\n"
CIPHERTEXT = "-----BEGIN PGP MESSAGE-----\nsynthetic-relay-framing-only-00000000\n-----END PGP MESSAGE-----\n"


def checked_connection(dsn):
    parsed = urlsplit(dsn)
    if parsed.hostname != "127.0.0.1" or parsed.port != 55433 or parsed.path != "/" + DATABASE or parsed.query:
        raise RuntimeError("secure proof requires the assigned loopback disposable v0 copy")
    db = psycopg.connect(dsn, autocommit=True)
    if db.execute("SELECT current_database()").fetchone()[0] != DATABASE:
        db.close()
        raise RuntimeError("incorrect disposable database")
    return db


def prepare(dsn):
    contract = load_contract(ROOT / "pipeline/contracts/development-baseline.json")
    with checked_connection(dsn) as db:
        exists = db.execute("SELECT 1 FROM uec.schema_migrations WHERE version=%s", (MIGRATION.stem,)).fetchone()
        inventory = _migration_checksums()
        if not exists:
            del inventory[MIGRATION.stem]
        verify_connection(db, contract, inventory)
        if not exists:
            with db.transaction(force_rollback=True):
                db.execute(MIGRATION.read_text(encoding="utf-8"))
                db.execute("INSERT INTO uec.schema_migrations(version,sha256) VALUES(%s,%s)",
                           (MIGRATION.stem, hashlib.sha256(MIGRATION.read_bytes()).hexdigest()))
                verify_connection(db, contract)
            if db.execute("SELECT to_regclass('uec.community_secure_inboxes')").fetchone()[0] is not None:
                raise RuntimeError("migration rollback did not restore schema")
            with db.transaction():
                db.execute(MIGRATION.read_text(encoding="utf-8"))
                db.execute("INSERT INTO uec.schema_migrations(version,sha256) VALUES(%s,%s)",
                           (MIGRATION.stem, hashlib.sha256(MIGRATION.read_bytes()).hexdigest()))
        result = verify_connection(db, contract)
        if result["status"] != "verified":
            raise RuntimeError("v0 baseline verification failed")


class LocalApi:
    def __init__(self, dsn, public_key=PUBLIC_KEY, fingerprint="b" * 40, token=None, daily_limit=1000):
        self.token = token or secrets.token_hex(32)
        binary = Path(os.environ.get("UEC_SECURE_TEST_BINARY", ROOT / "target/debug/uec-api.exe"))
        if not binary.is_file():
            raise RuntimeError("build the owned backend binary before testing")
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        self.origin = f"http://127.0.0.1:{port}"
        env = {k: v for k, v in os.environ.items() if not k.startswith("UEC_")}
        env.update({
            "UEC_DATABASE_URL": dsn, "PORT": str(port),
            "UEC_BIND_HOST": "127.0.0.1", "UEC_RUNTIME_MODE": "development",
            "UEC_CORS_ORIGINS": "http://127.0.0.1:4186,http://localhost:4186,http://127.0.0.1:4190",
            "UEC_COMMUNITY_ENABLED": "true", "UEC_COMMUNITY_PUBLIC_ENABLED": "false",
            "UEC_COMMUNITY_OPERATOR_TOKEN": self.token,
            "UEC_COMMUNITY_RETENTION_DAYS": "30", "UEC_COMMUNITY_CONTACT_RETENTION_DAYS": "7",
            "UEC_COMMUNITY_RECEIPT_DAYS": "14", "UEC_COMMUNITY_DAILY_INTAKE_CAP": str(daily_limit),
            "UEC_COMMUNITY_PENDING_CAP": "1000", "UEC_COMMUNITY_SECURE_ENABLED": "true",
            "UEC_COMMUNITY_SECURE_REVIEWER_PUBLIC_KEY": public_key,
            "UEC_COMMUNITY_SECURE_REVIEWER_FINGERPRINT": fingerprint,
        })
        self.process = subprocess.Popen([str(binary.resolve())], cwd=ROOT, env=env,
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            for _ in range(100):
                try:
                    with urllib.request.urlopen(self.origin + "/health/live", timeout=1):
                        return
                except (OSError, urllib.error.URLError):
                    if self.process.poll() is not None:
                        raise RuntimeError("owned secure API failed startup") from None
                    time.sleep(.1)
            raise RuntimeError("owned secure API readiness timed out")
        except BaseException:
            self.stop()
            raise

    def stop(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)


@unittest.skipUnless(os.environ.get("UEC_SECURE_TEST_DATABASE_URL"), "assigned disposable v0 URL required")
class SecureRelayAcceptance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dsn = os.environ["UEC_SECURE_TEST_DATABASE_URL"]
        prepare(cls.dsn)

    def setUp(self):
        self.ids = []
        self.legacy_ids = []
        self.api = LocalApi(self.dsn)
        self.addCleanup(self.api.stop)

    def tearDown(self):
        with checked_connection(self.dsn) as db:
            for identifier in self.ids:
                db.execute("DELETE FROM uec.community_secure_inboxes WHERE case_id=%s", (identifier,))
            for identifier in self.legacy_ids:
                self.request(f"/api/private/community/submissions/{identifier}/disposition",
                             {"action": "remove", "reason_code": "removed_by_request"}, operator=True)

    def request(self, path, body=None, operator=False, raw=None):
        headers = {"Content-Type": "application/json"}
        if operator:
            headers["Authorization"] = "Bearer " + self.api.token
        data = raw if raw is not None else json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(self.api.origin + path, data=data, headers=headers)
        try:
            response = urllib.request.urlopen(request, timeout=12)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            self.assertEqual(response.headers.get("Referrer-Policy"), "no-referrer")
            self.assertTrue(response.headers.get("Cache-Control", "").startswith("no-store"))
            payload = response.read()
            return response.code, json.loads(payload) if payload else None

    def submission(self, kind="facility"):
        case_id = str(uuid.uuid4())
        self.ids.append(case_id)
        return {"case_id": case_id, "initial_message_id": str(uuid.uuid4()), "kind": kind,
                "protocol": "uec-openpgp-inbox-v1", "access_secret": secrets.token_hex(32),
                "contributor_public_key": PUBLIC_KEY, "contributor_fingerprint": "a" * 40,
                "reviewer_fingerprint": "b" * 40, "ciphertext": CIPHERTEXT}

    def test_all_kinds_ciphertext_only_isolated_and_idempotent(self):
        for kind in ("facility", "evidence", "correction", "duplicate", "privacy_removal", "bug"):
            with self.subTest(kind=kind):
                claim = self.submission(kind)
                self.assertEqual(self.request("/api/community/secure/submissions", claim)[0], 201)
                self.assertEqual(self.request("/api/community/secure/submissions", claim)[0], 200)
                self.assertEqual(self.request("/api/community/secure/submissions", {**claim, "ciphertext": CIPHERTEXT.replace("0000", "1111")})[0], 409)
                auth = {k: claim[k] for k in ("case_id", "access_secret")}
                status, inbox = self.request("/api/community/secure/inbox", auth)
                self.assertEqual(status, 200)
                self.assertEqual(len(inbox["messages"]), 1)
                self.assertEqual(inbox["messages"][0]["ciphertext"], CIPHERTEXT)
                self.assertNotIn("access_secret", inbox)
                self.assertEqual(self.request("/api/community/secure/inbox", {**auth, "access_secret": "c" * 64})[0], 404)
                with checked_connection(self.dsn) as db:
                    row = db.execute("SELECT access_secret_sha256 FROM uec.community_secure_inboxes WHERE case_id=%s", (claim["case_id"],)).fetchone()
                    self.assertEqual(row[0], hashlib.sha256(claim["access_secret"].encode()).hexdigest())
                self.assertEqual(self.request("/api/private/community/secure/inbox", {"case_id": claim["case_id"]})[0], 404)
                self.assertEqual(self.request("/api/private/community/secure/inbox", {"case_id": claim["case_id"]}, operator=True)[0], 200)

    def test_replies_status_removal_and_bounded_history(self):
        claim = self.submission()
        self.assertEqual(self.request("/api/community/secure/submissions", claim)[0], 201)
        reviewer = {"case_id": claim["case_id"], "message_id": str(uuid.uuid4()),
                    "reviewer_fingerprint": "b" * 40, "ciphertext": CIPHERTEXT}
        self.assertEqual(self.request("/api/private/community/secure/messages", reviewer)[0], 404)
        self.assertEqual(self.request("/api/private/community/secure/messages", reviewer, operator=True)[0], 201)
        self.assertEqual(self.request("/api/private/community/secure/messages", reviewer, operator=True)[0], 200)
        contributor = {"case_id": claim["case_id"], "access_secret": claim["access_secret"],
                       "message_id": str(uuid.uuid4()), "ciphertext": CIPHERTEXT}
        self.assertEqual(self.request("/api/community/secure/messages", contributor)[0], 201)
        self.assertEqual(self.request("/api/community/secure/messages", contributor)[0], 200)
        self.assertEqual(self.request("/api/community/secure/messages", {**contributor, "message_id": reviewer["message_id"]})[0], 409)
        for _ in range(29):
            self.assertEqual(self.request("/api/community/secure/messages", {**contributor, "message_id": str(uuid.uuid4())})[0], 201)
        self.assertEqual(self.request("/api/community/secure/messages", {**contributor, "message_id": str(uuid.uuid4())})[0], 429)
        auth = {k: claim[k] for k in ("case_id", "access_secret")}
        self.assertEqual(len(self.request("/api/community/secure/inbox", auth)[1]["messages"]), 32)
        disposition = {"case_id": claim["case_id"], "status": "in_review"}
        self.assertEqual(self.request("/api/private/community/secure/disposition", disposition, operator=True)[0], 200)
        self.assertEqual(self.request("/api/community/secure/submissions", claim)[1]["status"], "in_review")
        self.assertEqual(self.request("/api/private/community/secure/disposition", {**disposition, "status": "closed"}, operator=True)[0], 200)
        self.assertEqual(self.request("/api/community/secure/inbox", auth)[0], 200)
        self.assertEqual(self.request("/api/community/secure/messages", {**contributor, "message_id": str(uuid.uuid4())})[0], 404)
        self.assertEqual(self.request("/api/private/community/secure/disposition", {**disposition, "status": "removed"}, operator=True)[0], 200)
        self.assertEqual(self.request("/api/community/secure/inbox", auth)[0], 404)
        self.assertEqual(self.request("/api/private/community/secure/disposition", disposition, operator=True)[0], 404)
        with checked_connection(self.dsn) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM uec.community_secure_messages WHERE case_id=%s", (claim["case_id"],)).fetchone()[0], 0)
            row = db.execute("SELECT access_secret_sha256,contributor_public_key,reviewer_public_key FROM uec.community_secure_inboxes WHERE case_id=%s", (claim["case_id"],)).fetchone()
            self.assertEqual(row, (None, "", ""))
            db.execute("UPDATE uec.community_secure_inboxes SET updated_at=now()-interval '31 days' WHERE case_id=%s", (claim["case_id"],))
        self.assertEqual(self.request("/api/private/community/secure/maintenance", {}, operator=True)[1]["purged"], 1)
        with checked_connection(self.dsn) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM uec.community_secure_events WHERE case_id=%s", (claim["case_id"],)).fetchone()[0], 0)

    def test_invalid_plaintext_fields_size_expiry_and_legacy(self):
        claim = self.submission()
        for change in ({"plaintext": "not allowed"}, {"ciphertext": "plaintext"},
                       {"reviewer_fingerprint": "c" * 40}, {"contributor_fingerprint": "b" * 40},
                       {"ciphertext": CIPHERTEXT.replace("END PGP MESSAGE", "END PGP PUBLIC KEY BLOCK")}):
            self.assertEqual(self.request("/api/community/secure/submissions", {**claim, **change})[0], 400)
        self.assertEqual(self.request("/api/community/secure/submissions", raw=b"x" * (129 * 1024))[0], 413)
        self.assertEqual(self.request("/api/community/secure/submissions", claim)[0], 201)
        with checked_connection(self.dsn) as db:
            db.execute("UPDATE uec.community_secure_inboxes SET created_at=now()-interval '3 days',expires_at=now()-interval '1 day' WHERE case_id=%s", (claim["case_id"],))
        auth = {k: claim[k] for k in ("case_id", "access_secret")}
        self.assertEqual(self.request("/api/community/secure/inbox", auth)[0], 404)
        self.assertEqual(self.request("/api/community/secure/submissions", claim)[0], 409)
        self.assertEqual(self.request("/api/private/community/secure/maintenance", {}, operator=True)[0], 200)
        legacy = {"kind": "bug", "consent": True, "description": "Synthetic relay compatibility test",
                  "expected_behavior": "Accept legacy bug", "reproduction_steps": "Submit synthetic form",
                  "page_url": "https://example.invalid/"}
        code, receipt = self.request("/api/community/submissions", legacy)
        self.assertEqual(code, 201)
        self.legacy_ids.append(receipt["submission_id"])
        self.assertEqual(self.request("/api/community/status", {k: receipt[k] for k in ("submission_id", "receipt_secret")})[0], 200)

    def test_v0_unchanged_and_evidence_updates_forbidden(self):
        with checked_connection(self.dsn) as db:
            self.assertEqual(verify_connection(db, load_contract(ROOT / "pipeline/contracts/development-baseline.json"))["status"], "verified")
        claim = self.submission()
        self.assertEqual(self.request("/api/community/secure/submissions", claim)[0], 201)
        with checked_connection(self.dsn) as db:
            for table in ("community_secure_messages", "community_secure_events"):
                with self.assertRaises(psycopg.errors.ObjectInUse):
                    with db.transaction():
                        db.execute(f"UPDATE uec.{table} SET case_id=case_id WHERE case_id=%s", (claim["case_id"],))

    def test_secure_and_legacy_share_daily_admission_cap(self):
        with checked_connection(self.dsn) as db:
            current = db.execute("SELECT (SELECT count(*) FROM uec.community_submissions WHERE created_at>=current_date)+(SELECT count(*) FROM uec.community_secure_inboxes WHERE created_at>=current_date)").fetchone()[0]
        self.assertLess(current, 999)
        self.api.stop()
        self.api = LocalApi(self.dsn, daily_limit=current + 1)
        self.addCleanup(self.api.stop)
        claim = self.submission()
        self.assertEqual(self.request("/api/community/secure/submissions", claim)[0], 201)
        self.assertEqual(self.request("/api/community/secure/submissions", self.submission())[0], 429)
        legacy = {"kind": "bug", "consent": True, "description": "Synthetic cap test",
                  "expected_behavior": "Capacity reached", "reproduction_steps": "Submit",
                  "page_url": "https://example.invalid/"}
        self.assertEqual(self.request("/api/community/submissions", legacy)[0], 429)

    def test_proposed_runtime_grants_cannot_read_source_or_rewrite_evidence(self):
        role = sql.Identifier("uec_secure_test_" + uuid.uuid4().hex)
        identifier = str(uuid.uuid4())
        with checked_connection(self.dsn) as db, db.transaction(force_rollback=True):
            db.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(role))
            db.execute(sql.SQL("GRANT USAGE ON SCHEMA uec TO {}").format(role))
            db.execute(sql.SQL("GRANT SELECT,INSERT,UPDATE,DELETE ON uec.community_secure_inboxes TO {}").format(role))
            db.execute(sql.SQL("GRANT SELECT,INSERT,DELETE ON uec.community_secure_messages TO {}").format(role))
            db.execute(sql.SQL("GRANT SELECT,INSERT ON uec.community_secure_events TO {}").format(role))
            db.execute(sql.SQL("SET LOCAL ROLE {}").format(role))
            self.assertFalse(db.execute("SELECT has_table_privilege(current_user,'uec.source_records','SELECT')").fetchone()[0])
            db.execute("INSERT INTO uec.community_secure_inboxes(case_id,kind,protocol,access_secret_sha256,contributor_public_key,contributor_fingerprint,reviewer_public_key,reviewer_fingerprint,expires_at) VALUES(%s,'bug','uec-openpgp-inbox-v1',%s,%s,%s,%s,%s,now()+interval '1 day')",
                       (identifier, "c" * 64, PUBLIC_KEY, "a" * 40, PUBLIC_KEY, "b" * 40))
            db.execute("INSERT INTO uec.community_secure_messages(case_id,message_id,ordinal,author,ciphertext) VALUES(%s,%s,1,'contributor',%s)",
                       (identifier, str(uuid.uuid4()), CIPHERTEXT))
            db.execute("INSERT INTO uec.community_secure_events(case_id,action,actor_role) VALUES(%s,'received','contributor')", (identifier,))
            with self.assertRaises(psycopg.errors.InsufficientPrivilege), db.transaction():
                db.execute("UPDATE uec.community_secure_messages SET ordinal=2 WHERE case_id=%s", (identifier,))
            db.execute("DELETE FROM uec.community_secure_inboxes WHERE case_id=%s", (identifier,))
            self.assertEqual(db.execute("SELECT count(*) FROM uec.community_secure_events WHERE case_id=%s", (identifier,)).fetchone()[0], 0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--serve", type=Path, help="public-only synthetic bootstrap JSON; local integration only")
    args, remaining = parser.parse_known_args()
    if args.prepare or args.serve:
        dsn = os.environ["UEC_SECURE_TEST_DATABASE_URL"]
        prepare(dsn)
        if args.serve:
            bootstrap = json.loads(args.serve.read_text(encoding="utf-8"))
            if set(bootstrap) != {"reviewer_public_key", "reviewer_fingerprint", "operator_token"}:
                raise RuntimeError("bootstrap must contain only public key, fingerprint and local test operator token")
            api = LocalApi(dsn, bootstrap["reviewer_public_key"], bootstrap["reviewer_fingerprint"], bootstrap["operator_token"])
            print(json.dumps({"origin": api.origin, "api_pid": api.process.pid, "database": DATABASE,
                              "experimental_local_only": True}), flush=True)
            try:
                while api.process.poll() is None:
                    time.sleep(.5)
            except KeyboardInterrupt:
                pass
            finally:
                api.stop()
        else:
            print("Assigned disposable v0 verified; migration rollback trial and installation passed.")
    else:
        unittest.main(argv=[__file__, *remaining])
