import os
import unittest
from pathlib import Path

import psycopg


ROOT = Path(__file__).parents[1]
MIGRATION = ROOT / "migrations" / "096_preview_enrichment_reconciliation.sql"


class EnrichmentReconciliationViewTests(unittest.TestCase):
    def test_migration_keeps_view_shape_and_derives_state_without_mutating_evidence(self):
        sql = MIGRATION.read_text(encoding="utf-8")
        self.assertIn("CREATE OR REPLACE VIEW real_preview.candidate_enrichment_reconciliation", sql)
        for column in ("candidate.candidate_id", "candidate.source_id", "candidate.snapshot_sha256",
                       "AS state_code", "AS reason_code"):
            self.assertIn(column, sql)
        for state in ("restricted", "source_coordinate", "resolved", "conflict", "unresolved",
                      "retryable", "provider_blocked", "queued", "insufficient"):
            self.assertIn(f"'{state}'", sql)
        self.assertIn("real_preview.candidate_display", sql)
        self.assertIn("target.snapshot_sha256 = candidate.snapshot_sha256", sql)
        self.assertIn("event.snapshot_sha256 = candidate.snapshot_sha256", sql)
        self.assertIn("ORDER BY event.occurred_at DESC, event.event_id DESC", sql)
        self.assertNotRegex(sql, r"(?im)^\s*(INSERT|UPDATE|DELETE|TRUNCATE)\b")
        self.assertNotIn("response", sql.lower())
        self.assertNotIn("query", sql.lower())

    @unittest.skipUnless(
        os.environ.get("UEC_ENRICHMENT_RECONCILIATION_REAL_DATA_ACCEPTANCE") == "true"
        and os.environ.get("UEC_DATABASE_URL"),
        "set UEC_ENRICHMENT_RECONCILIATION_REAL_DATA_ACCEPTANCE=true with assigned private DB URL",
    )
    def test_database_view_reconciles_displays_and_terminal_events_with_rollback(self):
        connection = psycopg.connect(os.environ["UEC_DATABASE_URL"], connect_timeout=15)
        try:
            connection.execute("SET statement_timeout='20000ms'")
            self.assertEqual(connection.execute("SELECT current_database()").fetchone()[0],
                             "uec_launch_sources_test_20261025")
            columns = connection.execute("""
                SELECT array_agg(column_name::text ORDER BY ordinal_position)
                FROM information_schema.columns
                WHERE table_schema='real_preview' AND table_name='candidate_enrichment_reconciliation'
            """).fetchone()[0]
            self.assertEqual(columns, ["candidate_id", "source_id", "snapshot_sha256", "state_code", "reason_code"])
            displayed_mismatches = connection.execute("""
                SELECT count(*) FROM real_preview.candidate_enrichment_reconciliation state
                JOIN real_preview.candidate_display display USING(candidate_id,snapshot_sha256)
                WHERE state.source_id IN ('de.locations','es.locations')
                  AND display.display_latitude BETWEEN -90 AND 90
                  AND display.display_longitude BETWEEN -180 AND 180
                  AND (display.display_latitude <> 0 OR display.display_longitude <> 0)
                  AND state.state_code NOT IN ('resolved','restricted','source_coordinate')
            """).fetchone()[0]
            self.assertEqual(displayed_mismatches, 0)
            shown = connection.execute("""
                SELECT count(*) FROM real_preview.candidate_enrichment_reconciliation state
                JOIN real_preview.candidate_display display USING(candidate_id,snapshot_sha256)
                WHERE state.source_id IN ('de.locations','es.locations')
                  AND state.state_code='resolved'
                  AND display.display_latitude BETWEEN -90 AND 90
                  AND display.display_longitude BETWEEN -180 AND 180
                  AND (display.display_latitude <> 0 OR display.display_longitude <> 0)
            """).fetchone()[0]
            self.assertGreater(shown, 0)

            target = connection.execute("""
                WITH latest AS (
                    SELECT DISTINCT ON (source_id) source_id,snapshot_sha256
                    FROM real_preview.source_preview_runs
                    ORDER BY source_id,created_at DESC,run_id DESC
                )
                SELECT target.job_id
                FROM real_preview.geocode_targets target
                JOIN real_preview.candidates candidate
                  ON candidate.candidate_id=target.candidate_id
                 AND candidate.snapshot_sha256=target.snapshot_sha256
                JOIN latest ON latest.source_id=candidate.source_id
                           AND latest.snapshot_sha256=candidate.snapshot_sha256
                JOIN uec.geocode_jobs job
                  ON job.job_id=target.job_id AND job.provider_id='geoapify'
                LEFT JOIN real_preview.candidate_display display
                  ON display.candidate_id=candidate.candidate_id
                 AND display.snapshot_sha256=candidate.snapshot_sha256
                WHERE candidate.source_id IN ('de.locations','es.locations')
                  AND display.display_latitude IS NULL
                  AND NOT EXISTS(
                      SELECT 1 FROM uec.public_access_restricted restricted
                      WHERE restricted.source_record_id=job.source_record_id
                  )
                ORDER BY candidate.source_id,candidate.candidate_id
                LIMIT 1
            """).fetchone()
            self.assertIsNotNone(target)
            job_id = target[0]
            cases = (
                ("accepted", False, "conflict", "provider_result_not_displayable"),
                ("review_required", False, "conflict", "provider_review_required"),
                ("unresolved", False, "unresolved", "provider_unresolved"),
                ("failed", True, "retryable", "provider_retryable_failure"),
                ("failed", False, "provider_blocked", "provider_nonretryable_failure"),
                ("started", False, "queued", "provider_job_active"),
                ("queued", False, "queued", "provider_job_active"),
            )
            observed = []
            for event_type, retryable, expected_state, expected_reason in cases:
                connection.execute("SAVEPOINT reconciliation_case")
                connection.execute("""
                    INSERT INTO uec.geocode_job_events
                        (job_id,event_type,attempt_number,retryable,details,occurred_at)
                    VALUES (%s,%s,1,%s,'{}'::jsonb,clock_timestamp()+interval '1 hour')
                """, (job_id, event_type, retryable))
                observed.append(connection.execute("""
                    SELECT state_code,reason_code
                    FROM real_preview.candidate_enrichment_reconciliation
                    WHERE candidate_id=(SELECT candidate_id FROM real_preview.geocode_targets WHERE job_id=%s)
                """, (job_id,)).fetchone())
                connection.execute("ROLLBACK TO SAVEPOINT reconciliation_case")
                connection.execute("RELEASE SAVEPOINT reconciliation_case")
            self.assertEqual(observed, [(state, reason) for _, _, state, reason in cases])
        finally:
            connection.rollback()
            connection.close()


if __name__ == "__main__":
    unittest.main()
