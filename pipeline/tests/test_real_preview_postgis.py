"""Disposable PostGIS integration for the isolated preview migration."""

import os
import unittest
from pathlib import Path

import psycopg

MIGRATIONS = sorted((Path(__file__).parents[1] / "migrations").glob("*.sql"))
DATABASE_URL = os.environ.get("UEC_REAL_PREVIEW_TEST_DATABASE_URL")


@unittest.skipUnless(DATABASE_URL, "requires a dedicated disposable PostGIS test database")
class RealPreviewPostgisTests(unittest.TestCase):
    def test_private_rows_are_idempotent_and_stay_out_of_public_release_membership(self):
        with psycopg.connect(DATABASE_URL) as connection:
            database_name = connection.execute("SELECT current_database()").fetchone()[0]
            if not database_name.startswith("uec_real_preview_test"):
                self.fail("integration database must use the dedicated uec_real_preview_test prefix")
            extensions = connection.execute("SELECT extname FROM pg_extension WHERE extname='postgis'").fetchall()
            self.assertEqual(len(extensions), 1, "dedicated integration database must have PostGIS")
            with connection.transaction():
                for migration in MIGRATIONS:
                    connection.execute(migration.read_text(encoding="utf-8"))
                connection.execute("INSERT INTO real_preview.imports(snapshot_sha256,observation_count) VALUES (%s,3)", ("a" * 64,))
                row = ("a" * 64, "it.853-2004", "synthetic-source-key", "numeric_source_coordinate", True,
                       "IT", "Example", None, 44.1, 11.2, "numeric")
                insert = """INSERT INTO real_preview.observations
                    (snapshot_sha256,source_id,source_identifier,location_class,facility_candidate,country_code,city,postal_code,latitude,longitude,coordinate_precision)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING"""
                numeric_observation_id = connection.execute(insert + " RETURNING preview_id", row).fetchone()[0]
                connection.execute(insert, row)
                coarse_observation_id = connection.execute(insert + " RETURNING preview_id", ("a" * 64, "fr.dgal.section-i", "synthetic-coarse-key", "city_postal", True,
                    "FR", "Example", None, None, None, "city")).fetchone()[0]
                unmapped_observation_id = connection.execute(insert + " RETURNING preview_id", ("a" * 64, "us.fsis", "synthetic-private-key", "unmapped_private_observation", True,
                    "US", None, None, None, None, None)).fetchone()[0]
                candidate_insert = """INSERT INTO real_preview.candidates
                    (snapshot_sha256,source_id,source_group_key,representative_observation_id,location_class,country_code,city,latitude,longitude,observation_count,
                     display_name,activity_label,activity_source,evidence_summary,source_record_url,source_name,observed_at,default_map_scope,map_scope_reason)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,1,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING"""
                numeric_candidate = ("a" * 64, "it.853-2004", "source-group-1", numeric_observation_id, "numeric_source_coordinate", "IT", "Example", 44.1, 11.2,
                    "Synthetic Facility", "Meat processing", "source", "Synthetic evidence summary", "https://example.test/record", "Synthetic source", "2026-09-20T12:00:00Z", True, None)
                connection.execute(candidate_insert, numeric_candidate)
                connection.execute(candidate_insert, numeric_candidate)
                connection.execute(candidate_insert, ("a" * 64, "fr.dgal.section-i", "source-group-2", coarse_observation_id, "city_postal", "FR", "Example", None, None,
                    None, None, None, None, None, None, None, True, None))
                connection.execute(candidate_insert, ("a" * 64, "us.fsis", "source-group-3", unmapped_observation_id, "unmapped_private_observation", "US", None, None, None,
                    None, None, None, None, None, None, None, False, "general-food"))
                safe_fields = connection.execute("""
                    SELECT display_name,activity_label,activity_source,evidence_summary,source_record_url,source_name,observed_at
                    FROM real_preview.candidates WHERE source_group_key='source-group-1'
                """).fetchone()
                self.assertEqual(safe_fields[:6], ("Synthetic Facility", "Meat processing", "source", "Synthetic evidence summary", "https://example.test/record", "Synthetic source"))
                self.assertIsNotNone(safe_fields[6])
                with self.assertRaises(psycopg.Error):
                    with connection.transaction():
                        connection.execute(candidate_insert, ("a" * 64, "it.853-2004", "source-group-invalid-url", numeric_observation_id,
                            "numeric_source_coordinate", "IT", "Example", 44.1, 11.2, None, None, None, None,
                            "http://example.test/record", None, None, True, None))
                coarse_candidate_id = connection.execute(
                    "SELECT candidate_id FROM real_preview.candidates WHERE source_group_key='source-group-2'"
                ).fetchone()[0]
                connection.execute("""
                    INSERT INTO real_preview.local_reference_display_evidence
                      (candidate_id,snapshot_sha256,source_id,reference_latitude,reference_longitude,
                       display_precision,display_geometry_source,reference_source_id,reference_source)
                    VALUES (%s,%s,%s,48.8,2.3,'locality_reference_coarse',
                            'synthetic municipality reference; approximate, not facility coordinates',
                            'synthetic-ref-1','synthetic reference dataset')
                """, (coarse_candidate_id, "a" * 64, "fr.dgal.section-i"))
                display = connection.execute(
                    "SELECT display_latitude,display_longitude,display_geometry_source FROM real_preview.candidates WHERE candidate_id=%s",
                    (coarse_candidate_id,),
                ).fetchone()
                self.assertEqual(display[:2], (48.8, 2.3))
                self.assertIn("approximate", display[2])
                self.assertEqual(connection.execute(
                    "SELECT display_precision FROM real_preview.local_reference_display_evidence WHERE candidate_id=%s",
                    (coarse_candidate_id,),
                ).fetchone()[0], "locality_reference_coarse")
                with self.assertRaises(psycopg.Error):
                    with connection.transaction():
                        connection.execute(candidate_insert, ("a" * 64, "it.853-2004", "source-group-zero", numeric_observation_id, "numeric_source_coordinate", "IT", "Example", 0.0, 0.0,
                            None, None, None, None, None, None, None, True, None))
                self.assertEqual(connection.execute("SELECT count(*) FROM real_preview.observations").fetchone()[0], 3)
                self.assertEqual(connection.execute("SELECT count(*) FROM real_preview.observations WHERE facility_candidate").fetchone()[0], 3)
                self.assertEqual(connection.execute("SELECT count(*) FROM real_preview.observations WHERE location_class='unmapped_private_observation'").fetchone()[0], 1)
                self.assertEqual(connection.execute("SELECT count(*) FROM real_preview.candidates").fetchone()[0], 3)
                scope_counts = connection.execute("""
                    SELECT count(*) FILTER (WHERE default_map_scope),
                           count(*) FILTER (WHERE NOT default_map_scope),
                           count(*) FILTER (WHERE location_class='unmapped_private_observation'),
                           count(*) FILTER (WHERE default_map_scope AND location_class='numeric_source_coordinate')
                    FROM real_preview.candidates
                """).fetchone()
                self.assertEqual(scope_counts, (2, 1, 1, 1))
                self.assertEqual(connection.execute(
                    "SELECT map_scope_reason FROM real_preview.candidates WHERE source_group_key='source-group-3'"
                ).fetchone()[0], "general-food")
                for relation in (
                    "uec.release_members",
                    "uec.map_facilities_public_discovery",
                    "uec.map_facilities_public_discovery_read_model",
                    "uec.graph_public_relationships",
                    "uec.graph_public_claims",
                ):
                    if connection.execute("SELECT to_regclass(%s)", (relation,)).fetchone()[0]:
                        self.assertEqual(connection.execute(f"SELECT count(*) FROM {relation}").fetchone()[0], 0)
                public_preview = connection.execute("SELECT to_regclass('uec.real_preview_observations')").fetchone()[0]
                self.assertIsNone(public_preview)
                with self.assertRaises(psycopg.Error):
                    with connection.transaction():
                        connection.execute("UPDATE real_preview.observations SET city='Changed' WHERE source_identifier='synthetic-source-key'")
                with self.assertRaises(psycopg.Error):
                    with connection.transaction():
                        connection.execute("UPDATE real_preview.candidates SET city='Changed' WHERE source_group_key='source-group-1'")
            # The migration and all synthetic rows are rolled back with the disposable test transaction.
            connection.rollback()


if __name__ == "__main__":
    unittest.main()
