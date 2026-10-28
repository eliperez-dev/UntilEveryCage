from __future__ import annotations

import uuid
import unittest
import copy
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

import psycopg

from pipeline.geocoding.postcode_reference import (
    MATCH_METHOD, RULESET, derived_result_id, normalize_postcode,
    select_postcode_reference,
    _append_result,
)


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "pipeline/migrations/110_locationiq_postcode_reference.sql"


def postcode_result(*, lat="51.5", lon="-0.12", country="gb", postcode="SW1A 1AA",
                    klass="place", result_type="postcode"):
    return {"lat": lat, "lon": lon, "class": klass, "type": result_type,
            "address": {"country_code": country, "postcode": postcode}}


class LocationIqPostcodeReferenceTests(unittest.TestCase):
    def test_unique_full_postcode_candidate(self):
        selected = select_postcode_reference({"results": [postcode_result()]}, "sw1a 1aa")
        self.assertEqual(selected, (0, 51.5, -0.12))

    def test_rejects_invalid_source_postcode_wrong_country_and_wrong_postcode(self):
        self.assertIsNone(select_postcode_reference({"results": [postcode_result()]}, "SW1A"))
        self.assertIsNone(select_postcode_reference(
            {"results": [postcode_result(country="ie")]}, "SW1A 1AA"))
        self.assertIsNone(select_postcode_reference(
            {"results": [postcode_result(postcode="SW1A 1AB")]}, "SW1A 1AA"))

    def test_requires_explicit_postcode_place_and_finite_in_bounds_coordinates(self):
        self.assertIsNone(select_postcode_reference(
            {"results": [postcode_result(klass="boundary")]}, "SW1A 1AA"))
        self.assertIsNone(select_postcode_reference(
            {"results": [postcode_result(result_type="city")]}, "SW1A 1AA"))
        self.assertIsNone(select_postcode_reference(
            {"results": [postcode_result(lat="NaN")]}, "SW1A 1AA"))
        self.assertIsNone(select_postcode_reference(
            {"results": [postcode_result(lon="-9")]}, "SW1A 1AA"))
        for latitude in (51.5, True, None):
            with self.subTest(latitude=latitude):
                self.assertIsNone(select_postcode_reference(
                    {"results": [postcode_result(lat=latitude)]}, "SW1A 1AA"))

    def test_identical_duplicates_are_one_point_but_conflicting_points_are_ambiguous(self):
        one = postcode_result()
        self.assertEqual(select_postcode_reference({"results": [one, dict(one)]}, "SW1A 1AA"),
                         (0, 51.5, -0.12))
        self.assertIsNone(select_postcode_reference(
            {"results": [one, postcode_result(lat="51.6")]}, "SW1A 1AA"))

    def test_derived_identity_is_stable_and_versioned(self):
        parent = uuid.UUID("31e82c7a-97fb-4adf-a880-041f9c44b00a")
        self.assertEqual(derived_result_id(parent), derived_result_id(str(parent)))
        self.assertEqual(MATCH_METHOD, "locationiq_postcode_reference_v1")
        self.assertEqual(RULESET, "uk-postcode-reference-v1")

    def test_migration_binds_parent_retained_context_and_approximate_cache(self):
        sql = MIGRATION.read_text(encoding="utf-8")
        for fragment in (
            "to_regnamespace('real_preview') IS NULL",
            "locationiq_uk_postcode_point",
            "item->>'class' IS DISTINCT FROM 'place'",
            "item->>'type' IS DISTINCT FROM 'postcode'",
            "parent.response->'results' IS DISTINCT FROM NEW.response->'results'",
            "target.snapshot_sha256=candidate.snapshot_sha256",
            "candidate.default_map_scope",
            "candidate.display_latitude IS NULL AND candidate.display_longitude IS NULL",
            "queued.details->>'first_pass_only'='true'",
            "locationiq_first_pass_context_audit",
            "provider_locality_approximate",
            "approximate_provider_locality_private_display",
            "locationiq_postcode_reference_v1",
            "coordinate_confidence_band IS NULL",
            "WHEN result_method='locationiq_postcode_reference_v1' THEN NULL",
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, sql)
        self.assertNotRegex(sql, r"(?im)^\s*(INSERT|UPDATE|DELETE)\s+uec\.(?:geocode_jobs|geocode_job_events|geocode_request_reservations)\b")
        self.assertNotRegex(sql, r"(?im)^\s*UPDATE\s+(?:uec|real_preview)\.(?:source_records|geocode_results)\b")
        self.assertIn("CREATE OR REPLACE FUNCTION real_preview.sync_geoapify_private_display()", sql)


@unittest.skipUnless(
    os.environ.get("UEC_LOCATIONIQ_FIRST_PASS_SQL_TESTS") == "1"
    and urlsplit(os.environ.get("UEC_DATABASE_URL", "")).path.strip("/")
        == "uec_launch_sources_test_20261025",
    "opt-in checks on the assigned local source database required",
)
class LocationIqPostcodeReferencePostgisTests(unittest.TestCase):
    def setUp(self):
        self.connection = psycopg.connect(os.environ["UEC_DATABASE_URL"])
        self.addCleanup(self.connection.close)
        self.addCleanup(self.connection.rollback)
        self.assertEqual(self.connection.execute("SELECT current_database()").fetchone()[0],
                         "uec_launch_sources_test_20261025")

    def test_python_and_sql_matcher_parity(self):
        cases = [postcode_result(), postcode_result(country="ie"),
                 postcode_result(postcode="SW1A 1AB"), postcode_result(lat="NaN"),
                 postcode_result(lon="-9"), postcode_result(lat=51.5),
                 postcode_result(klass="boundary"), postcode_result(result_type="house")]
        for item in cases:
            with self.subTest(item=item):
                matched = self.connection.execute(
                    "SELECT real_preview.locationiq_uk_postcode_point(%s::jsonb,%s) IS NOT NULL",
                    (json.dumps(item), "SW1A 1AA")).fetchone()[0]
                self.assertEqual(matched, select_postcode_reference({"results": [item]}, "SW1A 1AA") is not None)

    def test_retained_parent_capture_is_approximate_and_rollback_only(self):
        rows = self.connection.execute("""
            SELECT DISTINCT ON (job.job_id)
                   job.source_record_id,job.query,parent.geocode_result_id,
                   parent.response,parent.attempt_number,parent.queried_at
              FROM uec.geocode_jobs job
              JOIN uec.geocode_results parent ON parent.source_record_id=job.source_record_id
               AND parent.provider_id=job.provider_id AND parent.query=job.query
               AND parent.status='review_required'
              JOIN real_preview.geocode_targets target ON target.job_id=job.job_id
              JOIN real_preview.candidates candidate USING(candidate_id)
             WHERE job.provider_id='locationiq' AND candidate.country_code='GB'
               AND candidate.source_id IN ('fsa_approved_establishments','fss_approved_establishments')
               AND (candidate.display_latitude IS NULL
                    OR candidate.coordinate_method='locationiq_postcode_reference_v1')
               AND EXISTS (SELECT 1 FROM uec.geocode_job_events queued
                   WHERE queued.job_id=job.job_id AND queued.event_type='queued'
                     AND queued.details->>'first_pass_only'='true')
             ORDER BY job.job_id,parent.queried_at DESC LIMIT 100
        """).fetchall()
        for source, query, parent_id, response, attempt, queried_at in rows:
            selected = select_postcode_reference(response, json.loads(query).get("postcode"))
            if selected:
                break
        else:
            self.fail("retained unmapped UK postcode parent required for acceptance test")
        audit_sql = """WITH jobs AS (SELECT job_id FROM uec.geocode_jobs
            WHERE source_record_id=%s AND query=%s AND provider_id='locationiq')
            SELECT (SELECT count(*) FROM uec.geocode_request_reservations JOIN jobs USING(job_id)),
                   (SELECT count(*) FROM uec.geocode_job_events JOIN jobs USING(job_id))"""
        before = self.connection.execute(audit_sql, (source,query)).fetchone()
        index, latitude, longitude = selected
        derived = copy.deepcopy(response)
        derived.update(_uec_parent_geocode_result_id=str(parent_id),
                       _uec_ruleset_version=RULESET, _uec_selected_result_index=index,
                       _uec_offline_recheck=True)
        parent = dict(source_record_id=source, query=query, attempt_number=attempt, queried_at=queried_at)
        result_id = derived_result_id(parent_id)
        already_exists = self.connection.execute(
            "SELECT 1 FROM uec.geocode_results WHERE geocode_result_id=%s", (result_id,)).fetchone() is not None
        # A forged result list must not be accepted, even with a real parent ID.
        forged = copy.deepcopy(derived)
        forged["results"][index]["lon"] = str(longitude + 0.01)
        with self.assertRaises(psycopg.errors.CheckViolation):
            _append_result(self.connection, parent=parent, result_id=uuid.uuid4(),
                           response=forged, latitude=latitude, longitude=longitude)
        self.assertEqual(_append_result(self.connection, parent=parent, result_id=result_id,
                                       response=derived, latitude=latitude, longitude=longitude),
                         not already_exists)
        self.assertFalse(_append_result(self.connection, parent=parent, result_id=result_id,
                                       response=derived, latitude=latitude, longitude=longitude))
        precision = self.connection.execute("""SELECT DISTINCT evidence.display_precision,
            candidate.coordinate_method,candidate.coordinate_confidence_band,
            result.precision,result.queried_at=parent.queried_at
            FROM real_preview.geocode_display_evidence evidence
            JOIN real_preview.candidates candidate USING(candidate_id)
            JOIN uec.geocode_results result USING(geocode_result_id)
            JOIN uec.geocode_results parent ON parent.geocode_result_id=%s
            WHERE result.geocode_result_id=%s""", (parent_id,result_id)).fetchall()
        self.assertEqual(precision, [("provider_locality_approximate", MATCH_METHOD, None,
                                     "locationiq_postcode_point", True)])
        after = self.connection.execute(audit_sql, (source,query)).fetchone()
        self.assertEqual(after, before)
        self.connection.rollback()
        persisted = self.connection.execute(
            "SELECT 1 FROM uec.geocode_results WHERE geocode_result_id=%s", (result_id,)).fetchone() is not None
        self.assertEqual(persisted, already_exists)


if __name__ == "__main__":
    unittest.main()
