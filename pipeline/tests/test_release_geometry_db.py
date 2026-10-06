"""Disposable-PostGIS proof for source, provider, coarse and unmapped geometry."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import unittest
import uuid
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

from pipeline.common.release_geometry import geometry_rows_sql, RELEASE_GATE_METRICS_SQL


ROOT = Path(__file__).parents[1].parent
OWNED_DATABASE = "uec_v0_cohort_review_test20261005"
COHORT_SCRIPT = ROOT / "pipeline" / "scripts" / "stages" / "record-release-cohort-review.py"
SPEC = importlib.util.spec_from_file_location("geometry_test_cohort_review", COHORT_SCRIPT)
RECORDER = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(RECORDER)


class _RollbackFixture(Exception):
    pass


@unittest.skipUnless(os.environ.get("UEC_COHORT_REVIEW_TEST_DATABASE_URL"),
                     "set UEC_COHORT_REVIEW_TEST_DATABASE_URL for disposable PostGIS geometry proof")
class PublicGeometryPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.url = os.environ["UEC_COHORT_REVIEW_TEST_DATABASE_URL"]
        if os.environ.get("UEC_COHORT_REVIEW_TEST_DATABASE") != OWNED_DATABASE:
            raise unittest.SkipTest("geometry proof requires its exact disposable database")
        from urllib.parse import urlsplit
        parsed = urlsplit(cls.url)
        if parsed.hostname not in {"127.0.0.1", "localhost", "::1"} or parsed.path.lstrip("/") != OWNED_DATABASE:
            raise unittest.SkipTest("geometry proof requires its exact loopback disposable database")

    def _candidate(self, connection):
        suffix = uuid.uuid4().hex
        source = f"geometry.synthetic.{suffix}"
        release_id = f"v0-candidate-geometry-{suffix}"
        artifact_sha = hashlib.sha256(suffix.encode()).hexdigest()
        ruleset = f"geometry-rules-{suffix}"
        crosswalk = f"geometry-crosswalk-{suffix}"
        classification_ruleset = f"geometry-classification-{suffix}"
        freeze_sha = "a" * 64
        inventory_sha = "b" * 64
        crosswalk_doc = {"source_id": source, "taxonomy_version": "uec-taxonomy-v1",
                         "crosswalk_version": crosswalk, "ruleset_version": classification_ruleset,
                         "rules": []}
        connection.execute("INSERT INTO uec.sources(source_id,country_code,name,official_url,access_method,status) VALUES (%s,'ZZ','Synthetic source','https://example.invalid/','fixture','active')", (source,))
        artifact_id = connection.execute("""
            INSERT INTO uec.raw_artifacts(storage_key,sha256,byte_size,retrieved_at)
            VALUES (%s,%s,0,now()) RETURNING artifact_id::text
        """, (f"synthetic/{suffix}", artifact_sha)).fetchone()[0]
        connection.execute("""
            INSERT INTO uec.taxonomy_crosswalks(source_id,taxonomy_version,crosswalk_version,
                ruleset_version,definition,definition_sha256)
            VALUES (%s,'uec-taxonomy-v1',%s,%s,%s,%s)
        """, (source, crosswalk, classification_ruleset, Jsonb(crosswalk_doc),
              hashlib.sha256(json.dumps(crosswalk_doc, sort_keys=True).encode()).hexdigest()))
        connection.execute("""
            INSERT INTO uec.releases(release_id,status,ruleset_version,summary,profile,test_only)
            VALUES (%s,'candidate',%s,%s,'official',false)
        """, (release_id, ruleset, Jsonb({"candidate_only": True, "freeze_sha256": freeze_sha,
                                           "inventory_sha256": inventory_sha,
                                           "selected_sources": [source]})))

        fixtures = [
            ("source_unknown_precision", "processing_and_preparation", 55.5, 10.2,
             {"source_location": {"latitude": 55.5, "longitude": 10.2,
                                  "precision": "source-precision-unknown",
                                  "coordinate_method": "source_coordinates"}},
             "source_coordinates", "source-precision-unknown"),
            ("provider_high_accepted", "processing_and_preparation", 56.5, 10.3,
             {"display_location": {"latitude": 56.5, "longitude": 10.3,
                 "method": "geoapify_forward", "precision": "locality",
                 "provider": "Geoapify", "evidence_kind": "provider_derived",
                 "evidence_id": "synthetic-provider-evidence", "provider_status": "accepted",
                 "provider_queried_at": "2026-10-05T12:00:00Z",
                 "coordinate_review_status": "pending_human_review",
                 "confidence": 0.96, "confidence_band": "high"}},
             "geoapify_forward", "locality"),
            ("verified_coarse", "processing_and_preparation", 57.5, 10.4,
             {"display_location": {"latitude": 57.5, "longitude": 10.4,
                 "method": "coarse_reference", "precision": "municipality",
                 "evidence_kind": "verified_coarse_reference",
                 "evidence_id": "synthetic-reference-evidence",
                 "reference_source_id": "synthetic-grid-v1",
                 "source": "Synthetic administrative grid"}},
             "coarse_reference", "municipality"),
            ("unmapped", "processing_and_preparation", None, None, {}, None, None),
            ("zero_zero", "processing_and_preparation", 0.0, 0.0,
             {"source_location": {"latitude": 0, "longitude": 0,
                                  "precision": "numeric", "coordinate_method": "source_coordinates"}},
             "source_coordinates", "numeric"),
            ("provider_pending", "processing_and_preparation", 58.5, 10.5,
             {"display_location": {"latitude": 58.5, "longitude": 10.5,
                 "method": "geoapify_forward", "precision": "locality",
                 "provider": "Geoapify", "evidence_kind": "provider_derived",
                 "evidence_id": "synthetic-pending-evidence", "provider_status": "review_required",
                 "provider_queried_at": "2026-10-05T12:00:00Z",
                 "coordinate_review_status": "pending_human_review",
                 "confidence": 0.95, "confidence_band": "high"}},
             "geoapify_forward", "locality"),
            ("malformed_source", "processing_and_preparation", None, None,
             {"source_location": {"latitude": "not-a-number", "longitude": 10,
                                  "precision": "numeric", "coordinate_method": "source_coordinates"}},
             "source_coordinates", "numeric"),
            ("excluded_category", "slaughter", 59.5, 10.6,
             {"source_location": {"latitude": 59.5, "longitude": 10.6,
                                  "precision": "numeric", "coordinate_method": "source_coordinates"}},
             "source_coordinates", "numeric"),
        ]
        for index, (kind, category, latitude, longitude, evidence, method, precision) in enumerate(fixtures):
            record_id = connection.execute("""
                INSERT INTO uec.source_records(source_id,source_record_key,artifact_id,raw_fields,parsed_at)
                VALUES (%s,%s,%s,'{}',now()) RETURNING source_record_id::text
            """, (source, f"record-{index}-{suffix}", artifact_id)).fetchone()[0]
            facility_id = connection.execute("INSERT INTO uec.facilities(country_code,city) VALUES ('ZZ','Example') RETURNING facility_id::text").fetchone()[0]
            evidence["fixture_kind"] = kind
            observation_id = connection.execute("""
                INSERT INTO uec.observations(facility_id,source_record_id,observed_at,observation,classification,
                    ruleset_id,rule_id,classification_category,classification_review_status,first_observed_at,
                    coordinate,coordinate_method,coordinate_precision,coordinate_review_status)
                VALUES (%s,%s,now(),%s,'{}',%s,'fixture',%s,'review_required',now(),
                    CASE WHEN %s::float8 IS NULL THEN NULL
                         ELSE ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography END,
                    %s,%s,'review_required') RETURNING observation_id::text
            """, (facility_id, record_id, Jsonb(evidence), classification_ruleset, category,
                  latitude, longitude, latitude, method, precision)).fetchone()[0]
            set_id = connection.execute("""
                INSERT INTO uec.observation_taxonomy_assignment_sets
                    (observation_id,source_record_id,source_id,artifact_id,taxonomy_version,
                     crosswalk_version,ruleset_version,display_category)
                VALUES (%s,%s,%s,%s,'uec-taxonomy-v1',%s,%s,%s) RETURNING assignment_set_id::text
            """, (observation_id, record_id, source, artifact_id, crosswalk,
                  classification_ruleset, category)).fetchone()[0]
            connection.execute("""
                INSERT INTO uec.observation_taxonomy_assignments
                    (assignment_set_id,assignment_ordinal,primary_key,mapping_method,mapping_status)
                VALUES (%s,0,%s,'direct','mapped')
            """, (set_id, category))
            connection.execute("""
                INSERT INTO uec.release_members(release_id,facility_id,observation_id,default_visible)
                VALUES (%s,%s,%s,false)
            """, (release_id, facility_id, observation_id))

        member_count, member_sha = RECORDER._member_digest(connection, release_id)
        reviewed_at = "2026-10-05T12:00:00Z"
        scope = {
            "source_id": source, "artifact_id": artifact_id, "artifact_sha256": artifact_sha,
            "factual_review_status": "unreviewed", "privacy_screening_status": "passed",
            "privacy_method": "synthetic bounded privacy review", "privacy_evidence_reference": "test:privacy",
            "maintainer_approval": "approved", "publication_eligible": True,
            "project_approval_method": "synthetic release approval", "project_approval_evidence_reference": "test:approval",
            "redistribution_status": "cleared", "rights_actor": "maintainer:synthetic",
            "rights_reference": "test:rights", "rights_decided_at": reviewed_at,
            "classification_interpretation_status": "approved", "classification_method": "synthetic taxonomy review",
            "classification_evidence_reference": "test:classification",
            "geometry_interpretation_status": "approved", "geometry_method": "source, high-confidence accepted provider, and verified coarse reference",
            "geometry_evidence_reference": "test:geometry", "taxonomy_version": "uec-taxonomy-v1",
            "crosswalk_version": crosswalk, "classification_ruleset_version": classification_ruleset,
            "excluded_display_categories": ["slaughter"],
            "exclusion_reason_category": "scope-policy", "exclusion_policy_reference": "test:scope-policy",
        }
        return {
            "schema_version": "uec-release-cohort-review-v1", "release_id": release_id,
            "profile": "official", "ruleset_version": ruleset, "freeze_sha256": freeze_sha,
            "inventory_sha256": inventory_sha, "member_sha256": member_sha, "member_count": member_count,
            "reviewer": {"actor": "maintainer:synthetic", "role": "maintainer", "reviewed_at": reviewed_at},
            "review_method": "synthetic bounded release review", "review_evidence_reference": "test:release-review",
            "source_artifact_scopes": [scope],
        }

    def test_release_scoped_geometry_parity_and_suppression_without_evidence_mutation(self):
        with psycopg.connect(self.url) as connection:
            with self.assertRaises(_RollbackFixture):
                with connection.transaction():
                    document = self._candidate(connection)
                    release_id = document["release_id"]
                    before = connection.execute("""
                        SELECT md5(string_agg(to_jsonb(observation)::text,E'\\n' ORDER BY observation.observation_id))
                        FROM uec.observations observation
                        JOIN uec.release_members member USING(observation_id)
                        WHERE member.release_id=%s
                    """, (release_id,)).fetchone()[0]
                    review = RECORDER._verify(connection, document, apply_changes=True)
                    self.assertEqual(review["default_visible_count"], 6)
                    query = geometry_rows_sql("""
                        SELECT evidence->>'fixture_kind', display_precision,
                               ST_Y(display_location::geometry), ST_X(display_location::geometry),
                               geometry_provenance, approved_member_ok, default_visible
                        FROM eligible_geometry ORDER BY evidence->>'fixture_kind'
                    """)
                    rows = connection.execute(query, (release_id, release_id)).fetchall()
                    by_kind = {row[0]: row[1:] for row in rows}
                    self.assertEqual(len(by_kind), 7)
                    self.assertEqual(by_kind["source_unknown_precision"][0], "source_reported")
                    self.assertEqual(by_kind["source_unknown_precision"][1:3], (55.5, 10.2))
                    self.assertEqual(by_kind["source_unknown_precision"][3]["source_precision"], "source-precision-unknown")
                    self.assertEqual(by_kind["provider_high_accepted"][0], "approximate")
                    self.assertEqual(by_kind["provider_high_accepted"][1:3], (56.5, 10.3))
                    self.assertEqual(by_kind["provider_high_accepted"][3]["provider_status"], "accepted")
                    self.assertEqual(by_kind["provider_high_accepted"][3]["coordinate_review_status"], "pending_human_review")
                    self.assertEqual(by_kind["verified_coarse"][0], "approximate")
                    self.assertEqual(by_kind["unmapped"][0:3], ("unmapped", None, None))
                    self.assertEqual(by_kind["zero_zero"][0:3], ("unmapped", None, None))
                    self.assertEqual(by_kind["provider_pending"][0:3], ("unmapped", None, None))
                    self.assertEqual(by_kind["malformed_source"][0:3], ("unmapped", None, None))
                    self.assertEqual(by_kind["excluded_category"][0:3], ("source_reported", 59.5, 10.6))
                    self.assertFalse(by_kind["excluded_category"][4])
                    self.assertFalse(by_kind["excluded_category"][5])
                    self.assertTrue(all(row[4] for kind, row in by_kind.items()
                                        if kind != "excluded_category"))

                    wrong_scope = connection.execute(query, ("another-release", "another-release")).fetchall()
                    self.assertEqual(wrong_scope, [])
                    connection.execute("""
                        INSERT INTO uec.record_access_events(source_record_id,action,reason_category,
                            policy_version,maintainer,note)
                        SELECT observation.source_record_id,'public_access_revoked','privacy',
                               'ethics-v1','maintainer:synthetic','synthetic suppression proof'
                        FROM uec.observations observation
                        JOIN uec.release_members member USING(observation_id)
                        WHERE member.release_id=%s AND observation.observation->>'fixture_kind'='source_unknown_precision'
                    """, (release_id,))
                    metrics = connection.execute(RELEASE_GATE_METRICS_SQL,
                                                  (release_id, release_id, release_id)).fetchone()
                    self.assertEqual(metrics[1], 6)
                    self.assertEqual(metrics[4], 0)  # immutable source review_required is not promoted to approved
                    self.assertEqual(metrics[11], 1)  # active suppression is counted only on visible membership
                    after = connection.execute("""
                        SELECT md5(string_agg(to_jsonb(observation)::text,E'\\n' ORDER BY observation.observation_id))
                        FROM uec.observations observation
                        JOIN uec.release_members member USING(observation_id)
                        WHERE member.release_id=%s
                    """, (release_id,)).fetchone()[0]
                    self.assertEqual(before, after)
                    raise _RollbackFixture()


if __name__ == "__main__":
    unittest.main()
