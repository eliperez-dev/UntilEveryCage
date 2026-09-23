"""Disposable PostGIS integration for the isolated preview migration."""

import os
import unittest
from pathlib import Path

import psycopg

MIGRATION = Path(__file__).parents[1] / "migrations" / "045_real_preview_private.sql"
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
                connection.execute(MIGRATION.read_text(encoding="utf-8"))
                connection.execute("INSERT INTO real_preview.imports(snapshot_sha256,observation_count) VALUES (%s,3)", ("a" * 64,))
                row = ("a" * 64, "it.853-2004", "synthetic-source-key", "numeric_source_coordinate", True,
                       "IT", "Example", None, 44.1, 11.2, "numeric")
                insert = """INSERT INTO real_preview.observations
                    (snapshot_sha256,source_id,source_identifier,location_class,facility_candidate,country_code,city,postal_code,latitude,longitude,coordinate_precision)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING"""
                connection.execute(insert, row)
                connection.execute(insert, row)
                connection.execute(insert, ("a" * 64, "fr.dgal.section-i", "synthetic-coarse-key", "city_postal", True,
                    "FR", "Example", None, None, None, "city"))
                connection.execute(insert, ("a" * 64, "us.fsis", "synthetic-private-key", "unmapped_private_observation", False,
                    "US", None, None, None, None, None))
                self.assertEqual(connection.execute("SELECT count(*) FROM real_preview.observations").fetchone()[0], 3)
                self.assertEqual(connection.execute("SELECT count(*) FROM real_preview.observations WHERE facility_candidate").fetchone()[0], 2)
                self.assertEqual(connection.execute("SELECT count(*) FROM real_preview.observations WHERE location_class='unmapped_private_observation'").fetchone()[0], 1)
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
            # The migration and all synthetic rows are rolled back with the disposable test transaction.
            connection.rollback()


if __name__ == "__main__":
    unittest.main()
