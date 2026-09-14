"""Docker E2E for the private UK-candidate handoff and review boundary."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

import psycopg

try:
    from .fixture import E2EEnvironment
except ImportError:
    from fixture import E2EEnvironment

from pipeline.sources.uk.fsa_approved.adapter import FsaApprovedEstablishmentsAdapter

ROOT = Path(__file__).resolve().parents[3]
IMPORTER = ROOT / "pipeline/scripts/maintenance/import-candidate.py"


class CandidateImportE2ETests(unittest.TestCase):
    @classmethod
    def counts_for(cls):
        tables = ("raw_artifacts", "acquisition_runs", "acquisition_run_artifacts", "source_records",
                  "facilities", "observations", "releases", "release_members", "publication_review_events")
        with psycopg.connect(cls.env.database_url) as db:
            return {table: db.execute(f"SELECT count(*) FROM uec.{table}").fetchone()[0] for table in tables}

    def counts(self):
        return self.counts_for()

    @classmethod
    def setUpClass(cls):
        if os.environ.get("UEC_RUN_E2E") != "1":
            raise unittest.SkipTest("set UEC_RUN_E2E=1 to run Docker-backed E2E tests")
        cls.env = E2EEnvironment().start()
        cls.temp = tempfile.TemporaryDirectory()
        root = Path(cls.temp.name)
        raw = root / "uk-monthly.csv"
        raw.write_bytes(
            b"AppNo,TradingName,Country,CompetentAuthority,X,Y,AddressWithheld,All_Activities,Address1,Town,Postcode\n"
            b"UK-E2E-1,Example Foods,England,Food Standards Agency,-0.12,51.50,No,CP,House Farm,London,SW1\n"
        )
        manifest = FsaApprovedEstablishmentsAdapter().run(raw, root / "run", {
            "source_url": "https://example.invalid/uk-e2e.csv",
            "retrieved_at_utc": "2026-09-13T00:00:00Z",
            "checksum_sha256": __import__("hashlib").sha256(raw.read_bytes()).hexdigest(),
            "byte_size": raw.stat().st_size,
            "code_version": "e2e",
            "config_version": "fsa-e2e",
        })
        cls.release_id = "candidate-uk-e2e"
        cls.run_dir = root / "run"
        command = [sys.executable, str(IMPORTER), "--manifest", str(cls.run_dir / "manifest.json"),
                   "--normalized", str(cls.run_dir / "normalized/records.jsonl"), "--raw", str(raw),
                   "--release-id", cls.release_id, "--database-url", cls.env.database_url, "--disposable-db"]
        first = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        if first.returncode:
            cls.temp.cleanup(); cls.env.stop()
            raise RuntimeError(f"candidate importer failed:\n{first.stdout}\n{first.stderr}")
        second = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        if second.returncode:
            cls.temp.cleanup(); cls.env.stop()
            raise RuntimeError(f"candidate importer rerun failed:\n{second.stdout}\n{second.stderr}")
        cls.initial_counts = cls.counts_for()
        cls._record_id = None

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "temp", None):
            cls.temp.cleanup()
        if getattr(cls, "env", None):
            cls.env.stop()

    def request(self, path, headers=None):
        request = urllib.request.Request(f"http://127.0.0.1:{self.env.api_port}{path}", headers=headers or {})
        return urllib.request.urlopen(request, timeout=10)

    def test_import_is_idempotent_and_candidate_is_not_public_or_previewable(self):
        with psycopg.connect(self.env.database_url) as db:
            source_count, observation_count, artifact_count, release_member_count, review_count, release_count, run_count = db.execute(
                """SELECT count(DISTINCT r.source_record_id), count(DISTINCT o.observation_id)
                   , (SELECT count(*) FROM uec.raw_artifacts WHERE storage_key LIKE 'private-staging/%')
                   , (SELECT count(*) FROM uec.release_members WHERE release_id=%s)
                   , (SELECT count(*) FROM uec.publication_review_events WHERE release_id=%s)
                   , (SELECT count(*) FROM uec.releases WHERE release_id=%s)
                   , (SELECT count(*) FROM uec.acquisition_runs WHERE source_id='fsa_approved_establishments')
                   FROM uec.source_records r JOIN uec.observations o USING (source_record_id)
                   WHERE r.source_id='fsa_approved_establishments'""", (self.release_id, self.release_id, self.release_id)
            ).fetchone()
            self.assertEqual((source_count, observation_count, artifact_count, release_member_count, review_count, release_count, run_count), (1, 1, 1, 1, 1, 1, 2))
            review_state = db.execute("SELECT factual_review_status, privacy_screening_status, maintainer_approval, publication_eligible FROM uec.publication_review_events WHERE release_id=%s", (self.release_id,)).fetchone()
            self.assertEqual(review_state, ("unreviewed", "pending", "pending", False))
        # The public route succeeds with an empty envelope, not an error.
        with self.request("/api/v2/locations?profile=official") as response:
            body = json.loads(response.read())
        self.assertEqual(body["data"], [])
        self.assertNotIn("source_values", json.dumps(body))
        preview = urllib.request.Request(
            f"http://127.0.0.1:{self.env.api_port}/api/dev/preview/candidates",
            headers={"X-UEC-Dev-Preview-Token": self.env.dev_preview_token},
        )
        with urllib.request.urlopen(preview, timeout=10) as response:
            self.assertEqual(json.loads(response.read())["data"], [])

    def test_review_version_unlocks_preview_only_then_suppression_relocks_it(self):
        now = datetime.now(timezone.utc)
        with psycopg.connect(self.env.database_url) as db:
            with db.transaction():
                record_id = db.execute("SELECT source_record_id FROM uec.source_records WHERE source_id='fsa_approved_establishments'").fetchone()[0]
                facility_id, observation_id = uuid.uuid4(), uuid.uuid4()
                db.execute("INSERT INTO uec.facilities(facility_id,canonical_name,country_code,city) VALUES (%s,'E2E reviewed candidate','GB','London')", (facility_id,))
                # Evidence is append-only: this is a new reviewed observation,
                # not an UPDATE that silently mutates the imported candidate.
                db.execute("""INSERT INTO uec.observations(observation_id,facility_id,source_record_id,observed_at,observation,classification,ruleset_id,rule_id,classification_category,classification_review_status,default_visible,coordinate_review_status,first_observed_at)
                    VALUES (%s,%s,%s,%s,'{}','{}','fsa-e2e','operator-review','processing','approved',true,'approved',%s)""",
                           (observation_id, facility_id, record_id, now, now))
                db.execute("INSERT INTO uec.release_members(release_id,facility_id,observation_id,default_visible) VALUES (%s,%s,%s,true)", (self.release_id, facility_id, observation_id))
                db.execute("""INSERT INTO uec.geocode_results(source_record_id,provider_id,query,match_method,status,attempt_number,result,precision,queried_at)
                    VALUES (%s,'synthetic-review','operator-supplied synthetic point','operator-review','accepted',1,ST_SetSRID(ST_MakePoint(-0.12,51.50),4326)::geography,'city',%s)""", (record_id, now))
                db.execute("INSERT INTO uec.publication_review_events(source_record_id,release_id,factual_review_status,privacy_screening_status,maintainer_approval,publication_eligible,reviewer_role) VALUES (%s,%s,'reviewed','passed','approved',true,'authorized-synthetic-operator')", (record_id, self.release_id))
        preview = urllib.request.Request(f"http://127.0.0.1:{self.env.api_port}/api/dev/preview/candidates", headers={"X-UEC-Dev-Preview-Token": self.env.dev_preview_token})
        with urllib.request.urlopen(preview, timeout=10) as response:
            preview_body = json.loads(response.read())
            self.assertEqual(len(preview_body["data"]), 1)
            self.assertNotIn("source_values", json.dumps(preview_body))
        for headers in ({"X-UEC-Dev-Preview-Token": self.env.dev_preview_token, "Host": "attacker.invalid"},
                        {"X-UEC-Dev-Preview-Token": self.env.dev_preview_token, "Origin": "https://attacker.invalid"},
                        {"X-UEC-Dev-Preview-Token": "wrong"}):
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(urllib.request.Request(preview.full_url, headers=headers), timeout=10)
            self.assertIn(error.exception.code, (401, 403))
        with psycopg.connect(self.env.database_url) as db:
            db.execute("INSERT INTO uec.record_access_events(source_record_id,action,reason_category,policy_version,maintainer) VALUES (%s,'public_access_revoked','privacy','ethics-v1','authorized-synthetic-operator')", (record_id,))
        with urllib.request.urlopen(preview, timeout=10) as response:
            self.assertEqual(json.loads(response.read())["data"], [])

    def test_bad_row_rolls_back_candidate_import(self):
        before = self.counts()
        normalized = self.run_dir / "normalized/records.jsonl"
        original = normalized.read_text(encoding="utf-8")
        bad = self.run_dir / "normalized/bad-records.jsonl"
        bad.write_text(original + json.dumps({"source_id": "fsa_approved_establishments", "source_row": 999}) + "\n", encoding="utf-8")
        manifest = json.loads((self.run_dir / "manifest.json").read_text(encoding="utf-8"))
        manifest["normalized_rows"] = 2
        manifest["normalized_sha256"] = __import__("hashlib").sha256(bad.read_bytes()).hexdigest()
        bad_manifest = self.run_dir / "bad-manifest.json"
        bad_manifest.write_text(json.dumps(manifest), encoding="utf-8")
        command = [sys.executable, str(IMPORTER), "--manifest", str(bad_manifest), "--normalized", str(bad),
                   "--raw", str(self.run_dir.parent / "uk-monthly.csv"), "--release-id", "candidate-uk-bad",
                   "--database-url", self.env.database_url, "--disposable-db"]
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        after = self.counts()
        self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
