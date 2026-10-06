"""Synthetic-only community pilot proof against an explicitly disposable database.

Apply migrations to an empty database, then set UEC_COMMUNITY_TEST_DATABASE_URL
and UEC_COMMUNITY_TEST_BINARY. This launches and stops its own loopback API;
it never uses a running developer API or starts Docker itself.
"""
import concurrent.futures
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

import psycopg

try:
    from .fixture import E2EEnvironment
except ImportError:
    from fixture import E2EEnvironment

ROOT = Path(__file__).resolve().parents[3]


class CommunityIntakeProof(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dsn = os.environ.get("UEC_COMMUNITY_TEST_DATABASE_URL")
        binary = os.environ.get("UEC_COMMUNITY_TEST_BINARY")
        if not cls.dsn or not binary:
            if os.environ.get("UEC_RUN_E2E") != "1":
                raise unittest.SkipTest("set UEC_RUN_E2E=1 to run Docker-backed E2E tests")
            # The full CI E2E gate owns a fresh fixture. Keep its database,
            # stop only its temporary default API, and launch the pilot below.
            owned = E2EEnvironment().start()
            cls.addClassCleanup(owned.stop)
            cls.dsn = owned.database_url
            binary = owned.cargo_target_dir / ("uec-api.exe" if os.name == "nt" else "uec-api")
            owned.backend.terminate()
            owned.backend.wait(timeout=10)
        parsed = psycopg.conninfo.conninfo_to_dict(cls.dsn)
        if parsed.get("host") not in ("localhost", "127.0.0.1"):
            raise RuntimeError("proof requires a loopback disposable database")
        with psycopg.connect(cls.dsn) as db:
            if db.execute("SELECT count(*) FROM uec.source_records").fetchone()[0] != 0:
                raise RuntimeError("proof refuses a nonempty source database")
            if db.execute("SELECT count(*) FROM uec.community_submissions").fetchone()[0] != 0:
                raise RuntimeError("proof requires empty community intake")
        seed = E2EEnvironment.__new__(E2EEnvironment)
        seed.database_url = cls.dsn
        seed.seed_community_scenario()
        cls.token = secrets.token_urlsafe(48)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        cls.origin = f"http://127.0.0.1:{port}"
        env = {key: value for key, value in os.environ.items()
               if not key.startswith("UEC_")}
        env.update({
            "UEC_DATABASE_URL": cls.dsn, "PORT": str(port),
            "UEC_BIND_HOST": "127.0.0.1", "UEC_RUNTIME_MODE": "development",
            "UEC_COMMUNITY_ENABLED": "true", "UEC_COMMUNITY_PUBLIC_ENABLED": "true",
            "UEC_COMMUNITY_OPERATOR_TOKEN": cls.token,
            "UEC_COMMUNITY_RETENTION_DAYS": "30",
            "UEC_COMMUNITY_CONTACT_RETENTION_DAYS": "7",
            "UEC_COMMUNITY_RECEIPT_DAYS": "14",
            "UEC_COMMUNITY_DAILY_INTAKE_CAP": "20",
            "UEC_COMMUNITY_PENDING_CAP": "20",
        })
        cls.process = subprocess.Popen(
            [str(Path(binary).resolve())], cwd=ROOT, env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        cls.addClassCleanup(cls.stop_api)
        for _ in range(100):
            try:
                with urllib.request.urlopen(cls.origin + "/health/live", timeout=1):
                    return
            except (OSError, urllib.error.URLError):
                if cls.process.poll() is not None:
                    raise RuntimeError("owned community API failed to start")
                time.sleep(.1)
        raise RuntimeError("owned community API readiness timed out")

    @classmethod
    def stop_api(cls):
        if cls.process.poll() is None:
            cls.process.terminate()
            try:
                cls.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                cls.process.kill()
                cls.process.wait(timeout=5)

    def request(self, path, body=None, token=None, raw=None):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        data = raw if raw is not None else (
            json.dumps(body).encode() if body is not None else None)
        request = urllib.request.Request(self.origin + path, data=data, headers=headers)
        try:
            response = urllib.request.urlopen(request, timeout=10)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            code = response.code
            payload = json.loads(response.read())
            self.assertTrue(response.headers.get("Cache-Control", "").startswith("no-store"))
            self.assertTrue(response.headers.get("Referrer-Policy") == "no-referrer")
        return code, payload

    def submit(self, claim):
        code, receipt = self.request("/api/community/submissions", claim)
        self.assertTrue(code == 201, "valid synthetic intake must succeed")
        self.assertTrue(set(receipt) == {"submission_id", "receipt_secret", "status"})
        self.assertTrue(len(receipt["receipt_secret"]) >= 32)
        return receipt

    def disposition(self, receipt, action, **fields):
        return self.request(
            f"/api/private/community/submissions/{receipt['submission_id']}/disposition",
            {"action": action, "reason_code": "privacy" if action == "remove" else "eligible",
             **fields}, token=self.token)

    def test_private_intake_live_public_gates_and_retention(self):
        with psycopg.connect(self.dsn) as db:
            baseline = db.execute(
                "SELECT (SELECT count(*) FROM uec.source_records),"
                "(SELECT count(*) FROM uec.release_members)").fetchone()
            target, facility = db.execute(
                "SELECT source_record_id,facility_id FROM uec.observations "
                "JOIN uec.source_records USING(source_record_id) "
                "WHERE source_record_key='screened-unreviewed'").fetchone()
        other = str(uuid.uuid4())
        marker = "SYNTHETIC_PRIVATE_CLAIM"
        facility_claim = {"kind": "facility", "label": "Synthetic intake",
                          "country_code": "DK", "source_url": "https://example.invalid/evidence",
                          "description": marker, "contact_email": "synthetic@example.invalid",
                          "claimed_latitude": float(0), "claimed_longitude": float(0),
                          "claimed_precision": "unknown", "location_input_method": "manual_pin",
                          "consent": True}
        receipts = [
            self.submit(facility_claim),
            self.submit({"kind": "evidence", "target_record_id": str(facility),
                         "source_url": "https://example.invalid/evidence", "consent": True}),
            self.submit({"kind": "correction", "target_record_id": str(facility),
                         "description": marker, "consent": True}),
            self.submit({"kind": "duplicate", "target_record_id": str(facility),
                         "duplicate_record_id": other, "consent": True}),
            self.submit({"kind": "privacy_removal", "target_record_id": str(facility),
                         "description": marker, "consent": True}),
        ]
        optional_facility = self.submit({"kind": "facility", "label": "Synthetic no-source facility",
                                         "consent": True})
        unknown_country_facility = self.submit({"kind": "facility", "label": "Synthetic unknown-country facility",
                                                "country_code": "unknown", "consent": True})
        source_free_evidence = self.submit({"kind": "evidence", "target_record_id": str(facility),
                                            "description": "Synthetic supporting context without a URL",
                                            "consent": True})
        private = receipts[0]
        code, status = self.request("/api/community/status", {
            "submission_id": private["submission_id"], "receipt_secret": private["receipt_secret"]})
        self.assertTrue(code == 200 and set(status) == {"submission_id", "status"})
        code, _ = self.request("/api/private/community/submissions", token=private["receipt_secret"])
        self.assertTrue(code == 404, "receipt must not authorize the operator")
        code, queue = self.request("/api/private/community/submissions", token=self.token)
        self.assertTrue(code == 200 and len(queue["submissions"]) == 8)
        serialized = json.dumps(queue)
        self.assertTrue("contact_email" not in serialized and private["receipt_secret"] not in serialized)
        with psycopg.connect(self.dsn) as db:
            claim, stored_hash = db.execute(
                "SELECT claim,receipt_secret_sha256 FROM uec.community_submissions WHERE submission_id=%s",
                (private["submission_id"],)).fetchone()
            self.assertTrue("contact_email" not in claim)
            self.assertTrue(stored_hash == hashlib.sha256(private["receipt_secret"].encode()).hexdigest())
            self.assertTrue(db.execute("SELECT count(*) FROM uec.community_submission_contacts").fetchone()[0] == 1)
            optional_claim = db.execute(
                "SELECT claim FROM uec.community_submissions WHERE submission_id=%s",
                (optional_facility["submission_id"],)).fetchone()[0]
            self.assertTrue(optional_claim.get("label") == "Synthetic no-source facility"
                            and "country_code" not in optional_claim and "source_url" not in optional_claim)
            unknown_claim = db.execute(
                "SELECT claim FROM uec.community_submissions WHERE submission_id=%s",
                (unknown_country_facility["submission_id"],)).fetchone()[0]
            self.assertTrue("country_code" not in unknown_claim and "source_url" not in unknown_claim)
            source_free_claim = db.execute(
                "SELECT claim FROM uec.community_submissions WHERE submission_id=%s",
                (source_free_evidence["submission_id"],)).fetchone()[0]
            self.assertTrue(source_free_claim.get("kind") == "evidence"
                            and source_free_claim.get("description") == "Synthetic supporting context without a URL"
                            and "source_url" not in source_free_claim)
        code, _ = self.request("/api/community/submissions", {**facility_claim, "unexpected": marker})
        self.assertTrue(code == 400)
        code, _ = self.request("/api/community/submissions", raw=b'{"kind":"facility","label":"' + b"x" * 13000 + b'"}')
        self.assertTrue(code == 400)
        code, _ = self.request("/api/community/claims?release_id=e2e-community")
        self.assertTrue(code == 400, "public profile must be explicitly selected")
        code, claims = self.request("/api/community/claims?profile=community&release_id=e2e-community")
        self.assertTrue(code == 200 and claims["claim_count"] == 0)
        for _ in range(3):
            code, _ = self.request("/api/community/status", {
                "submission_id": private["submission_id"], "receipt_secret": "invalid"})
            self.assertTrue(code == 404)
        code, _ = self.request("/api/community/status", {
            "submission_id": private["submission_id"], "receipt_secret": private["receipt_secret"]})
        self.assertTrue(code == 200, "guesses must not invalidate the legitimate receipt")
        code, _ = self.disposition(private, "link_community",
                                   community_record_id=str(target), release_id="e2e-community")
        self.assertTrue(code == 400, "intake must be screened before linkage")
        self.assertTrue(self.disposition(private, "screen")[0] == 200)
        self.assertTrue(self.disposition(receipts[4], "screen")[0] == 200)
        self.assertTrue(self.disposition(receipts[4], "link_community",
                                        community_record_id=str(target), release_id="e2e-community")[0] == 400)
        code, _ = self.disposition(private, "link_community",
                                   community_record_id=str(target), release_id="e2e-community")
        self.assertTrue(code == 200)
        code, claims = self.request("/api/community/claims?profile=community&release_id=e2e-community")
        self.assertTrue(code == 200 and claims["claim_count"] == 1)
        self.assertTrue(marker not in json.dumps(claims) and "latitude" not in json.dumps(claims))
        claim = claims["claims"][0]
        self.assertTrue(claim["factual_review_status"] == "unreviewed" and claim["project_approval"] == "not-approved")
        self.assertTrue("unreviewed" in claim["warning"].lower())
        code, detail = self.request(f"/api/community/claims/{private['submission_id']}?profile=community&release_id=e2e-community")
        self.assertTrue(code == 200 and detail == claim)
        code, status = self.request("/api/community/status", {
            "submission_id": private["submission_id"], "receipt_secret": private["receipt_secret"]})
        self.assertTrue(code == 200 and status.get("public_record_url") == claim["public_record_url"])
        with psycopg.connect(self.dsn) as db:
            db.execute("INSERT INTO uec.record_access_events(source_record_id,action,reason_category,policy_version,maintainer) "
                       "VALUES(%s,'public_access_revoked','privacy','ethics-v1','synthetic-proof')", (target,))
        code, claims = self.request("/api/community/claims?profile=community&release_id=e2e-community")
        self.assertTrue(code == 200 and claims["claim_count"] == 0)
        code, _ = self.request(f"/api/community/claims/{private['submission_id']}?profile=community&release_id=e2e-community")
        self.assertTrue(code == 404, "current record restriction must hide the direct claim")
        code, status = self.request("/api/community/status", {
            "submission_id": private["submission_id"], "receipt_secret": private["receipt_secret"]})
        self.assertTrue(code == 200 and "public_record_url" not in status)
        self.assertTrue(self.disposition(private, "remove")[0] == 200)
        code, _ = self.request("/api/community/status", {
            "submission_id": private["submission_id"], "receipt_secret": private["receipt_secret"]})
        self.assertTrue(code == 404, "removal must revoke the receipt")
        with psycopg.connect(self.dsn) as db:
            row = db.execute("SELECT claim,receipt_secret_sha256,linked_source_record_id FROM uec.community_submissions "
                             "WHERE submission_id=%s", (private["submission_id"],)).fetchone()
            self.assertTrue(row == ({}, None, None))
            self.assertTrue(db.execute("SELECT count(*) FROM uec.community_submission_contacts").fetchone()[0] == 0)
            db.execute("UPDATE uec.community_submissions SET created_at=now()-interval '40 days',"
                       "receipt_expires_at=now()-interval '1 day' WHERE submission_id=%s",
                       (receipts[1]["submission_id"],))
        code, stats = self.request("/api/private/community/maintenance", {}, token=self.token)
        self.assertTrue(code == 200 and stats["submissions_expired"] == 1)
        with psycopg.connect(self.dsn) as db:
            current = db.execute("SELECT (SELECT count(*) FROM uec.source_records),"
                                 "(SELECT count(*) FROM uec.release_members)").fetchone()
            self.assertTrue(current == baseline, "intake must not create source or release membership")
            self.assertTrue(db.execute("SELECT count(*) FROM uec.community_submission_events "
                                       "WHERE submission_id=%s AND action='expire'",
                                       (receipts[1]["submission_id"],)).fetchone()[0] == 1)
        for operation in ("UPDATE uec.community_submission_events SET reason_code='other'",
                          "DELETE FROM uec.community_submission_events"):
            with psycopg.connect(self.dsn) as db:
                with self.assertRaises(psycopg.Error):
                    db.execute(operation)

        # Race the final pending slot; capacity must be atomic across clients.
        with psycopg.connect(self.dsn) as db:
            pending = db.execute("SELECT count(*) FROM uec.community_submissions WHERE status IN ('received','held')").fetchone()[0]
            for _ in range(19 - pending):
                db.execute("INSERT INTO uec.community_submissions(submission_id,kind,status,claim,receipt_expires_at,created_at) "
                           "VALUES(%s,'evidence','received','{}',now(),now()-interval '1 day')", (uuid.uuid4(),))
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as workers:
            results = list(workers.map(lambda _: self.request("/api/community/submissions", facility_claim)[0], range(2)))
        self.assertTrue(sorted(results) == [201, 429], "only one client can obtain the final pending slot")
        with psycopg.connect(self.dsn) as db:
            db.execute("UPDATE uec.community_submissions SET status='screened' WHERE status IN ('received','held')")
            today = db.execute("SELECT count(*) FROM uec.community_submissions WHERE created_at>=current_date").fetchone()[0]
            for _ in range(20 - today):
                db.execute("INSERT INTO uec.community_submissions(submission_id,kind,status,claim,receipt_expires_at) "
                           "VALUES(%s,'evidence','rejected','{}',now())", (uuid.uuid4(),))
        code, _ = self.request("/api/community/submissions", facility_claim)
        self.assertTrue(code == 429, "daily cap also applies when the pending queue is empty")


if __name__ == "__main__":
    unittest.main()
