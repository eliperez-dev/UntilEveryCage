"""Source-bound result reuse, with opt-in rollback-only real-data acceptance."""
import os
from pathlib import Path
import unittest

import psycopg

from pipeline.geocoding import shared_query_reconciliation as shared
from pipeline.scripts.release_baseline import load_contract, verify_connection


class SharedQueryTests(unittest.TestCase):
    def test_other_database_rejected_before_planning_or_mutation(self):
        class Connection:
            def execute(self, sql):
                if sql != "SELECT current_database()": raise AssertionError("must not read or write source tables")
                return self
            def fetchone(self): return ("not_the_assigned_copy",)
        for apply in (False, True):
            with self.assertRaises(ValueError): shared.reconcile(Connection(), apply=apply)


@unittest.skipUnless(os.environ.get("UEC_SHARED_QUERY_SQL_TESTS") == "1", "assigned local test copy required")
class SharedQueryPostgisTests(unittest.TestCase):
    def test_real_identical_targets_reuse_existing_evidence_without_requests(self):
        with psycopg.connect(os.environ["UEC_DATABASE_URL"],
                             application_name="uec-shared-query-acceptance",
                             options="-c statement_timeout=30000") as connection:
            self.assertEqual(connection.execute("SELECT current_database()").fetchone()[0], shared.DATABASE)
            contract = load_contract(Path(__file__).parents[1]/"contracts/development-baseline.json")
            self.assertEqual(verify_connection(connection, contract)["status"], "verified")
            def requests():
                return connection.execute("""SELECT count(DISTINCT reservation.reservation_id)
                    FROM uec.geocode_request_reservations reservation JOIN real_preview.geocode_targets target USING(job_id)
                    WHERE target.source_id='pl.giw.approved-food'""").fetchone()[0]
            before = requests()
            preview = shared.reconcile(connection)
            if not preview["shared_targets"]:
                # The retained cohort may already have completed this stage.
                # Verify its real links instead of manufacturing pending rows.
                completed, missing_links = connection.execute("""SELECT count(*),count(*) FILTER(WHERE NOT EXISTS(
                    SELECT 1 FROM real_preview.geocode_targets linked
                    WHERE linked.job_id=(event.details->>'shared_requested_job_id')::uuid
                      AND linked.candidate_id=original.candidate_id))
                    FROM uec.geocode_job_events event
                    JOIN real_preview.geocode_targets original USING(job_id)
                    WHERE event.details->>'processing_mode'='shared_query_reconciliation'
                      AND original.source_id='pl.giw.approved-food'""").fetchone()
                self.assertGreater(completed, 0, "real pending or completed shared-address targets required")
                self.assertEqual(missing_links, 0)
            with connection.transaction(force_rollback=True):
                result = shared.reconcile(connection, apply=True)
                self.assertEqual(result["targets_linked"], preview["shared_targets"])
                self.assertEqual(result["display_evidence_added"], preview["targets_with_validated_point"])
                self.assertEqual(result["duplicate_jobs_closed"], preview["shared_targets"])
                self.assertEqual(shared.reconcile(connection, apply=True)["targets_linked"], 0)
                self.assertEqual(requests(), before)
                self.assertEqual(verify_connection(connection, contract)["status"], "verified")
            self.assertEqual(shared.reconcile(connection), preview)
            self.assertEqual(requests(), before)
            self.assertEqual(verify_connection(connection, contract)["status"], "verified")


if __name__ == "__main__": unittest.main()
