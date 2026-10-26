import os
import unittest
from pathlib import Path

import psycopg


ROOT = Path(__file__).parents[1]
MIGRATION = ROOT / "migrations" / "097_germany_audited_candidate_cache_alignment.sql"
EXPECTED_REJECT_MUTATION_MD5 = "cd250977853154d88600a40fee48d2b1"


class GermanyCandidateCacheAlignmentTests(unittest.TestCase):
    def test_migration_is_narrowly_guarded_and_preserves_append_only_evidence(self):
        sql = MIGRATION.read_text(encoding="utf-8")
        self.assertIn(EXPECTED_REJECT_MUTATION_MD5, sql)
        self.assertIn("pg_get_functiondef('real_preview.reject_mutation()'::regprocedure)", sql)
        self.assertIn("OLD.source_id = 'de.locations'", sql)
        self.assertIn("OLD.location_class <> 'numeric_source_coordinate'", sql)
        self.assertIn("NEW.display_latitude IS NULL", sql)
        self.assertIn("NEW.display_longitude IS NULL", sql)
        self.assertIn("NEW.display_geometry_source IS NULL", sql)
        self.assertIn("audit.outcome <> 'matched'", sql)
        self.assertIn("audit.outcome = 'matched'", sql)
        self.assertIn("source_preview_runs", sql)
        self.assertNotRegex(sql, r"(?im)^\s*(UPDATE|DELETE|TRUNCATE)\s+real_preview\.(geocode_display_evidence|germany_geocode_context_audit)\b")

    @unittest.skipUnless(
        os.environ.get("UEC_GERMANY_CACHE_ALIGNMENT_REAL_ACCEPTANCE") == "true"
        and os.environ.get("UEC_DATABASE_URL"),
        "set UEC_GERMANY_CACHE_ALIGNMENT_REAL_ACCEPTANCE=true with assigned private DB URL",
    )
    def test_database_cache_repair_is_current_audited_and_rollback_safe(self):
        connection = psycopg.connect(os.environ["UEC_DATABASE_URL"], connect_timeout=15)
        try:
            connection.execute("SET statement_timeout='20000ms'")
            self.assertEqual(connection.execute("SELECT current_database()").fetchone()[0],
                             "uec_launch_sources_test_20261025")
            leaked = connection.execute("""
                SELECT count(*)
                FROM real_preview.candidates candidate
                WHERE candidate.source_id='de.locations'
                  AND candidate.location_class <> 'numeric_source_coordinate'
                  AND candidate.snapshot_sha256=(
                      SELECT run.snapshot_sha256 FROM real_preview.source_preview_runs run
                      WHERE run.source_id='de.locations'
                      ORDER BY run.created_at DESC,run.run_id DESC LIMIT 1
                  )
                  AND candidate.display_latitude IS NOT NULL
                  AND EXISTS (
                      SELECT 1 FROM real_preview.geocode_display_evidence evidence
                      JOIN real_preview.germany_geocode_context_audit audit
                        ON audit.candidate_id=evidence.candidate_id
                       AND audit.snapshot_sha256=candidate.snapshot_sha256
                       AND audit.geocode_result_id=evidence.geocode_result_id
                       AND audit.outcome <> 'matched'
                      WHERE evidence.candidate_id=candidate.candidate_id
                        AND evidence.display_latitude=candidate.display_latitude
                        AND evidence.display_longitude=candidate.display_longitude
                        AND evidence.display_geometry_source=candidate.display_geometry_source
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM real_preview.geocode_display_evidence evidence
                      JOIN real_preview.germany_geocode_context_audit audit
                        ON audit.candidate_id=evidence.candidate_id
                       AND audit.snapshot_sha256=candidate.snapshot_sha256
                       AND audit.geocode_result_id=evidence.geocode_result_id
                       AND audit.outcome='matched'
                      WHERE evidence.candidate_id=candidate.candidate_id
                        AND evidence.display_latitude=candidate.display_latitude
                        AND evidence.display_longitude=candidate.display_longitude
                        AND evidence.display_geometry_source=candidate.display_geometry_source
                  )
            """).fetchone()[0]
            self.assertEqual(leaked, 0)

            cache_candidate = connection.execute("""
                SELECT candidate.candidate_id,evidence.display_latitude,evidence.display_longitude,
                       evidence.display_geometry_source,evidence.match_confidence
                FROM real_preview.candidates candidate
                JOIN real_preview.geocode_display_evidence evidence
                  ON evidence.candidate_id=candidate.candidate_id
                JOIN real_preview.germany_geocode_context_audit audit
                  ON audit.candidate_id=evidence.candidate_id
                 AND audit.snapshot_sha256=candidate.snapshot_sha256
                 AND audit.geocode_result_id=evidence.geocode_result_id
                 AND audit.outcome <> 'matched'
                WHERE candidate.source_id='de.locations'
                  AND candidate.location_class <> 'numeric_source_coordinate'
                  AND candidate.snapshot_sha256=(
                      SELECT run.snapshot_sha256 FROM real_preview.source_preview_runs run
                      WHERE run.source_id='de.locations'
                      ORDER BY run.created_at DESC,run.run_id DESC LIMIT 1
                  )
                  AND evidence.match_confidence IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1 FROM real_preview.local_reference_display_evidence local
                      WHERE local.candidate_id=candidate.candidate_id
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM real_preview.geocode_display_evidence other_evidence
                      JOIN real_preview.germany_geocode_context_audit matched
                        ON matched.candidate_id=other_evidence.candidate_id
                       AND matched.snapshot_sha256=candidate.snapshot_sha256
                       AND matched.geocode_result_id=other_evidence.geocode_result_id
                       AND matched.outcome='matched'
                      WHERE other_evidence.candidate_id=candidate.candidate_id
                        AND other_evidence.display_latitude=evidence.display_latitude
                        AND other_evidence.display_longitude=evidence.display_longitude
                        AND other_evidence.display_geometry_source=evidence.display_geometry_source
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM real_preview.germany_geocode_context_audit matched_candidate
                      WHERE matched_candidate.candidate_id=candidate.candidate_id
                        AND matched_candidate.snapshot_sha256=candidate.snapshot_sha256
                        AND matched_candidate.outcome='matched'
                  )
                ORDER BY evidence.created_at DESC,evidence.geocode_result_id DESC
                LIMIT 1
            """).fetchone()
            self.assertIsNotNone(cache_candidate)
            candidate_id, latitude, longitude, geometry_source, confidence = cache_candidate
            initial_cache = connection.execute("""
                SELECT display_latitude,display_longitude,display_geometry_source
                FROM real_preview.candidates WHERE candidate_id=%s
            """, (candidate_id,)).fetchone()
            self.assertEqual(initial_cache, (None, None, None))
            initial_view = connection.execute("""
                SELECT display_latitude,display_longitude,display_geometry_source
                FROM real_preview.candidate_display WHERE candidate_id=%s
            """, (candidate_id,)).fetchone()
            self.assertEqual(initial_view, (None, None, None))

            connection.execute("SAVEPOINT cache_alignment_case")
            try:
                # Recreate only a cache value backed by retained raw evidence,
                # then prove the narrow audited-clear exception can remove it.
                connection.execute("""
                    UPDATE real_preview.candidates
                    SET display_latitude=%s,display_longitude=%s,display_geometry_source=%s,
                        coordinate_method='geoapify_forward',coordinate_provider='Geoapify',
                        coordinate_confidence=%s,coordinate_confidence_band='high'
                    WHERE candidate_id=%s
                """, (latitude, longitude, geometry_source, confidence, candidate_id))
                connection.execute("""
                    UPDATE real_preview.candidates
                    SET display_latitude=NULL,display_longitude=NULL,display_geometry_source=NULL
                    WHERE candidate_id=%s
                """, (candidate_id,))
                repaired = connection.execute("""
                    SELECT candidate.display_latitude,candidate.display_longitude,candidate.display_geometry_source,
                           display.display_latitude,display.display_longitude,display.display_geometry_source
                    FROM real_preview.candidates candidate
                    JOIN real_preview.candidate_display display USING(candidate_id,snapshot_sha256)
                    WHERE candidate.candidate_id=%s
                """, (candidate_id,)).fetchone()
                self.assertEqual(repaired, (None, None, None, None, None, None))

                with self.assertRaises(psycopg.Error):
                    with connection.transaction():
                        connection.execute("""
                            UPDATE real_preview.candidates
                            SET city=COALESCE(city,'') || ' cache guard probe'
                            WHERE candidate_id=%s
                        """, (candidate_id,))
            finally:
                connection.execute("ROLLBACK TO SAVEPOINT cache_alignment_case")
                connection.execute("RELEASE SAVEPOINT cache_alignment_case")
        finally:
            connection.rollback()
            connection.close()


if __name__ == "__main__":
    unittest.main()
