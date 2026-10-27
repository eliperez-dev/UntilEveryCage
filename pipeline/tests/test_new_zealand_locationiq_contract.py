"""Offline synthetic checks for the NZ LocationIQ SQL acceptance contract."""
import importlib.util
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

import psycopg

from pipeline.geocoding.private_profiles import profile_by_id, profile_for_source

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "pipeline/migrations/102_new_zealand_locationiq_private_enrichment.sql"
WORKER_SPEC = importlib.util.spec_from_file_location(
    "nz_locationiq_worker_test", ROOT / "pipeline/scripts/stages/geocode-worker.py")
WORKER = importlib.util.module_from_spec(WORKER_SPEC)
WORKER_SPEC.loader.exec_module(WORKER)


class NewZealandLocationIqContractTests(unittest.TestCase):
    def test_profile_is_explicitly_private_and_country_scoped(self):
        profile = profile_for_source("nz.locations", provider_id="locationiq")
        self.assertEqual(profile["profile_id"], "locationiq-nz-mpi-rmp")
        self.assertEqual(profile["country_code"], "NZ")
        self.assertEqual(profile["status"], "enabled-private-only")
        self.assertEqual(profile_by_id(profile["profile_id"]), profile)

    def test_worker_accepts_only_explicit_nz_profile_with_bounded_locationiq_limits(self):
        with patch.object(WORKER, "get_adapter"), \
             patch.object(WORKER.psycopg, "connect", side_effect=RuntimeError("no database")) as connect:
            with self.assertRaisesRegex(RuntimeError, "no database"):
                WORKER.run("postgresql://synthetic", "locationiq", 1, 0, 1,
                           private_source_profile_id="locationiq-nz-mpi-rmp",
                           daily_budget=5000, provider_interval=1.05)
        connect.assert_called_once()
        with patch.object(WORKER.psycopg, "connect") as connect:
            with self.assertRaises(ValueError):
                WORKER.run("postgresql://synthetic", "locationiq", 1, 0, 1,
                           private_source_profile_id="locationiq-unlisted", daily_budget=5000,
                           provider_interval=1.05)
        connect.assert_not_called()

    def test_migration_independently_requires_source_scope_restrictions_and_audit(self):
        sql = MIGRATION.read_text(encoding="utf-8")
        required = (
            "candidate.source_id='nz.locations'", "candidate.country_code='NZ'",
            "location.location_evidence->>'country_code'='NZ'",
            "location.location_evidence->>'number_of_locations'", "trim", "='1'",
            "candidate.snapshot_sha256=(SELECT run.snapshot_sha256",
            "ORDER BY run.created_at DESC,run.run_id DESC LIMIT 1",
            "NOT EXISTS (SELECT 1 FROM uec.public_access_restricted",
            "NOT EXISTS (SELECT 1 FROM real_preview.enrichment_state_events",
            "jsonb_array_elements(NEW.response->'results')",
            "ST_Y(NEW.result::geometry) <> (selected->>'lat')::DOUBLE PRECISION",
            "ST_X(NEW.result::geometry) <> (selected->>'lon')::DOUBLE PRECISION",
            "new_zealand_locationiq_context_audit", "outcome='matched'",
        )
        for fragment in required:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, sql)
        self.assertIn("latitude BETWEEN -47.5 AND -34.0", sql)
        self.assertIn("longitude BETWEEN 166 AND 179.9", sql)
        self.assertIn("jsonb_typeof(location.location_evidence->'location_count')='number'", sql)
        self.assertIn("location.location_evidence->>'location_count'='1'", sql)
        self.assertEqual(sql.count("trim(coalesce(location.location_evidence->>'number_of_locations',''))='1'"), 2)
        self.assertEqual(sql.count("jsonb_typeof(location.location_evidence->'location_count')='number'"), 2)
        self.assertEqual(sql.count("location.location_evidence->>'location_count'='1'"), 2)
        self.assertIn("'address','address_lines','city','postal_code','region','country_code','coordinates'", sql)
        self.assertIn("'number_of_locations','location_count'", sql)
        self.assertIn("source_id='nz.locations' OR NOT (location_evidence ?|", sql)
        self.assertIn("address->>'postcode'", sql)
        self.assertIn("NOT NULL", sql)  # Audit and source context remain fail-closed.
        self.assertNotRegex(sql, r"(?im)^\s*(UPDATE|DELETE|TRUNCATE)\s+real_preview\.(?:candidates|geocode_display_evidence)")

    def test_migration_requires_postcode_only_when_source_evidence_has_one(self):
        sql = MIGRATION.read_text(encoding="utf-8")
        self.assertIn("nullif(trim(location.location_evidence->>'postal_code'),'') IS NULL", sql)
        self.assertIn("OR location.location_evidence->>'postal_code' ~ '^[0-9]{4}$'", sql)
        self.assertIn("nullif(trim(postcode),'') IS NOT NULL", sql)
        self.assertIn("address->>'postcode','') <> trim(postcode)", sql)


@unittest.skipUnless(
    os.environ.get("UEC_NZ_LOCATIONIQ_SQL_TESTS") == "1"
    and urlsplit(os.environ.get("UEC_DATABASE_URL", "")).path.strip("/") == "uec_launch_sources_test_20261025",
    "explicit opt-in on the assigned disposable NZ SQL-test database required",
)
class NewZealandLocationIqSqlFunctionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.connection = psycopg.connect(os.environ["UEC_DATABASE_URL"])
        if cls.connection.execute("SELECT current_database()").fetchone()[0] != "uec_launch_sources_test_20261025":
            cls.connection.close()
            raise RuntimeError("wrong disposable database")
        present = cls.connection.execute(
            "SELECT to_regprocedure('real_preview.locationiq_new_zealand_address_matches(jsonb,text,text,text)')"
        ).fetchone()[0]
        if present is None:
            cls.connection.close()
            raise RuntimeError("NZ LocationIQ migration 102 must be applied before opt-in SQL tests")

    @classmethod
    def tearDownClass(cls):
        cls.connection.close()

    def matches(self, item, *, source_address="12 Lambton Quay", postcode=None, town="Wellington"):
        return self.connection.execute(
            "SELECT real_preview.locationiq_new_zealand_address_matches(%s::jsonb,%s,%s,%s)",
            (json.dumps(item), source_address, postcode, town),
        ).fetchone()[0]

    def test_sql_function_positive_optional_postcode_and_exact_address_town(self):
        result = {"lat": "-41.2865", "lon": "174.7762", "class": "building",
                  "type": "house", "address": {"road": "Lambton Quay", "house_number": "12",
                  "city": "Wellington", "postcode": "6011", "country_code": "nz"}}
        self.assertTrue(self.matches(result, postcode="6011"))
        self.assertTrue(self.matches(result))
        suburb_result = {**result, "address": {**result["address"], "city": "Wellington Region",
                                                "suburb": "Wellington"}}
        self.assertTrue(self.matches(suburb_result))
        address_node = {**result, "class": "place", "type": "house"}
        self.assertTrue(self.matches(address_node))
        self.assertFalse(self.matches({**address_node, "type": "houses"}))
        self.assertFalse(self.matches({**address_node, "type": "city"}))

    def test_sql_function_rejects_mismatched_components_and_off_bounds(self):
        base = {"lat": "-41.2865", "lon": "174.7762", "class": "building",
                "type": "house", "address": {"road": "Lambton Quay", "house_number": "12",
                "city": "Wellington", "postcode": "6011", "country_code": "nz"}}
        for field, value in (("country_code", "au"), ("road", "Other Road"),
                             ("house_number", "13"), ("city", "Lower Hutt"),
                             ("postcode", "6021")):
            with self.subTest(field=field):
                self.assertFalse(self.matches({**base, "address": {**base["address"], field: value}},
                                              postcode="6011"))
        self.assertFalse(self.matches({**base, "lat": "-33.9"}))
        self.assertFalse(self.matches({**base, "lon": "179.95"}))
        self.assertFalse(self.matches({**base, "lat": "NaN"}))


if __name__ == "__main__":
    unittest.main()
