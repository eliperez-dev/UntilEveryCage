"""Rollback-only account quota acceptance on the approved local V0 copy."""
import hashlib
import importlib.util
import os
from pathlib import Path
import unittest
from urllib.parse import urlsplit
import uuid
from unittest.mock import patch

import psycopg

from pipeline.geocoding.accounts import attribute_history
from pipeline.scripts.release_baseline import load_contract,verify_connection

ROOT=Path(__file__).resolve().parents[2]
MIGRATION=ROOT/"pipeline/migrations/101_geocode_account_budgets.sql"
DATABASE="uec_launch_sources_test_20261025"
SPEC=importlib.util.spec_from_file_location("account_activation_real",ROOT/"pipeline/scripts/stages/activate-locationiq-preview.py")
ACTIVATION=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ACTIVATION)


def check_unmatched_retry(connection):
    """Exercise retained real jobs inside the caller's rollback transaction."""
    class BorrowedConnection:
        def __enter__(self): return connection
        def __exit__(self,*_): return False
    with patch.object(ACTIVATION.psycopg,"connect",return_value=BorrowedConnection()):
        report,jobs=ACTIVATION.requeue_unmatched("borrowed",limit=2,provider_account="secondary")
        if report["provider_calls"] != 0 or report["jobs_staged"] != len(jobs):
            raise AssertionError("retry staging accounting mismatch")
        for job in jobs:
            current=connection.execute("""SELECT event_type,attempt_number,
                details->>'recovery_reason' FROM uec.geocode_job_events WHERE job_id=%s
                ORDER BY occurred_at DESC,event_id DESC LIMIT 1""",(job,)).fetchone()
            if current != ("queued",2,"operator_authorized_unmatched_retry"):
                raise AssertionError("retry did not retain attempt history")
    return len(jobs)


@unittest.skipUnless(urlsplit(os.environ.get("UEC_DATABASE_URL","")).path.strip("/")==DATABASE,
                     "assigned disposable real-data database required")
class GeocodeAccountPostgisTests(unittest.TestCase):
    def test_account_history_quota_rate_and_duplicate_guards_rollback(self):
        with psycopg.connect(os.environ["UEC_DATABASE_URL"],autocommit=True) as c:
            with c.transaction(force_rollback=True):
                c.execute("SET LOCAL statement_timeout='60s'")
                if not c.execute("SELECT 1 FROM uec.schema_migrations WHERE version=%s",
                                  (MIGRATION.stem,)).fetchone():
                    c.execute(MIGRATION.read_text(encoding="utf-8"))
                    c.execute("INSERT INTO uec.schema_migrations(version,sha256) VALUES(%s,%s)",
                        (MIGRATION.stem,hashlib.sha256(MIGRATION.read_bytes()).hexdigest()))
                day=c.execute("SELECT (now() AT TIME ZONE 'UTC')::date").fetchone()[0]
                fingerprint="""SELECT count(*),md5(string_agg(reservation_id::text||':'||
                    job_id::text||':'||attempt_number::text||':'||retry_number::text,
                    '|' ORDER BY reservation_id)) FROM uec.geocode_request_reservations
                    WHERE provider_id='locationiq' AND budget_date=%s"""
                before=c.execute(fingerprint,(day,)).fetchone()
                history=attribute_history(c,budget_date=day,
                    secondary_workers=("de-parallel-secondary-20261027-locationiq",))
                self.assertEqual(sum(history["accounts"].values()),before[0])
                self.assertGreater(history["accounts"]["secondary"],0)
                self.assertEqual(history,attribute_history(c,budget_date=day,
                    secondary_workers=("de-parallel-secondary-20261027-locationiq",)))
                self.assertEqual(before,c.execute(fingerprint,(day,)).fetchone())
                # Use a synthetic provider under the same SQL admission function
                # so the real account balances and rows are never altered.
                provider="fixture-account-"+uuid.uuid4().hex
                for account in ("one","two"):
                    c.execute("INSERT INTO uec.geocode_provider_accounts VALUES(%s,%s,1,1.05)",
                              (provider,account))
                source=c.execute("SELECT source_record_id FROM uec.geocode_jobs LIMIT 1").fetchone()[0]
                jobs=[c.execute("INSERT INTO uec.geocode_jobs(source_record_id,provider_id,query) VALUES(%s,%s,%s) RETURNING job_id",
                    (source,provider,"synthetic account request "+str(n))).fetchone()[0] for n in range(3)]
                def reserve(account,job,interval=1.05):
                    return c.execute("SELECT * FROM uec.reserve_geocode_account_request(%s,%s,%s,1,1,1,%s)",
                                     (provider,account,job,interval)).fetchone()
                self.assertIsNotNone(reserve("one",jobs[0])[0])
                self.assertEqual(reserve("one",jobs[1]),(None,"budget"))
                self.assertIsNotNone(reserve("two",jobs[1])[0])
                # Cross-account deduplication is global, not one copy per key.
                c.execute("INSERT INTO uec.geocode_provider_accounts VALUES(%s,'three',1,1.05)",(provider,))
                with self.assertRaises(psycopg.errors.UniqueViolation):
                    with c.transaction(): reserve("three",jobs[0])
                with self.assertRaises(psycopg.errors.CheckViolation):
                    with c.transaction(): reserve("three",jobs[2],0)
                c.execute("INSERT INTO uec.geocode_provider_accounts VALUES(%s,'rate',2,60)",(provider,))
                first=c.execute("SELECT * FROM uec.reserve_geocode_account_request(%s,'rate',%s,1,1,2,60)",
                                (provider,jobs[2])).fetchone()
                self.assertIsNotNone(first[0])
                self.assertEqual(c.execute("SELECT * FROM uec.reserve_geocode_account_request(%s,'rate',%s,2,1,2,60)",
                                           (provider,jobs[2])).fetchone(),(None,"rate_limited"))
                self.assertGreater(check_unmatched_retry(c),0)
                self.assertEqual(verify_connection(c,load_contract(
                    ROOT/"pipeline/contracts/development-baseline.json"))["status"],"verified")


if __name__=="__main__": unittest.main()
