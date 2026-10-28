"""Offline and opt-in SELECT-only checks for LocationIQ structured capture."""
from __future__ import annotations

import json
import os
from pathlib import Path
import unittest
from urllib.parse import urlsplit

import psycopg


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "pipeline/migrations/108_locationiq_structured_first_pass.sql"
DATABASE_NAME = "uec_launch_sources_test_20261025"


class LocationIqFirstPassMigrationContractTests(unittest.TestCase):
    def test_unverified_source_axes_do_not_discard_independent_address_matches(self):
        sql = (ROOT / "pipeline/migrations/109_first_pass_unverified_source_axes.sql").read_text(encoding="utf-8")
        self.assertIn("capture_locationiq_first_pass_private_display", sql)
        self.assertIn("CREATE TEMP TABLE uec_first_pass_109_replay", sql)
        self.assertIn("result.status='accepted'", sql)
        self.assertIn("EXECUTE replace(definition,old_guard,'')", sql)
        self.assertNotRegex(sql, r"(?im)^\s*(INSERT INTO|UPDATE|DELETE FROM)\s+uec\.(?:geocode_results|geocode_request_reservations|geocode_job_events)\b")

    def test_migration_is_private_scoped_and_preserves_existing_profile_space(self):
        sql = MIGRATION.read_text(encoding="utf-8")
        for fragment in (
            "to_regnamespace('real_preview') IS NULL",
            "private_geocoding_source_profiles_spain_profile_scope",
            "geoapify-es-aesan-rgseaa",
            "geoapify-es-aesan-verified-municipality",
            "locationiq-es-aesan-rgseaa",
            "locationiq-es-cat-feed-sandach",
            "locationiq-gb-fsa-approved-establishments",
            "locationiq-gb-fss-approved-establishments",
            "locationiq-nz-mpi-rmp",
            "uec-address-query-v1",
            "(SELECT count(*) FROM jsonb_object_keys(payload)) <> 6",
            "candidate.default_map_scope",
            "candidate.snapshot_sha256=COALESCE",
            "payload->>'locality'=verified.municipality",
            "NOT EXISTS (SELECT 1 FROM uec.public_access_restricted",
            "state.state_code='restricted'",
            "number_of_locations",
            "location_count",
            "locationiq_first_pass_address_matches",
            "viable_count <> 1",
            "locationiq_first_pass_context_audit",
            "geocode_display_evidence",
            "real preview evidence is append-only",
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, sql)
        self.assertIn("candidate.source_id='es.cat.feed-sandach'", sql)
        self.assertIn("profile.source_id=candidate.source_id", sql)
        self.assertIn("JOIN real_preview.geocode_targets target ON target.job_id=job.job_id", sql)
        self.assertIn("END LOOP;\n        RETURN NEW;", sql)
        self.assertNotIn("context_count <> 1", sql)
        self.assertIn("target.snapshot_sha256=candidate.snapshot_sha256", sql)
        self.assertIn("geometry_latitude <> selected_latitude", sql)
        self.assertIn("geometry_longitude <> selected_longitude", sql)
        self.assertNotRegex(sql, r"(?im)^\s*(UPDATE|DELETE|TRUNCATE)\s+(?:uec|real_preview)\.(?:source_records|geocode_results|geocode_display_evidence|candidates)\b")
        self.assertNotRegex(sql, r"(?im)^\s*(INSERT|UPDATE|DELETE)\s+uec\.(?:releases|release_members|publication_review_events)\b")


@unittest.skipUnless(
    os.environ.get("UEC_LOCATIONIQ_FIRST_PASS_SQL_TESTS") == "1"
    and urlsplit(os.environ.get("UEC_DATABASE_URL", "")).path.strip("/") == DATABASE_NAME,
    "opt-in SELECT-only matcher checks on the assigned disposable database required",
)
class LocationIqFirstPassPostgisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.connection = psycopg.connect(os.environ["UEC_DATABASE_URL"])
        if cls.connection.execute("SELECT current_database()").fetchone()[0] != DATABASE_NAME:
            cls.connection.close()
            raise RuntimeError("wrong disposable database")
        migration = cls.connection.execute(
            "SELECT count(*) FROM uec.schema_migrations WHERE version='108_locationiq_structured_first_pass'"
        ).fetchone()[0]
        function = cls.connection.execute(
            "SELECT to_regprocedure('real_preview.locationiq_first_pass_address_matches(jsonb,text,text,text,text,text)')"
        ).fetchone()[0]
        if migration != 1 or function is None:
            cls.connection.close()
            raise RuntimeError("LocationIQ first-pass migration 108 must be applied before opt-in checks")

    @classmethod
    def tearDownClass(cls):
        cls.connection.close()

    def matches(self, item, address, locality, postcode, region, country):
        row = self.connection.execute(
            "SELECT real_preview.locationiq_first_pass_address_matches(%s::jsonb,%s,%s,%s,%s,%s)",
            (json.dumps(item), address, locality, postcode, region, country),
        ).fetchone()
        return row[0]

    def test_es_accepts_exact_fragment_and_optional_source_context(self):
        item = {"lat": "40.4168", "lon": "-3.7038", "class": "building", "type": "house",
                "address": {"house_number": "4", "road": "Calle Example", "city": "Madrid",
                            "county": "Comunidad de Madrid", "postcode": "28001", "country_code": "es"}}
        self.assertTrue(self.matches(item, "Old Road, Calle Example 4, Unit 2", "Madrid",
                                     "28001", "Comunidad de Madrid", "ES"))
        self.assertTrue(self.matches(item, "Calle Example 4", "Madrid", None, None, "ES"))
        self.assertFalse(self.matches(item, "Calle Example", "Madrid", None, None, "ES"))
        self.assertFalse(self.matches(item, "Calle Example 4", "Madrid", "28002", None, "ES"))
        self.assertFalse(self.matches(item, "Calle Example 4", "Madrid", None, "Catalonia", "ES"))

    def test_gb_and_nz_matchers_check_source_fragments_country_and_bounds(self):
        gb = {"lat": "51.5074", "lon": "-0.1278", "class": "place", "type": "house",
              "address": {"house_number": "12", "road": "High Street", "city": "London",
                          "postcode": "SW1A1AA", "state": "Greater London", "country_code": "gb"}}
        self.assertTrue(self.matches(gb, "Unit 4, 12 High Street, Estate", "London",
                                     "SW1A 1AA", "Greater London", "GB"))
        self.assertTrue(self.matches(gb, "12 High Street", "", "SW1A 1AA", None, "GB"))
        self.assertFalse(self.matches(gb, "12 High Street", "", None, None, "GB"))
        self.assertFalse(self.matches(gb, "12 High Street", "Elsewhere", "SW1A 1AA", None, "GB"))
        self.assertFalse(self.matches({**gb, "type": "houses"}, "12 High Street", "London",
                                      "SW1A 1AA", None, "GB"))
        self.assertFalse(self.matches({**gb, "class": "highway", "type": "road"}, "12 High Street",
                                      "London", "SW1A 1AA", None, "GB"))
        nz = {"lat": "-41.2865", "lon": "174.7762", "class": "building", "type": "house",
              "address": {"house_number": "12", "road": "Sample Road", "city": "Wellington",
                          "country_code": "nz"}}
        self.assertTrue(self.matches(nz, "Unit 2, 12 Sample Road", "Wellington", None, None, "NZ"))
        self.assertFalse(self.matches({**nz, "lon": "179.95"}, "12 Sample Road", "Wellington",
                                      None, None, "NZ"))


if __name__ == "__main__":
    unittest.main()
