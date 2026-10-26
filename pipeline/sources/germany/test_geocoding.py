import os
import hashlib
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

import psycopg
from psycopg.types.json import Jsonb

from pipeline.geocoding.private_profiles import profile_by_id, profile_for_source
from pipeline.geocoding.registry import get_adapter


class GermanyPrivateGeocodingTests(unittest.TestCase):
    def test_profile_is_country_and_source_scoped_private_only(self):
        profile = profile_for_source("de.locations")
        self.assertEqual(profile["profile_id"], "geoapify-de-bltu")
        self.assertEqual(profile["country_code"], "DE")
        self.assertEqual(profile["status"], "enabled-private-only")
        self.assertNotIn("facility name", profile["source_scope"])
        self.assertEqual(profile_by_id("geoapify-de-bltu"), profile)

    def test_profile_adapter_applies_germany_filter_without_ip_bias(self):
        with patch.dict(os.environ, {"GEOAPIFY_API_KEY": "synthetic-test-key"}):
            adapter = get_adapter("geoapify", private_source_profile_id="geoapify-de-bltu")
        self.assertEqual(adapter.country_code, "de")
        self.assertTrue(adapter.private_source_profile)
        self.assertTrue(adapter.strict_matching)

    def test_activation_cli_defaults_to_repeatable_full_cohort_batches(self):
        path = Path(__file__).parents[2] / "scripts" / "stages" / "activate-de-bltu-geoapify.py"
        spec = importlib.util.spec_from_file_location("de_geoapify_activator_test", path)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)
        self.assertGreaterEqual(module.DEFAULT_BATCH_SIZE, 500)

    @unittest.skipUnless(
        os.environ.get("UEC_GERMANY_REAL_DATA_ACCEPTANCE") == "true"
        and os.environ.get("UEC_DATABASE_URL"),
        "set UEC_GERMANY_REAL_DATA_ACCEPTANCE=true with the assigned private DB URL",
    )
    def test_database_display_bridge_positive_and_negative_cases_rollback(self):
        connection = psycopg.connect(os.environ["UEC_DATABASE_URL"], connect_timeout=15)
        try:
            connection.execute("SET statement_timeout='20000ms'")
            self.assertEqual(connection.execute("SELECT current_database()").fetchone()[0],
                             "uec_launch_sources_test_20261025")
            profile = connection.execute(
                """SELECT count(*) FROM real_preview.private_geocoding_source_profiles
                    WHERE profile_id='geoapify-de-bltu' AND source_id='de.locations'
                      AND country_code='DE' AND enabled"""
            ).fetchone()[0]
            self.assertEqual(profile, 1)
            other_profiles = connection.execute(
                """SELECT array_agg(profile_id || ':' || country_code::text ORDER BY profile_id)
                     FROM real_preview.private_geocoding_source_profiles
                    WHERE profile_id <> 'geoapify-de-bltu'"""
            ).fetchone()[0]
            self.assertEqual(other_profiles, [
                "geoapify-dk-smiley:DK", "geoapify-es-aesan-rgseaa:ES",
                "geoapify-es-aesan-verified-municipality:ES",
                "geoapify-gb-fsa-approved-establishments:GB",
                "geoapify-gb-fss-approved-establishments:GB",
                "geoapify-nl-nvwa-approved-food:NL",
                "geoapify-us-aphis-mailing-locality:US",
            ])
            shared_function = connection.execute(
                "SELECT pg_get_functiondef('real_preview.capture_geoapify_private_display()'::regprocedure)"
            ).fetchone()[0]
            german_join = "ON profile.source_id = candidate.source_id AND profile.enabled AND profile.profile_id <> 'geoapify-de-bltu'"
            generic_join = "ON profile.source_id = candidate.source_id AND profile.enabled"
            self.assertEqual(shared_function.count(german_join), 1)
            prior_shared_function = shared_function.replace(german_join, generic_join)
            self.assertEqual(hashlib.md5(prior_shared_function.encode("utf-8"), usedforsecurity=False).hexdigest(),
                             "3a11e2f75ee9bd2adefae58c0f50aebf")
            self.assertEqual(connection.execute("""
                SELECT real_preview.normalize_germany_state('Bayern') = real_preview.normalize_germany_state('DE-BY'),
                       real_preview.normalize_germany_state('Bayern') <> real_preview.normalize_germany_state('DE-BB')
            """).fetchone(), (True, True))

            target = connection.execute("""
                SELECT placeholder.source_record_id,placeholder.query,candidate.candidate_id,
                       private_location.location_evidence->>'address',
                       COALESCE(private_location.location_evidence->>'postal_code',
                           (regexp_match(private_location.location_evidence->>'city','^([0-9]{5})[[:space:]]+'))[1]),
                       regexp_replace(private_location.location_evidence->>'city','^[0-9]{5}[[:space:]]+',''),
                       private_location.location_evidence->>'region'
                  FROM real_preview.candidates candidate
                  JOIN real_preview.candidate_private_location_evidence private_location USING(candidate_id)
                  JOIN real_preview.source_preview_runs run
                    ON run.source_id=candidate.source_id AND run.snapshot_sha256=candidate.snapshot_sha256
                  JOIN real_preview.geocode_targets existing_target
                    ON existing_target.candidate_id=candidate.candidate_id
                  JOIN uec.geocode_jobs placeholder
                    ON placeholder.job_id=existing_target.job_id
                   AND placeholder.provider_id='geoapify'
                  JOIN uec.geocode_job_events queued ON queued.job_id=placeholder.job_id
                   AND queued.event_type='queued'
                 WHERE candidate.source_id='de.locations' AND candidate.country_code='DE'
                   AND candidate.snapshot_sha256=(SELECT current_run.snapshot_sha256
                       FROM real_preview.source_preview_runs current_run
                       WHERE current_run.source_id='de.locations'
                       ORDER BY current_run.created_at DESC,current_run.run_id DESC LIMIT 1)
                   AND private_location.location_evidence->>'country_code'='DE'
                   AND NULLIF(BTRIM(private_location.location_evidence->>'address'),'') IS NOT NULL
                   AND private_location.location_evidence->>'address' ~ 'ß'
                   AND COALESCE(private_location.location_evidence->>'postal_code',
                       (regexp_match(private_location.location_evidence->>'city','^([0-9]{5})[[:space:]]+'))[1]) ~ '^[0-9]{5}$'
                   AND NOT EXISTS(SELECT 1 FROM uec.public_access_restricted restricted
                                  WHERE restricted.source_record_id=placeholder.source_record_id)
                 ORDER BY candidate.candidate_id LIMIT 1
            """).fetchone()
            self.assertIsNotNone(target)
            source_record_id, query, candidate_id, source_address, source_postcode, source_city, source_region = target
            self.assertIsNotNone(source_address)
            self.assertIsNotNone(source_postcode)
            self.assertIsNotNone(source_city)
            self.assertIsNotNone(source_region)
            connection.execute("SAVEPOINT de_bridge_cases")
            wrong_state = connection.execute(
                """SELECT CASE WHEN real_preview.normalize_germany_state(%s) = real_preview.normalize_germany_state('DE-BB')
                               THEN 'DE-BY' ELSE 'DE-BB' END""",
                (source_region,),
            ).fetchone()[0]

            def feature(address=source_address, country="DE", confidence=0.96,
                        postcode=source_postcode, city=source_city, state=source_region):
                return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [10.0, 51.0]},
                        "properties": {"place_id": "rollback-acceptance", "result_type": "building",
                                       "country_code": country, "address_line1": address,
                                       "postcode": postcode, "city": city, "state": state,
                                       "rank": {"confidence": confidence}}}

            cases = (
                ("positive", [feature()], 1),
                ("wrong_country", [feature(country="AT")], 0),
                ("wrong_address", [feature(address="Diagnostic Different Street 998")], 0),
                ("wrong_postcode", [feature(postcode="00000")], 0),
                ("wrong_locality", [feature(city="Different Town")], 0),
                ("wrong_state", [feature(state=wrong_state)], 0),
                ("ambiguous", [feature(), feature()], 0),
                ("low_confidence", [feature(confidence=0.89)], 0),
            )
            observed = []
            try:
                for label, features, expected in cases:
                    connection.execute("SAVEPOINT de_bridge_case")
                    response = {"type": "FeatureCollection", "features": features,
                                "_uec_selected_feature_index": 0}
                    result_id = connection.execute("""
                        INSERT INTO uec.geocode_results
                            (source_record_id,provider_id,provider_version,query,provider_address_id,result,
                             precision,match_method,status,attempt_number,retryable,response,queried_at)
                        VALUES (%s,'geoapify','de-rollback-acceptance',%s,'rollback-address',
                                ST_SetSRID(ST_MakePoint(10.0,51.0),4326)::geography,
                                'building','geoapify_forward','accepted',1,false,%s,now())
                        RETURNING geocode_result_id
                    """, (source_record_id, query, Jsonb(response))).fetchone()[0]
                    actual = connection.execute(
                        "SELECT count(*) FROM real_preview.geocode_display_evidence WHERE candidate_id=%s AND geocode_result_id=%s",
                        (candidate_id, result_id),
                    ).fetchone()[0]
                    observed.append((label, actual, expected))
                    if label == "positive":
                        shown = connection.execute(
                            "SELECT display_latitude,display_longitude FROM real_preview.candidate_display WHERE candidate_id=%s",
                            (candidate_id,),
                        ).fetchone()
                        self.assertEqual(shown, (51.0, 10.0))
                    connection.execute("ROLLBACK TO SAVEPOINT de_bridge_case")
                    connection.execute("RELEASE SAVEPOINT de_bridge_case")
                self.assertEqual(observed, [(label, expected, expected) for label, _, expected in cases])
            finally:
                connection.rollback()

            persisted = connection.execute(
                "SELECT count(*) FROM uec.geocode_results WHERE provider_version='de-rollback-acceptance'"
            ).fetchone()[0]
            self.assertEqual(persisted, 0)
        finally:
            connection.rollback()
            connection.close()


if __name__ == "__main__":
    unittest.main()
