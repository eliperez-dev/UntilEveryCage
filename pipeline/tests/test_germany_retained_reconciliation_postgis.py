"""Rollback-only real-V0 acceptance of retained German response replay."""
import hashlib
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit
import uuid

import psycopg

from pipeline.geocoding import germany_retained_reconciliation as reconciliation
from pipeline.geocoding.german_streets import street_matches
from pipeline.scripts.release_baseline import load_contract, verify_connection

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "pipeline/migrations/100_germany_retained_geocode_reconciliation.sql"


@unittest.skipUnless(urlsplit(os.environ.get("UEC_DATABASE_URL", "")).path.strip("/")
                     == reconciliation.DATABASE, "assigned disposable real-data database required")
class RetainedGermanyPostgisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.connection = psycopg.connect(os.environ["UEC_DATABASE_URL"], autocommit=True)
        if cls.connection.execute("SELECT current_database()").fetchone()[0] != reconciliation.DATABASE:
            cls.connection.close()
            raise RuntimeError("wrong_disposable_database")
        cls.transaction = cls.connection.transaction(force_rollback=True)
        cls.transaction.__enter__()
        try:
            cls.connection.execute("SET LOCAL lock_timeout='5s'")
            cls.connection.execute("SET LOCAL statement_timeout='60s'")
            if cls.connection.execute("SELECT 1 FROM uec.schema_migrations WHERE version=%s",
                                      (MIGRATION.stem,)).fetchone() is None:
                cls.connection.execute(MIGRATION.read_text(encoding="utf-8"))
                cls.connection.execute("INSERT INTO uec.schema_migrations(version,sha256) VALUES(%s,%s)",
                    (MIGRATION.stem, hashlib.sha256(MIGRATION.read_bytes()).hexdigest()))
        except Exception:
            cls.transaction.__exit__(*__import__('sys').exc_info())
            cls.connection.close()
            raise

    @classmethod
    def tearDownClass(cls):
        cls.transaction.__exit__(None, None, None)
        cls.connection.close()

    def test_independent_sql_street_rule_matches_python(self):
        cases = [
            ("Lindenstr. 12", "Lindenstraße", "12"),
            ("12 Lindenstrasse", "Linden Straße", "12"),
            ("Mühlenstraße 12", "Muehlenstrasse", "12"),
            ("Mühlenstraße 12", "Muhlenstrasse", "12"),
            ("Lindenstr. 12a", "Lindenstraße", "12"),
            ("Lindenstr. 12/1", "Lindenstraße", "12-1"),
            ("12a Bahnhofstr.", "Bahnhofstraße", "12a"),
            ("12 Bahnhofstr. 13", "Bahnhofstraße", "12"),
            ("Lindenstr. 12", "Lindenweg", "12"),
        ]
        for source, road, house in cases:
            with self.subTest(source=source, road=road, house=house):
                actual = self.connection.execute(
                    "SELECT real_preview.locationiq_retained_street_matches_v1(%s,%s,%s)",
                    (source, road, house)).fetchone()[0]
                self.assertEqual(actual, street_matches(source, road, house))

    def test_real_replay_is_mapped_idempotent_and_does_not_rewrite_parent_results(self):
        connection = self.connection
        fingerprint_sql = """SELECT md5(COALESCE(string_agg(
            geocode_result_id::text || ':' || status || ':' || response::text,
            '|' ORDER BY geocode_result_id),''))
            FROM uec.geocode_results WHERE geocode_result_id=ANY(%s::uuid[])"""
        # Live workers may append new responses during this rollback-only test.
        # Check immutability of the fixed original cohort, not a changing table.
        parent_ids = [row[0] for row in connection.execute("""
            SELECT geocode_result_id FROM uec.geocode_results
            WHERE provider_id='locationiq' AND status='review_required'
        """).fetchall()]
        before = connection.execute(fingerprint_sql, (parent_ids,)).fetchone()[0]

        class ExistingConnection:
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def execute(self, *args, **kwargs): return connection.execute(*args, **kwargs)
            def transaction(self): return connection.transaction()

        with patch.object(reconciliation.psycopg, "connect", return_value=ExistingConnection()), \
             patch("urllib.request.urlopen", side_effect=AssertionError("network forbidden")), \
             patch("urllib.request.build_opener", side_effect=AssertionError("network forbidden")):
            result = reconciliation.reconcile(os.environ["UEC_DATABASE_URL"], limit=5000)
            repeated = reconciliation.reconcile(os.environ["UEC_DATABASE_URL"], limit=5000)
        # An already-reconciled copy can append zero; require actual persisted
        # lineage/evidence below rather than requiring new work on every run.
        self.assertEqual(result["database_rejected"], 0)
        self.assertEqual(result["provider_calls"], 0)
        self.assertEqual(repeated["appended"], 0)
        self.assertEqual(before, connection.execute(fingerprint_sql, (parent_ids,)).fetchone()[0])
        valid = connection.execute("""
            SELECT bool_and(parent.status='review_required'
                AND parent.query=child.query AND parent.queried_at=child.queried_at
                AND parent.attempt_number=child.attempt_number
                AND child.match_method=%s AND child.status='accepted'
                AND evidence.evidence_id IS NOT NULL AND audit.outcome='matched')
            FROM real_preview.germany_retained_geocode_reconciliations lineage
            JOIN uec.geocode_results parent ON parent.geocode_result_id=lineage.parent_geocode_result_id
            JOIN uec.geocode_results child ON child.geocode_result_id=lineage.derived_geocode_result_id
            LEFT JOIN real_preview.geocode_display_evidence evidence
                ON evidence.candidate_id=lineage.candidate_id
               AND evidence.geocode_result_id=lineage.derived_geocode_result_id
            LEFT JOIN real_preview.germany_geocode_context_audit audit
                ON audit.candidate_id=lineage.candidate_id
               AND audit.geocode_result_id=lineage.derived_geocode_result_id
        """, (reconciliation.MATCH_METHOD,)).fetchone()[0]
        self.assertIs(valid, True)
        # A forged derived row without its immutable parent link cannot persist.
        with self.assertRaises(psycopg.errors.CheckViolation):
            with connection.transaction():
                connection.execute("""
                    INSERT INTO uec.geocode_results
                    SELECT %s,source_record_id,provider_id,provider_version,query,
                           provider_address_id,result,precision,match_method,status,
                           attempt_number,retryable,response,queried_at
                    FROM uec.geocode_results WHERE match_method=%s LIMIT 1
                """, (uuid.uuid4(), reconciliation.MATCH_METHOD))
        self.assertEqual(verify_connection(connection, load_contract(
            ROOT / "pipeline/contracts/development-baseline.json"))["status"], "verified")


if __name__ == "__main__":
    unittest.main()
