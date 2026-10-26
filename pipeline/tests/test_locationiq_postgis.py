"""Real-v0 baseline plus rollback-only LocationIQ schema and matching checks."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

import psycopg

from pipeline.scripts.release_baseline import load_contract, verify_connection

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "pipeline/migrations/098_locationiq_private_enrichment.sql"


@unittest.skipUnless(urlsplit(os.environ.get("UEC_DATABASE_URL", "")).path.strip("/") == "uec_launch_sources_test_20261025",
                     "assigned disposable real-data database required")
class LocationIqPostgisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.connection = psycopg.connect(os.environ["UEC_DATABASE_URL"],autocommit=True)
        if cls.connection.execute("SELECT current_database()").fetchone()[0] != "uec_launch_sources_test_20261025":
            cls.connection.close()
            raise RuntimeError("wrong disposable database")
        cls.transaction = cls.connection.transaction(force_rollback=True)
        cls.transaction.__enter__()
        try:
            if cls.connection.execute("SELECT 1 FROM uec.schema_migrations WHERE version=%s",(MIGRATION.stem,)).fetchone() is None:
                cls.connection.execute(MIGRATION.read_text(encoding="utf-8"))
                cls.connection.execute("INSERT INTO uec.schema_migrations(version,sha256) VALUES(%s,%s)",
                                       (MIGRATION.stem,hashlib.sha256(MIGRATION.read_bytes()).hexdigest()))
        except Exception:
            cls.transaction.__exit__(*__import__('sys').exc_info())
            cls.connection.close()
            raise

    @classmethod
    def tearDownClass(cls):
        cls.transaction.__exit__(None,None,None)
        cls.connection.close()

    def test_approved_v0_identity_and_counts_are_unchanged(self):
        result = verify_connection(self.connection,load_contract(ROOT / "pipeline/contracts/development-baseline.json"))
        self.assertEqual(result["status"],"verified")

    def test_database_rechecks_address_components_and_rejects_bad_points(self):
        base = {"lat":"52.5","lon":"13.4","class":"building","type":"house","address":{
            "road":"Musterstraße","house_number":"12","postcode":"12345","city":"Berlin","state_code":"BE","country_code":"de"}}
        def matches(row):
            return self.connection.execute("SELECT real_preview.locationiq_germany_address_matches(%s::jsonb,%s,%s,%s,%s)",
                (json.dumps(row),"Musterstraße 12","12345","Berlin","BE")).fetchone()[0]
        self.assertTrue(matches(base))
        for field,value in (("postcode","54321"),("city","Potsdam"),("state_code","BB"),("country_code","at"),
                            ("house_number","13"),("road","Other Road")):
            with self.subTest(field=field):
                self.assertFalse(matches({**base,"address":{**base["address"],field:value}}))
        for row in ({**base,"lat":"NaN"},{**base,"lon":"999"},{**base,"lat":True},
                    {**base,"lat":"not-a-number"},{**base,"type":"road"},{**base,"class":"landuse"}):
            with self.subTest(row_type=row.get("type")):
                self.assertFalse(matches(row))
        self.assertFalse(matches({**base,"address":{**base["address"],"state":"Bayern"}}))

    def test_both_provider_profiles_coexist_without_changing_default(self):
        rows = self.connection.execute("SELECT provider_id,profile_id FROM real_preview.private_geocoding_source_profiles WHERE source_id='de.locations' ORDER BY provider_id").fetchall()
        self.assertEqual(rows,[("geoapify","geoapify-de-bltu"),("locationiq","locationiq-de-bltu")])

    def test_real_unmapped_batch_can_be_staged_without_provider_calls_or_persistent_writes(self):
        budget = self.connection.execute("SELECT reserved_requests >= daily_limit FROM uec.geocode_provider_budgets WHERE provider_id='geoapify' AND budget_date=(now() AT TIME ZONE 'UTC')::date").fetchone()
        if not budget or not budget[0]:
            self.skipTest("primary allowance is not exhausted")
        spec = importlib.util.spec_from_file_location("locationiq_activation_test", ROOT / "pipeline/scripts/stages/activate-locationiq-preview.py")
        activation = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(activation)
        connection = self.connection
        class RollbackConnection:
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def execute(self,*args,**kwargs): return connection.execute(*args,**kwargs)
            def transaction(self): return connection.transaction(force_rollback=True)
        before = self.connection.execute("SELECT count(*) FROM uec.geocode_jobs WHERE provider_id='locationiq'").fetchone()[0]
        with patch.object(activation.psycopg,"connect",return_value=RollbackConnection()):
            summary, jobs = activation.activate(os.environ["UEC_DATABASE_URL"],limit=24)
        self.assertEqual(summary["jobs_staged"]+summary["invalid_query_formats_skipped"],24)
        self.assertGreater(summary["jobs_staged"],0)
        self.assertEqual(summary["provider_calls"],0)
        self.assertEqual(len(set(jobs)),summary["jobs_staged"])
        after = self.connection.execute("SELECT count(*) FROM uec.geocode_jobs WHERE provider_id='locationiq'").fetchone()[0]
        self.assertEqual(before,after)


if __name__ == "__main__":
    unittest.main()
