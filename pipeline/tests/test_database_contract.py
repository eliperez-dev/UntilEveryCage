import os
import unittest
import uuid

import psycopg


DATABASE_URL = os.environ.get(
    "UEC_DATABASE_URL",
    "postgresql://uec:uec-local-development-only@localhost:5433/uec",
)


class DatabaseContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.connection = psycopg.connect(DATABASE_URL)
        except psycopg.Error as error:
            raise unittest.SkipTest(f"PostGIS is unavailable: {error}")

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "connection"):
            cls.connection.close()

    def test_repeated_geocode_attempts_are_preserved(self):
        source_id = f"test.contract.{uuid.uuid4().hex}"
        artifact_id = uuid.uuid4()
        record_id = uuid.uuid4()
        with self.connection.transaction():
            self.connection.execute(
                "INSERT INTO uec.sources (source_id, country_code, name, official_url, access_method) VALUES (%s, 'DK', 'Test', 'https://example.invalid', 'test')",
                (source_id,),
            )
            self.connection.execute(
                "INSERT INTO uec.raw_artifacts (artifact_id, storage_key, sha256, byte_size, retrieved_at) VALUES (%s, 'test/contract', %s, 1, now())",
                (artifact_id, uuid.uuid4().hex + uuid.uuid4().hex),
            )
            self.connection.execute(
                "INSERT INTO uec.source_records (source_record_id, source_id, source_record_key, artifact_id, raw_fields, parsed_at) VALUES (%s, %s, 'record-1', %s, '{}'::jsonb, now())",
                (record_id, source_id, artifact_id),
            )
            for attempt, status in ((1, "failed"), (2, "unresolved")):
                self.connection.execute(
                    "INSERT INTO uec.geocode_results (source_record_id, provider_id, query, match_method, status, attempt_number, queried_at) VALUES (%s, 'test-geocoder', 'Example 1', 'address', %s, %s, now())",
                    (record_id, status, attempt),
                )
            count = self.connection.execute(
                "SELECT count(*) FROM uec.geocode_results WHERE source_record_id = %s",
                (record_id,),
            ).fetchone()[0]
            self.assertEqual(count, 2)

    def test_evidence_update_and_delete_are_rejected(self):
        with self.connection.transaction():
            with self.assertRaises(psycopg.Error) as update_error:
                with self.connection.transaction():
                    self.connection.execute("UPDATE uec.source_records SET raw_fields = raw_fields WHERE source_record_id = (SELECT source_record_id FROM uec.source_records LIMIT 1)")
            self.assertEqual(update_error.exception.sqlstate, "55006")

            with self.assertRaises(psycopg.Error) as delete_error:
                with self.connection.transaction():
                    self.connection.execute("DELETE FROM uec.geocode_results")
            self.assertEqual(delete_error.exception.sqlstate, "55006")

    def test_geocode_job_state_is_event_sourced(self):
        source_record_id = self.connection.execute(
            "SELECT source_record_id FROM uec.source_records s WHERE NOT EXISTS (SELECT 1 FROM uec.record_access_events e WHERE e.source_record_id = s.source_record_id) LIMIT 1"
        ).fetchone()[0]
        with self.connection.transaction():
            job_id = self.connection.execute(
                "INSERT INTO uec.geocode_jobs (source_record_id, provider_id, query) VALUES (%s, 'test-geocoder', %s) RETURNING job_id",
                (source_record_id, f"test query {uuid.uuid4().hex}"),
            ).fetchone()[0]
            self.connection.execute(
                "INSERT INTO uec.geocode_job_events (job_id, event_type, attempt_number, occurred_at) VALUES (%s, 'queued', 1, now() - interval '2 seconds'), (%s, 'started', 1, now() - interval '1 second'), (%s, 'unresolved', 1, now())",
                (job_id, job_id, job_id),
            )
            current = self.connection.execute(
                "SELECT event_type FROM uec.geocode_job_current WHERE job_id = %s",
                (job_id,),
            ).fetchone()[0]
            self.assertEqual(current, "unresolved")

    def test_map_projection_is_read_only_and_requires_accepted_geocode(self):
        relation = self.connection.execute(
            "SELECT relkind FROM pg_class WHERE oid = 'uec.map_facilities_current'::regclass"
        ).fetchone()[0]
        self.assertEqual(relation, "v")
        columns = self.connection.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_schema = 'uec' AND table_name = 'map_facilities_current'"
        ).fetchall()
        self.assertIn(("geocoded_location",), columns)
        release_relation = self.connection.execute(
            "SELECT relkind FROM pg_class WHERE oid = 'uec.map_facilities_release'::regclass"
        ).fetchone()[0]
        self.assertEqual(release_relation, "v")
        public_relation = self.connection.execute(
            "SELECT relkind FROM pg_class WHERE oid = 'uec.map_facilities_public'::regclass"
        ).fetchone()[0]
        self.assertEqual(public_relation, "v")
        self.assertEqual(
            self.connection.execute("SELECT count(*) FROM uec.map_facilities_public").fetchone()[0],
            0,
        )
        display_relation = self.connection.execute(
            "SELECT relkind FROM pg_class WHERE oid = 'uec.map_facilities_display'::regclass"
        ).fetchone()[0]
        self.assertEqual(display_relation, "v")
        for view in ("uec.facility_observation_summary", "uec.facility_lifecycle_current"):
            self.assertEqual(self.connection.execute("SELECT relkind FROM pg_class WHERE oid = %s::regclass", (view,)).fetchone()[0], "v")
        history_columns = {row[0] for row in self.connection.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='uec' AND table_name='map_facilities_display_history'").fetchall()}
        self.assertTrue({"first_observed_at", "last_observed_at", "observation_count", "lifecycle_status"}.issubset(history_columns))

    def test_lifecycle_events_are_append_only_and_do_not_infer_closure(self):
        facility_id = self.connection.execute("SELECT facility_id FROM uec.facilities LIMIT 1").fetchone()[0]
        with self.connection.transaction():
            self.connection.execute("""
                INSERT INTO uec.facility_lifecycle_events
                (facility_id, status, effective_at, evidence_note)
                VALUES (%s, 'explicitly_closed', now(), 'Official closure notice, test fixture')
            """, (facility_id,))
            self.assertEqual(self.connection.execute("SELECT status FROM uec.facility_lifecycle_current WHERE facility_id=%s", (facility_id,)).fetchone()[0], "explicitly_closed")
            with self.assertRaises(psycopg.Error) as error:
                with self.connection.transaction():
                    self.connection.execute("DELETE FROM uec.facility_lifecycle_events")
            self.assertEqual(error.exception.sqlstate, "55006")

    def test_all_lifecycle_states_and_latest_transition_are_supported(self):
        facility_id = self.connection.execute("SELECT facility_id FROM uec.facilities LIMIT 1").fetchone()[0]
        states = ("active_observed", "not_seen_recently", "status_unknown", "explicitly_closed")
        with self.connection.transaction():
            for index, state in enumerate(states):
                self.connection.execute("""
                    INSERT INTO uec.facility_lifecycle_events
                    (facility_id, status, effective_at, evidence_note, created_at)
                    VALUES (%s, %s, now() + (%s || ' seconds')::interval,
                            %s, now() + (%s || ' seconds')::interval)
                """, (facility_id, state, index, f"Evidence for {state}", index))
            current = self.connection.execute(
                "SELECT status FROM uec.facility_lifecycle_current WHERE facility_id = %s",
                (facility_id,),
            ).fetchone()[0]
            self.assertEqual(current, "explicitly_closed")
            with self.assertRaises(psycopg.Error):
                with self.connection.transaction():
                    self.connection.execute("INSERT INTO uec.facility_lifecycle_events (facility_id, status, evidence_note) VALUES (%s, 'invalid', 'bad')", (facility_id,))

    def test_review_geocode_uses_city_reference_for_display_only(self):
        row = self.connection.execute("""
            SELECT m.release_id, m.observation_id, m.facility_id, o.source_record_id,
                   f.city, f.country_code
            FROM uec.release_members m
            JOIN uec.observations o ON o.observation_id = m.observation_id
            JOIN uec.facilities f ON f.facility_id = m.facility_id
            WHERE m.default_visible = true AND f.city IS NOT NULL AND btrim(f.city) <> ''
            LIMIT 1
        """).fetchone()
        original_release_id, observation_id, facility_id, source_record_id, city, country = row
        with self.connection.transaction():
            release_id = f'test-display-{uuid.uuid4().hex}'
            self.connection.execute("INSERT INTO uec.releases (release_id, status, ruleset_version, profile, summary) VALUES (%s, 'promoted', 'test-v1', 'secondary', '{}'::jsonb)", (release_id,))
            self.connection.execute("INSERT INTO uec.release_members (release_id, facility_id, observation_id, default_visible) VALUES (%s, %s, %s, true)", (release_id, facility_id, observation_id))
            self.connection.execute("""
                INSERT INTO uec.city_reference_points
                (country_code, city_name, reference_location, reference_source,
                 source_retrieved_at, source_reference_id)
                VALUES (%s, %s, ST_SetSRID(ST_MakePoint(10, 55), 4326)::geography,
                        %s, now(), %s)
                ON CONFLICT DO NOTHING
            """, (country, city, "https://example.invalid/cities", uuid.uuid4().hex))
            self.connection.execute("""
                INSERT INTO uec.geocode_results
                (source_record_id, provider_id, query, match_method, status,
                 attempt_number, queried_at, response)
                VALUES (%s, %s, %s, 'address', 'review_required', 999, now(), '{}'::jsonb)
            """, (source_record_id, "test-display", f"{city} test"))
            display = self.connection.execute("""
                SELECT ST_X(display_location::geometry), ST_Y(display_location::geometry), display_precision
                FROM uec.map_facilities_display_base
                WHERE release_id = %s AND observation_id = %s
            """, (release_id, observation_id)).fetchone()
            self.assertEqual(display[2], "city")
            self.assertAlmostEqual(display[0], 10)
            self.assertAlmostEqual(display[1], 55)

    def test_safety_restriction_is_auditable_without_mutating_evidence(self):
        source_record_id = self.connection.execute(
            "SELECT source_record_id FROM uec.source_records s WHERE NOT EXISTS (SELECT 1 FROM uec.record_access_events e WHERE e.source_record_id = s.source_record_id) LIMIT 1"
        ).fetchone()[0]
        original = self.connection.execute(
            "SELECT raw_fields FROM uec.source_records WHERE source_record_id = %s",
            (source_record_id,),
        ).fetchone()[0]
        with self.connection.transaction():
            self.connection.execute("""
                INSERT INTO uec.record_access_events
                (source_record_id, action, reason_category, policy_version, maintainer, note)
                VALUES (%s, 'public_access_revoked', 'privacy', 'ethics-v1', 'test-maintainer', 'test only')
            """, (source_record_id,))
            current = self.connection.execute(
                "SELECT action, reason_category, policy_version FROM uec.record_access_current WHERE source_record_id = %s",
                (source_record_id,),
            ).fetchone()
            self.assertEqual(current, ("public_access_revoked", "privacy", "ethics-v1"))
            self.assertEqual(
                self.connection.execute("SELECT raw_fields FROM uec.source_records WHERE source_record_id = %s", (source_record_id,)).fetchone()[0],
                original,
            )

    def test_restricted_record_is_excluded_from_public_map_projection(self):
        row = self.connection.execute("""
            SELECT m.release_id, o.source_record_id
            FROM uec.release_members m
            JOIN uec.facilities f ON f.facility_id = m.facility_id
            JOIN uec.observations o ON o.observation_id = m.observation_id
            WHERE m.default_visible = true AND f.city IS NOT NULL AND btrim(f.city) <> ''
            LIMIT 1
        """).fetchone()
        release_id, source_record_id = row
        with self.connection.transaction():
            self.connection.execute("UPDATE uec.releases SET status = 'promoted' WHERE release_id = %s", (release_id,))
            before = self.connection.execute(
                "SELECT count(*) FROM uec.map_facilities_release WHERE release_id = %s AND source_record_id = %s",
                (release_id, source_record_id),
            ).fetchone()[0]
            self.assertEqual(before, 1)
            self.connection.execute("""
                INSERT INTO uec.record_access_events
                (source_record_id, action, reason_category, policy_version, maintainer, occurred_at)
                VALUES (%s, 'public_access_revoked', 'safety', 'ethics-v1', 'test-maintainer', now() + interval '2 seconds')
            """, (source_record_id,))
            after = self.connection.execute(
                "SELECT count(*) FROM uec.map_facilities_public WHERE source_record_id = %s",
                (source_record_id,),
            ).fetchone()[0]
            self.assertEqual(after, 0)

    def test_access_can_only_be_restored_by_a_new_explicit_event(self):
        source_record_id = self.connection.execute(
            "SELECT source_record_id FROM uec.source_records s WHERE NOT EXISTS (SELECT 1 FROM uec.record_access_events e WHERE e.source_record_id = s.source_record_id) LIMIT 1"
        ).fetchone()[0]
        with self.connection.transaction():
            self.connection.execute("""
                INSERT INTO uec.record_access_events
                (source_record_id, action, reason_category, policy_version, maintainer)
                VALUES (%s, 'public_access_revoked', 'safety', 'ethics-v1', 'test-maintainer')
            """, (source_record_id,))
            self.connection.execute("""
                INSERT INTO uec.record_access_events
                (source_record_id, action, reason_category, policy_version, maintainer, occurred_at)
                VALUES (%s, 'public_access_restored', 'other', 'ethics-v1', 'test-maintainer', now() + interval '1 second')
            """, (source_record_id,))
            current = self.connection.execute(
                "SELECT action FROM uec.record_access_current WHERE source_record_id = %s",
                (source_record_id,),
            ).fetchone()[0]
            self.assertEqual(current, "public_access_restored")
            restricted = self.connection.execute(
                "SELECT count(*) FROM uec.public_access_restricted WHERE source_record_id = %s",
                (source_record_id,),
            ).fetchone()[0]
            self.assertEqual(restricted, 0)

    def test_suppression_references_are_payload_free_and_reimport_safe(self):
        tables = {row[0] for row in self.connection.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'uec'").fetchall()}
        if "suppression_cases" not in tables or "suppression_references" not in tables:
            self.skipTest("database is older than migration 018; Docker E2E applies the current schema")
        self.assertIn("suppression_cases", tables)
        self.assertIn("suppression_references", tables)
        columns = {row[0] for row in self.connection.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='uec' AND table_name='suppression_references'").fetchall()}
        self.assertNotIn("address", columns)
        self.assertNotIn("coordinates", columns)
        self.assertIn("source_record_key", columns)

    def test_suppression_lift_requires_explicit_lifted_state(self):
        migration = (__import__('pathlib').Path(__file__).parents[1] / 'migrations' / '019_explicit_suppression_lift.sql').read_text(encoding='utf-8')
        self.assertIn("'lifted'", migration)
        self.assertIn("'closed', 'expired'", migration)
        self.assertNotIn("WHERE case_record.status IN ('active', 'review')", migration)

    def test_v2_display_history_is_suppression_aware(self):
        migration = (__import__('pathlib').Path(__file__).parents[1] / 'migrations' / '020_suppression_aware_v2_history.sql').read_text(encoding='utf-8')
        self.assertIn('DROP VIEW IF EXISTS uec.map_facilities_display_history', migration)
        self.assertIn('FROM uec.public_access_restricted restricted', migration)
        self.assertIn('restricted.source_record_id = display.source_record_id', migration)


if __name__ == "__main__":
    unittest.main()
