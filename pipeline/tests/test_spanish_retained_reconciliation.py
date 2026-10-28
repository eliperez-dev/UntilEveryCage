"""Offline recovery tests plus opt-in, rollback-only local PostGIS checks."""
from __future__ import annotations

import copy
import json
import os
import unittest
import uuid
from unittest.mock import patch
from urllib.parse import urlsplit

import psycopg

from pipeline.geocoding import spanish_addresses as s
from pipeline.geocoding import spanish_retained_reconciliation as recovery
from pipeline.tests import test_locationiq_first_pass as f


class SpanishRetainedReplayTests(unittest.TestCase):
    def test_offline_replay_is_append_ready_and_does_not_mutate_parent(self):
        retained = {"results": [f.candidate()]}
        original = copy.deepcopy(retained)
        with patch("urllib.request.urlopen", side_effect=AssertionError("network forbidden")):
            response = recovery.replay(f.query("C/ Example, 4"), retained)
        self.assertIsNotNone(response)
        self.assertEqual(response["_uec_selected_result_index"], 0)
        self.assertEqual(retained, original)
        parent = uuid.UUID(int=42)
        self.assertEqual(recovery.result_id(parent), recovery.result_id(parent))
        self.assertNotEqual(recovery.result_id(parent), parent)

    def test_replay_rejects_empty_ambiguous_or_conflicting_evidence(self):
        for response in (None, {}, {"results": []},
                         {"results": [f.candidate(), f.candidate(place_id=43)]},
                         {"results": [f.candidate(address={**f.candidate()["address"], "house_number": "5"})]}):
            self.assertIsNone(recovery.replay(f.query("C/ Example, 4"), response))


@unittest.skipUnless(
    os.environ.get("UEC_SPANISH_REPLAY_SQL_TESTS") == "1"
    and urlsplit(os.environ.get("UEC_DATABASE_URL", "")).path.strip("/") == recovery.DATABASE,
    "opt-in local disposable database required",
)
class SpanishRetainedPostgisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.connection = psycopg.connect(os.environ["UEC_DATABASE_URL"])
        if cls.connection.execute("SELECT current_database()").fetchone()[0] != recovery.DATABASE:
            raise RuntimeError("wrong disposable database")

    @classmethod
    def tearDownClass(cls):
        cls.connection.close()

    def test_street_format_and_administrative_parity(self):
        for source in ("C/ Example, 4", "Calle Example 4 Nave 2", "4 Calle Example",
                       "Calle Example", "Calle Other 4", "Avenida Example 4",
                       "Calle Example 4-6", "Calle Example 4A"):
            expected = s.street_matches(source, "Calle Example", "4")
            actual = self.connection.execute("SELECT real_preview.spanish_street_matches(%s,%s,%s)",
                (source, "Calle Example", "4")).fetchone()[0]
            self.assertEqual(actual, expected)
        for region in ("Madrid", "Comunidad de Madrid", "Girona", "Andalucía", "Unknown"):
            for address in ({"state": "Cataluña", "state_code": "CT"},
                            {"province": "Girona"}, {"state": "Andalucía"},
                            {"province": "Barcelona", "state": "Catalonia"},
                            {"state": "Catalonia", "state_code": "MD"},
                            {"postcode": "28001"}):
                expected = s.province_matches(address, region, "28001")
                actual = self.connection.execute("SELECT real_preview.spanish_admin_matches(%s::jsonb,%s)",
                    (json.dumps(address), region)).fetchone()[0]
                self.assertEqual(actual, expected)

    def test_reference_region_and_province_alias_parity(self):
        for aliases, provinces in s.REGIONS:
            for alias in aliases:
                actual = self.connection.execute("SELECT real_preview.spanish_region_members(%s)", (alias,)).fetchone()[0]
                self.assertEqual(set(actual), set(provinces.split()))

    def test_real_parent_capture_and_forged_parent_are_rollback_only(self):
        rows = self.connection.execute("""
            SELECT DISTINCT result.geocode_result_id,result.source_record_id,result.query,
                   result.attempt_number,result.queried_at,result.response,target.candidate_id
            FROM uec.geocode_results result JOIN uec.geocode_jobs job
              ON job.source_record_id=result.source_record_id AND job.query=result.query
             AND job.provider_id=result.provider_id
            JOIN real_preview.geocode_targets target USING(job_id)
            WHERE result.provider_id='locationiq' AND result.match_method='locationiq_forward'
              AND result.status='review_required'
              AND target.source_id IN ('es.locations','es.cat.feed-sandach')
            ORDER BY result.geocode_result_id
        """).fetchall()
        matches = [(*row, response) for row in rows
                   if (response := recovery.replay(row[2], row[5])) is not None][:2]
        self.assertEqual(len(matches), 2, "real retained matching parents required")
        for parent, record, query, attempt, date, original, candidate, response in matches:
            with self.connection.transaction(force_rollback=True):
                recovery.append_evaluation(self.connection, parent_id=parent, source_record_id=record,
                    query=query, attempt=attempt, queried_at=date, response=response, candidate_ids=[candidate])
            with self.connection.transaction(force_rollback=True):
                with self.assertRaises(ValueError):
                    recovery.append_evaluation(self.connection, parent_id=parent, source_record_id=record,
                        query=query, attempt=attempt, queried_at=date, response=response,
                        candidate_ids=[uuid.UUID(int=99)])
            with self.connection.transaction(force_rollback=True):
                with self.assertRaises(psycopg.errors.CheckViolation):
                    recovery.append_evaluation(self.connection, parent_id=uuid.UUID(int=9),
                        source_record_id=record, query=query, attempt=attempt, queried_at=date,
                        response=response, candidate_ids=[candidate])
            changed = copy.deepcopy(response)
            selected = changed["results"][changed["_uec_selected_result_index"]]
            selected["address"]["house_number"] = "999999"
            with self.connection.transaction(force_rollback=True):
                with self.assertRaises(psycopg.errors.CheckViolation):
                    recovery.append_evaluation(self.connection, parent_id=parent, source_record_id=record,
                        query=query, attempt=attempt, queried_at=date, response=changed, candidate_ids=[candidate])


if __name__ == "__main__":
    unittest.main()
