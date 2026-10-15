"""Opt-in disposable PostGIS proof for APHIS mailing-locality display fan-out.

Run only with ``UEC_APHIS_POSTGIS_TEST_DATABASE_URL`` pointing at an isolated
database.  The test derives a same-locality pair from that disposable copy and
never prints IDs, location values, queries, or provider payloads.
"""
from __future__ import annotations

import json
import os
import unittest
import uuid

import psycopg


PROFILE_ID = "geoapify-us-aphis-mailing-locality"


class AphisMailingLocalityPostgisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database_url = os.environ.get("UEC_APHIS_POSTGIS_TEST_DATABASE_URL")
        if not cls.database_url:
            raise unittest.SkipTest("set UEC_APHIS_POSTGIS_TEST_DATABASE_URL for the disposable PostGIS gate")
        cls.connection = psycopg.connect(cls.database_url)
        database = cls.connection.execute("SELECT current_database()").fetchone()[0]
        if not database.startswith("uec_aphis_gate_"):
            raise RuntimeError("APHIS PostGIS gate requires a named disposable database")

    @classmethod
    def tearDownClass(cls):
        cls.connection.close()

    def test_accepted_city_fans_out_only_to_exact_us_mailing_locality_targets(self):
        with self.connection.transaction():
            pair = self.connection.execute("""
                WITH latest AS (
                    SELECT snapshot_sha256 FROM real_preview.source_preview_runs
                     WHERE source_id='us.aphis' ORDER BY created_at DESC,run_id DESC LIMIT 1
                ) SELECT array_agg(candidate_id ORDER BY candidate_id), min(snapshot_sha256)
                    FROM (
                        SELECT c.candidate_id,c.snapshot_sha256
                          FROM real_preview.candidates c JOIN latest USING(snapshot_sha256)
                         WHERE c.source_id='us.aphis' AND c.country_code='US'
                         ORDER BY c.candidate_id LIMIT 2
                    ) selected
            """).fetchone()
            self.assertIsNotNone(pair[0], "disposable APHIS fixture needs two latest candidates")
            candidate_ids, snapshot_sha256 = pair
            self.assertEqual(len(candidate_ids), 2)
            city, state = "Synthetic Gate City", "TX"
            self.connection.execute("SET LOCAL session_replication_role = replica")
            for candidate_id in candidate_ids:
                self.connection.execute("""
                    UPDATE real_preview.candidate_private_location_evidence
                       SET location_evidence=jsonb_set(
                           jsonb_set(location_evidence,'{city}',to_jsonb(%s::text),true),
                           '{region}',to_jsonb(%s::text),true)
                     WHERE candidate_id=%s
                """, (city, state, candidate_id))
            self.connection.execute("SET LOCAL session_replication_role = origin")
            source_record_id = self.connection.execute("""
                SELECT source_record_id FROM uec.source_records
                 WHERE source_id='us.aphis' ORDER BY parsed_at DESC NULLS LAST LIMIT 1
            """).fetchone()[0]
            query = ", ".join((city, state, "United States"))
            job_id = self.connection.execute("""
                INSERT INTO uec.geocode_jobs(source_record_id,provider_id,query)
                VALUES (%s,'geoapify',%s) RETURNING job_id
            """, (source_record_id, query)).fetchone()[0]
            self.connection.execute("""
                INSERT INTO uec.geocode_job_events(job_id,event_type,attempt_number,retryable,details)
                VALUES (%s,'queued',1,false,%s::jsonb)
            """, (job_id, json.dumps({"processing_mode": "private_geoapify_source_profile", "profile_id": PROFILE_ID})))
            for candidate_id in candidate_ids:
                self.connection.execute("""
                    INSERT INTO real_preview.geocode_targets(job_id,candidate_id,snapshot_sha256,source_id,source_record_key)
                    SELECT %s,candidate_id,%s,source_id,source_group_key
                      FROM real_preview.candidates WHERE candidate_id=%s
                """, (job_id, snapshot_sha256, candidate_id))

            def record(properties):
                result_id = uuid.uuid4()
                response = {"_uec_selected_feature_index": 0, "features": [{
                    "geometry": {"type": "Point", "coordinates": [-90.0, 35.0]},
                    "properties": properties,
                }]}
                self.connection.execute("""
                    INSERT INTO uec.geocode_results(
                        geocode_result_id,source_record_id,provider_id,query,provider_address_id,
                        result,precision,match_method,status,attempt_number,retryable,response,queried_at
                    ) VALUES (
                        %s,%s,'geoapify',%s,'synthetic-gate',
                        ST_SetSRID(ST_MakePoint(-90.0,35.0),4326)::geography,
                        'geoapify_locality_point','private_source_profile','accepted',1,false,%s::jsonb,now()
                    )
                """, (result_id, source_record_id, query, json.dumps(response)))
                return self.connection.execute("""
                    SELECT count(*) FROM real_preview.geocode_display_evidence
                     WHERE geocode_result_id=%s
                """, (result_id,)).fetchone()[0]

            accepted = {"result_type": "city", "country_code": "US", "city": city,
                        "state_code": state, "rank": {"confidence": 0.95}}
            self.assertEqual(record(accepted), 2)
            self.assertEqual(record({**accepted, "result_type": "building"}), 0)
            self.assertEqual(record({**accepted, "city": "wrong locality"}), 0)
            self.assertEqual(record({**accepted, "state_code": "ZZ"}), 0)
            self.assertEqual(record({**accepted, "country_code": "CA"}), 0)
            self.connection.execute("""INSERT INTO uec.record_access_events
                (source_record_id,action,reason_category,policy_version,maintainer,note)
                VALUES (%s,'public_access_revoked','privacy','aphis-gate-test','test','synthetic gate')""",
                (source_record_id,))
            self.assertEqual(record(accepted), 0)


if __name__ == "__main__":
    unittest.main()
