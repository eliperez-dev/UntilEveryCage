from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

from pipeline.common import release_cohort_review as contract


ROOT = Path(__file__).parents[1].parent
SCRIPT = ROOT / "pipeline" / "scripts" / "stages" / "record-release-cohort-review.py"
SPEC = importlib.util.spec_from_file_location("record_release_cohort_review", SCRIPT)
recorder = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(recorder)
OWNED_DATABASE = "uec_v0_cohort_review_test20261005"


class CohortReviewContractTests(unittest.TestCase):
    def test_document_requires_explicit_operator_evidence_and_safe_allowlist(self):
        document = {
            "schema_version": "uec-release-cohort-review-v1", "release_id": "candidate",
            "profile": "official", "ruleset_version": "rules-v1", "freeze_sha256": "a" * 64,
            "inventory_sha256": "b" * 64, "member_sha256": "c" * 64, "member_count": 1,
            "reviewer": {"actor": "maintainer:synthetic", "role": "maintainer",
                          "reviewed_at": "2026-10-05T12:00:00Z"},
            "review_method": "synthetic document review", "review_evidence_reference": "test:review",
            "source_artifact_scopes": [{
                "source_id": "test.source", "artifact_id": str(uuid.uuid4()), "artifact_sha256": "d" * 64,
                "factual_review_status": "unreviewed", "privacy_screening_status": "pending",
                "privacy_method": "synthetic explicit status", "privacy_evidence_reference": "test:privacy",
                "maintainer_approval": "pending", "publication_eligible": False,
                "project_approval_method": "synthetic explicit status", "project_approval_evidence_reference": "test:approval",
                "redistribution_status": "unknown", "rights_actor": "maintainer:synthetic",
                "rights_reference": "test:rights", "rights_decided_at": "2026-10-05T12:00:00Z",
                "classification_interpretation_status": "unreviewed", "classification_method": "synthetic",
                "classification_evidence_reference": "test:classification", "geometry_interpretation_status": "unreviewed",
                "geometry_method": "synthetic", "geometry_evidence_reference": "test:geometry",
                "taxonomy_version": contract.TAXONOMY_VERSION, "crosswalk_version": "crosswalk-v1",
                "classification_ruleset_version": "class-v1", "excluded_display_categories": [],
            }],
        }
        self.assertEqual(contract.validate_document(document), document)
        invalid = json.loads(json.dumps(document))
        invalid["review_method"] = ""
        with self.assertRaises(contract.CohortReviewError):
            contract.validate_document(invalid)
        invalid = json.loads(json.dumps(document))
        invalid["raw_rows"] = [{"address": "forbidden"}]
        with self.assertRaises(contract.CohortReviewError):
            contract.validate_document(invalid)

    def test_migration_and_worker_scope_are_release_and_artifact_bound(self):
        migration = (ROOT / "pipeline" / "migrations" / "062_release_cohort_review.sql").read_text(encoding="utf-8").lower()
        self.assertIn("release_cohort_review_documents_append_only", migration)
        self.assertIn("release_cohort_review_scopes_append_only", migration)
        self.assertIn("to_jsonb(new) - 'default_visible'", migration)
        self.assertIn("release membership cannot grow after cohort review", migration)
        query = contract.geometry_approval_sql("SELECT observation_id FROM approved_geometry_members")
        for token in ("scope.geometry_interpretation_status='approved'", "artifact.sha256=scope.artifact_sha256",
                      "release.summary->>'freeze_sha256'=scope.freeze_sha256",
                      "release.summary->>'inventory_sha256'=scope.inventory_sha256",
                      "release.status IN ('candidate','validated','promoted')"):
            self.assertIn(token, query)

    def test_operator_document_must_remain_in_ignored_local_reports(self):
        with self.assertRaises(contract.CohortReviewError):
            recorder._read_operator_document(ROOT / "README.md")

    def test_migration_and_worker_scope_are_release_and_artifact_bound(self):
        migration = (ROOT / "pipeline" / "migrations" / "062_release_cohort_review.sql").read_text(encoding="utf-8").lower()
        self.assertIn("release_cohort_review_documents_append_only", migration)
        self.assertIn("release_cohort_review_scopes_append_only", migration)
        self.assertIn("to_jsonb(new) - 'default_visible'", migration)
        self.assertIn("release membership cannot grow after cohort review", migration)
        query = contract.geometry_approval_sql("SELECT observation_id FROM approved_geometry_members")
        for token in ("scope.geometry_interpretation_status='approved'", "artifact.sha256=scope.artifact_sha256",
                      "release.summary->>'freeze_sha256'=scope.freeze_sha256",
                      "release.summary->>'inventory_sha256'=scope.inventory_sha256",
                      "release.status IN ('candidate','validated','promoted')"):
            self.assertIn(token, query)

    def test_operator_document_must_remain_in_ignored_local_reports(self):
        with self.assertRaises(contract.CohortReviewError):
            recorder._read_operator_document(ROOT / "README.md")


@unittest.skipUnless(os.environ.get("UEC_COHORT_REVIEW_TEST_DATABASE_URL"),
                     "set UEC_COHORT_REVIEW_TEST_DATABASE_URL for disposable PostGIS cohort review proof")
class CohortReviewPostgresTests(unittest.TestCase):
    """Synthetic integration test; every fixture is rolled back inside its test."""

    @classmethod
    def setUpClass(cls):
        cls.url = os.environ["UEC_COHORT_REVIEW_TEST_DATABASE_URL"]
        if os.environ.get("UEC_COHORT_REVIEW_TEST_DATABASE") != OWNED_DATABASE:
            raise unittest.SkipTest("UEC_COHORT_REVIEW_TEST_DATABASE must name the exact disposable database")
        from urllib.parse import urlsplit
        parsed = urlsplit(cls.url)
        if parsed.hostname not in {"127.0.0.1", "localhost", "::1"} or parsed.path.lstrip("/") != OWNED_DATABASE:
            raise unittest.SkipTest("cohort review proof requires its exact loopback disposable database")
        with psycopg.connect(cls.url) as connection:
            migrations = connection.execute("SELECT count(*) FROM uec.schema_migrations").fetchone()[0]
            expected = len(list((ROOT / "pipeline" / "migrations").glob("*.sql")))
            if migrations != expected:
                raise unittest.SkipTest("dedicated cohort review test database is not fully migrated")

    def _fixture(self, connection):
        suffix = uuid.uuid4().hex
        source = f"cohort.synthetic.{suffix}"
        release_id = f"v0-candidate-cohort-{suffix}"
        artifact_hash = hashlib.sha256(suffix.encode()).hexdigest()
        freeze_hash = "a" * 64
        inventory_hash = "b" * 64
        ruleset = f"release-rules-{suffix}"
        crosswalk = f"crosswalk-{suffix}"
        classification_ruleset = f"classification-{suffix}"
        crosswalk_document = {"source_id": source, "taxonomy_version": contract.TAXONOMY_VERSION,
                              "crosswalk_version": crosswalk, "ruleset_version": classification_ruleset, "rules": []}
        connection.execute("INSERT INTO uec.sources(source_id,country_code,name,official_url,access_method,status) VALUES (%s,'ZZ','Synthetic','https://example.invalid/','fixture','active')", (source,))
        artifact_id = connection.execute("""
            INSERT INTO uec.raw_artifacts(storage_key,sha256,byte_size,retrieved_at)
            VALUES (%s,%s,0,now()) RETURNING artifact_id::text
        """, (f"synthetic/{suffix}", artifact_hash)).fetchone()[0]
        connection.execute("INSERT INTO uec.taxonomy_crosswalks(source_id,taxonomy_version,crosswalk_version,ruleset_version,definition,definition_sha256) VALUES (%s,%s,%s,%s,%s,%s)",
                           (source, contract.TAXONOMY_VERSION, crosswalk, classification_ruleset,
                            Jsonb(crosswalk_document), hashlib.sha256(json.dumps(crosswalk_document, sort_keys=True).encode()).hexdigest()))
        connection.execute("INSERT INTO uec.releases(release_id,status,ruleset_version,summary,profile,test_only) VALUES (%s,'candidate',%s,%s,'official',false)",
                           (release_id, ruleset, Jsonb({"candidate_only": True, "freeze_sha256": freeze_hash,
                                                       "inventory_sha256": inventory_hash, "selected_sources": [source]})))
        categories = ["slaughter", "processing_and_preparation"]
        for index, category in enumerate(categories):
            record_id = connection.execute("""
                INSERT INTO uec.source_records(source_id,source_record_key,artifact_id,raw_fields,parsed_at)
                VALUES (%s,%s,%s,'{}',now()) RETURNING source_record_id::text
            """, (source, f"record-{index}-{suffix}", artifact_id)).fetchone()[0]
            facility_id = connection.execute("INSERT INTO uec.facilities(country_code) VALUES ('ZZ') RETURNING facility_id::text").fetchone()[0]
            observation_id = connection.execute("""
                INSERT INTO uec.observations(facility_id,source_record_id,observed_at,observation,classification,
                    ruleset_id,rule_id,classification_category,classification_review_status,first_observed_at)
                VALUES (%s,%s,now(),'{}','{}',%s,'rule',%s,'review_required',now()) RETURNING observation_id::text
            """, (facility_id, record_id, classification_ruleset, category)).fetchone()[0]
            set_id = connection.execute("""
                INSERT INTO uec.observation_taxonomy_assignment_sets
                    (observation_id,source_record_id,source_id,artifact_id,taxonomy_version,crosswalk_version,
                     ruleset_version,display_category)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING assignment_set_id::text
            """, (observation_id, record_id, source, artifact_id, contract.TAXONOMY_VERSION,
                  crosswalk, classification_ruleset, category)).fetchone()[0]
            connection.execute("""
                INSERT INTO uec.observation_taxonomy_assignments
                    (assignment_set_id,assignment_ordinal,primary_key,mapping_method,mapping_status)
                VALUES (%s,0,%s,'direct','mapped')
            """, (set_id, category))
            connection.execute("INSERT INTO uec.release_members(release_id,facility_id,observation_id,default_visible) VALUES (%s,%s,%s,false)",
                               (release_id, facility_id, observation_id))
            connection.execute("""
                INSERT INTO uec.publication_review_events
                    (source_record_id,release_id,factual_review_status,privacy_screening_status,
                     maintainer_approval,publication_eligible,reviewer_role,reviewed_at)
                VALUES (%s,%s,'unreviewed','pending','pending',false,'importer','2020-01-01T00:00:00Z')
            """, (record_id, release_id))
        member_count, member_sha = recorder._member_digest(connection, release_id)
        reviewed_at = "2026-10-05T12:00:00Z"
        scope = {
            "source_id": source, "artifact_id": artifact_id, "artifact_sha256": artifact_hash,
            "factual_review_status": "unreviewed", "privacy_screening_status": "passed",
            "privacy_method": "synthetic explicit operator status", "privacy_evidence_reference": "test:privacy-evidence",
            "maintainer_approval": "approved", "publication_eligible": True,
            "project_approval_method": "synthetic explicit operator status", "project_approval_evidence_reference": "test:approval-evidence",
            "redistribution_status": "cleared", "rights_actor": "maintainer:synthetic", "rights_reference": "test:rights-evidence",
            "rights_decided_at": reviewed_at, "classification_interpretation_status": "approved",
            "classification_method": "synthetic taxonomy review", "classification_evidence_reference": "test:classification",
            "geometry_interpretation_status": "approved", "geometry_method": "synthetic geometry review",
            "geometry_evidence_reference": "test:geometry", "taxonomy_version": contract.TAXONOMY_VERSION,
            "crosswalk_version": crosswalk, "classification_ruleset_version": classification_ruleset,
            "excluded_display_categories": ["slaughter"], "exclusion_reason_category": "scope-policy",
            "exclusion_policy_reference": "test:exclude-category",
        }
        document = {
            "schema_version": "uec-release-cohort-review-v1", "release_id": release_id,
            "profile": "official", "ruleset_version": ruleset, "freeze_sha256": freeze_hash,
            "inventory_sha256": inventory_hash, "member_sha256": member_sha, "member_count": member_count,
            "reviewer": {"actor": "maintainer:synthetic", "role": "maintainer", "reviewed_at": reviewed_at},
            "review_method": "synthetic bounded review", "review_evidence_reference": "test:review-evidence",
            "source_artifact_scopes": [scope],
        }
        return document

    def test_dry_run_apply_exclusion_unreviewed_replay_and_atomicity(self):
        with psycopg.connect(self.url) as connection:
            with self.assertRaises(_RollbackFixture):
                with connection.transaction():
                    document = self._fixture(connection)
                    template_path = ROOT / "data" / "reports" / f".cohort-review-test-{uuid.uuid4().hex}.json"
                    try:
                        template_receipt = recorder.prepare_template(connection, document["release_id"], template_path)
                        template = json.loads(template_path.read_text(encoding="utf-8"))
                        self.assertEqual(template_receipt["status"], "prepared")
                        self.assertEqual(template["member_sha256"], document["member_sha256"])
                        self.assertEqual(template["source_artifact_scopes"][0]["redistribution_status"], "unknown")
                        self.assertFalse(template["source_artifact_scopes"][0]["publication_eligible"])
                        self.assertEqual(connection.execute("SELECT count(*) FROM uec.release_cohort_review_documents WHERE release_id=%s", (document["release_id"],)).fetchone()[0], 0)
                    finally:
                        template_path.unlink(missing_ok=True)
                    dry = recorder._verify(connection, document, apply_changes=False)
                    self.assertEqual(dry["status"], "verified")
                    self.assertEqual(dry["member_count"], 2)
                    self.assertEqual(dry["default_visible_count"], 1)
                    self.assertEqual(connection.execute("SELECT count(*) FROM uec.release_cohort_review_documents WHERE release_id=%s", (document["release_id"],)).fetchone()[0], 0)
                    self.assertEqual(connection.execute("SELECT bool_and(NOT default_visible) FROM uec.release_members WHERE release_id=%s", (document["release_id"],)).fetchone()[0], True)

                    invalid = json.loads(json.dumps(document))
                    invalid["member_sha256"] = "f" * 64
                    with self.assertRaises(contract.CohortReviewError):
                        recorder._verify(connection, invalid, apply_changes=True)
                    self.assertEqual(connection.execute("SELECT count(*) FROM uec.source_rights_decisions WHERE release_id=%s", (document["release_id"],)).fetchone()[0], 0)
                    originals_before = connection.execute("""
                        SELECT
                          md5(COALESCE((SELECT string_agg(to_jsonb(record)::text,E'\n' ORDER BY record.source_record_id)
                              FROM uec.release_members member
                              JOIN uec.observations observation USING(observation_id)
                              JOIN uec.source_records record USING(source_record_id)
                              WHERE member.release_id=%s),'')),
                          md5(COALESCE((SELECT string_agg(to_jsonb(observation)::text,E'\n' ORDER BY observation.observation_id)
                              FROM uec.release_members member
                              JOIN uec.observations observation USING(observation_id)
                              WHERE member.release_id=%s),''))
                    """, (document["release_id"], document["release_id"])).fetchone()

                    apply = recorder._verify(connection, document, apply_changes=True)
                    self.assertEqual(apply["status"], "recorded")
                    self.assertEqual(apply["default_visible_count"], 1)
                    visible = connection.execute("""
                        SELECT assignment_set.display_category,member.default_visible
                        FROM uec.release_members member
                        JOIN uec.observations observation USING(observation_id)
                        JOIN uec.observation_taxonomy_assignment_sets assignment_set USING(observation_id)
                        WHERE member.release_id=%s ORDER BY assignment_set.display_category
                    """, (document["release_id"],)).fetchall()
                    self.assertEqual(visible, [("processing_and_preparation", True), ("slaughter", False)])
                    self.assertEqual(connection.execute("""
                        SELECT
                          md5(COALESCE((SELECT string_agg(to_jsonb(record)::text,E'\n' ORDER BY record.source_record_id)
                              FROM uec.release_members member
                              JOIN uec.observations observation USING(observation_id)
                              JOIN uec.source_records record USING(source_record_id)
                              WHERE member.release_id=%s),'')),
                          md5(COALESCE((SELECT string_agg(to_jsonb(observation)::text,E'\n' ORDER BY observation.observation_id)
                              FROM uec.release_members member
                              JOIN uec.observations observation USING(observation_id)
                              WHERE member.release_id=%s),''))
                    """, (document["release_id"], document["release_id"])).fetchone(), originals_before)
                    event = connection.execute("""
                        SELECT factual_review_status,privacy_screening_status,maintainer_approval,publication_eligible
                        FROM uec.publication_review_release_current WHERE release_id=%s
                        ORDER BY source_record_id LIMIT 1
                    """, (document["release_id"],)).fetchone()
                    self.assertEqual(event[0], "unreviewed")
                    counts_before = connection.execute("""
                        SELECT (SELECT count(*) FROM uec.source_rights_decisions WHERE release_id=%s),
                               (SELECT count(*) FROM uec.publication_review_events WHERE release_id=%s)
                    """, (document["release_id"], document["release_id"])).fetchone()
                    replay = recorder._verify(connection, document, apply_changes=True)
                    self.assertEqual(replay["status"], "already_recorded")
                    self.assertEqual(connection.execute("""
                        SELECT (SELECT count(*) FROM uec.source_rights_decisions WHERE release_id=%s),
                               (SELECT count(*) FROM uec.publication_review_events WHERE release_id=%s)
                    """, (document["release_id"], document["release_id"])).fetchone(), counts_before)

                    # The fixture transaction rolls back every synthetic row,
                    # including the successful apply, when this sentinel exits.
                    raise _RollbackFixture()


class _RollbackFixture(Exception):
    pass


if __name__ == "__main__":
    unittest.main()
