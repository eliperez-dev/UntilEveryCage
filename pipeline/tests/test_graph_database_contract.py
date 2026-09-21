import os
import unittest
import uuid

import psycopg


DATABASE_URL = os.environ.get(
    "UEC_DATABASE_URL",
    "postgresql://uec:uec-local-development-only@localhost:5433/uec",
)


class GraphDatabaseContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.connection = psycopg.connect(DATABASE_URL)
            tables = {row[0] for row in cls.connection.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'uec'"
            ).fetchall()}
            if "claims" not in tables or "organization_relationship_observations" not in tables:
                raise unittest.SkipTest("graph migrations are not applied")
        except psycopg.Error as error:
            raise unittest.SkipTest(f"PostGIS is unavailable: {error}")

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "connection"):
            cls.connection.close()

    def fixture(self):
        suffix = uuid.uuid4().hex
        source_id = f"test.graph.{suffix}"
        artifact_id = uuid.uuid4()
        record_id = uuid.uuid4()
        facility_id = uuid.uuid4()
        organization_id = uuid.uuid4()
        other_organization_id = uuid.uuid4()
        self.connection.execute(
            "INSERT INTO uec.sources (source_id, country_code, name, official_url, access_method) VALUES (%s, 'US', 'Synthetic graph source', 'https://example.invalid/graph', 'fixture')",
            (source_id,),
        )
        self.connection.execute(
            "INSERT INTO uec.raw_artifacts (artifact_id, storage_key, sha256, byte_size, retrieved_at) VALUES (%s, %s, %s, 1, now())",
            (artifact_id, f"test/{suffix}", suffix + "0" * (64 - len(suffix))),
        )
        self.connection.execute(
            "INSERT INTO uec.source_records (source_record_id, source_id, source_record_key, artifact_id, raw_fields, parsed_at) VALUES (%s, %s, %s, %s, '{}'::jsonb, now())",
            (record_id, source_id, f"record-{suffix}", artifact_id),
        )
        self.connection.execute(
            "INSERT INTO uec.facilities (facility_id, canonical_name, country_code) VALUES (%s, 'Synthetic facility', 'US')",
            (facility_id,),
        )
        self.connection.execute(
            "INSERT INTO uec.organizations (organization_id, canonical_name, country_code) VALUES (%s, 'Synthetic operator', 'US'), (%s, 'Synthetic alternate owner', 'US')",
            (organization_id, other_organization_id),
        )
        return source_id, artifact_id, record_id, facility_id, organization_id, other_organization_id

    def test_source_qualified_crosswalk_and_contradictory_claims_coexist(self):
        with self.connection.transaction():
            source, artifact, record, facility, organization, alternate = self.fixture()
            left = self.connection.execute(
                "INSERT INTO uec.source_entity_identifiers (source_id, source_record_id, entity_type, facility_id, identifier_type, source_identifier, observed_at) VALUES (%s, %s, 'facility', %s, 'permit', 'FAC-1', now()) RETURNING identifier_id",
                (source, record, facility),
            ).fetchone()[0]
            right = self.connection.execute(
                "INSERT INTO uec.source_entity_identifiers (source_id, source_record_id, entity_type, organization_id, identifier_type, source_identifier, observed_at) VALUES (%s, %s, 'organization', %s, 'registration', 'ORG-1', now()) RETURNING identifier_id",
                (source, record, organization),
            ).fetchone()[0]
            self.connection.execute(
                "INSERT INTO uec.source_entity_crosswalks (left_identifier_id, right_identifier_id, source_id, source_record_id, match_method, observed_at) VALUES (%s, %s, %s, %s, 'synthetic review', now())",
                (left, right, source, record),
            )
            for count in (10, 20):
                self.connection.execute(
                    "INSERT INTO uec.claims (source_id, source_record_id, facility_id, claim_domain, claim_kind, claim_value, observed_at) VALUES (%s, %s, %s, 'animal_count', 'annual_headcount', jsonb_build_object('count', %s), now())",
                    (source, record, facility, count),
                )
            self.assertEqual(
                self.connection.execute(
                    "SELECT count(*) FROM uec.claim_current WHERE facility_id = %s AND claim_kind = 'annual_headcount'",
                    (facility,),
                ).fetchone()[0],
                2,
            )
            with self.assertRaises(psycopg.Error):
                with self.connection.transaction():
                    self.connection.execute(
                        "INSERT INTO uec.source_entity_crosswalks (left_identifier_id, right_identifier_id, source_id, source_record_id, match_method, observed_at) VALUES (%s, %s, 'wrong-source', %s, 'bad', now())",
                        (left, right, record),
                    )

    def test_unknown_relationship_requires_reason_and_public_suppression_propagates(self):
        with self.connection.transaction():
            source, artifact, record, facility, organization, alternate = self.fixture()
            self.connection.execute(
                "INSERT INTO uec.organization_relationship_observations (source_id, source_record_id, target_facility_id, assertion_status, unknown_reason, observed_at) VALUES (%s, %s, %s, 'unknown', 'source did not identify the operator', now())",
                (source, record, facility),
            )
            with self.assertRaises(psycopg.Error):
                with self.connection.transaction():
                    self.connection.execute(
                        "INSERT INTO uec.organization_relationship_observations (source_id, source_record_id, target_facility_id, assertion_status, observed_at) VALUES (%s, %s, %s, 'unknown', now())",
                        (source, record, facility),
                    )
            release = f"graph-release-{uuid.uuid4().hex}"
            self.connection.execute(
                "INSERT INTO uec.releases (release_id, status, ruleset_version, profile, summary) VALUES (%s, 'promoted', 'graph-test', 'official', '{}'::jsonb)",
                (release,),
            )
            claim = self.connection.execute(
                "INSERT INTO uec.claims (source_id, source_record_id, facility_id, claim_domain, claim_kind, claim_value, observed_at, review_state, storage_state, privacy_status, publication_status, release_id) VALUES (%s, %s, %s, 'operation', 'synthetic_status', '{\"status\":\"open\"}', now(), 'accepted', 'released', 'passed', 'released', %s) RETURNING claim_id",
                (source, record, facility, release),
            ).fetchone()[0]
            self.assertEqual(self.connection.execute("SELECT count(*) FROM uec.graph_public_claims WHERE claim_id = %s", (claim,)).fetchone()[0], 1)
            self.connection.execute(
                "INSERT INTO uec.record_access_events (source_record_id, action, reason_category, policy_version, maintainer) VALUES (%s, 'public_access_revoked', 'privacy', 'ethics-v1', 'synthetic-test')",
                (record,),
            )
            self.assertEqual(self.connection.execute("SELECT count(*) FROM uec.graph_public_claims WHERE claim_id = %s", (claim,)).fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
