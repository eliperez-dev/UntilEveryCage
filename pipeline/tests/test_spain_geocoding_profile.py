import unittest
import hashlib
import os
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

from pipeline.geocoding.geoapify import GeoapifyAdapter
from pipeline.sources.spain_rgseaa.municipality_activation import verified_municipality_query


ROOT = Path(__file__).parents[1]


class SpainGeocodingProfileTests(unittest.TestCase):
    def test_spain_profile_migration_is_private_and_address_exact(self):
        sql = (ROOT / "migrations/090_spain_private_geocoding_profile.sql").read_text(encoding="utf-8")
        for required in (
            "to_regnamespace('real_preview') IS NULL",
            "'geoapify-es-aesan-rgseaa', 'es.locations', 'ES'",
            "country_code IN ('GB','DK','NL','US','ES')",
            "profile.profile_id = 'geoapify-es-aesan-rgseaa'",
            "candidate.source_id = 'es.locations'",
            "feature->'properties'->>'housenumber'",
            "viable_match_count <> 1",
            "confidence_score < .90",
            "result_type NOT IN ('building','amenity')",
            "public_access_restricted",
            "capture_spain_geoapify_private_display",
            "geocode_results_spain_geoapify_private_display",
        ):
            with self.subTest(required=required):
                self.assertIn(required, sql)
        self.assertNotIn("DROP TABLE", sql.upper())
        self.assertNotIn("CREATE OR REPLACE FUNCTION REAL_PREVIEW.CAPTURE_GEOAPIFY_PRIVATE_DISPLAY", sql.upper())
        self.assertNotIn("DROP TRIGGER GEOCODE_RESULTS_GEOAPIFY_PREVIEW_DISPLAY", sql.upper())

    def test_accent_normalization_preserves_numeric_and_street_tokens(self):
        self.assertEqual(GeoapifyAdapter._normalize("10 Calle de la Constitución"),
                         GeoapifyAdapter._normalize("10 Calle de la Constitucion"))
        self.assertNotEqual(GeoapifyAdapter._normalize("10 Calle de la Constitución"),
                            GeoapifyAdapter._normalize("11 Calle de la Constitución"))
        self.assertNotEqual(GeoapifyAdapter._normalize("10 Calle de la Constitución"),
                            GeoapifyAdapter._normalize("10 Avenida de la Constitución"))

    def test_verified_municipality_query_contains_only_three_unambiguous_components(self):
        self.assertEqual(verified_municipality_query("  Albarracín ", " Teruel  "),
                         "Albarracín, Teruel, Spain")
        for municipality, province in (("", "Teruel"), ("Albarracín", ""),
                                       ("Town, Address", "Teruel"), ("Town", "Province, Region")):
            with self.subTest(municipality=bool(municipality), province=bool(province)):
                with self.assertRaises(ValueError):
                    verified_municipality_query(municipality, province)

    def test_spain_municipality_migration_is_separate_strict_and_city_precision_only(self):
        sql = (ROOT / "migrations/094_spain_verified_municipality_geocoding.sql").read_text(encoding="utf-8")
        for required in (
            "private_geocoding_source_profiles_one_non_es_profile",
            "source_id <> 'es.locations'",
            "private_geocoding_source_profiles_spain_profile_scope",
            "geoapify-es-aesan-verified-municipality",
            "spain_verified_locality_evidence",
            "result_type <> 'city'",
            "confidence_score < .90",
            "properties->>'county'",
            "query_parts[3]) <> 'spain'",
            "provider_locality_approximate",
            "approximate municipality point, not facility coordinates",
            "CREATE TRIGGER geocode_results_spain_verified_municipality_display",
        ):
            with self.subTest(required=required):
                self.assertIn(required, sql)
        self.assertNotIn("capture_geoapify_private_display()", sql)
        self.assertNotIn("DROP TRIGGER GEOCODE_RESULTS_GEOAPIFY_PREVIEW_DISPLAY", sql.upper())

    @unittest.skipUnless(
        os.environ.get("UEC_SPAIN_REAL_DATA_ACCEPTANCE") == "true"
        and os.environ.get("UEC_DATABASE_URL"),
        "set UEC_SPAIN_REAL_DATA_ACCEPTANCE=true with the assigned private DB URL",
    )
    def test_database_display_bridge_positive_and_negative_cases_rollback(self):
        with psycopg.connect(os.environ["UEC_DATABASE_URL"]) as connection:
            database = connection.execute("SELECT current_database()").fetchone()[0]
            self.assertEqual(database, "uec_launch_sources_test_20261025")
            applied = connection.execute(
                "SELECT count(*) FROM uec.schema_migrations WHERE version='091_spain_private_geocoding_address_expression'"
            ).fetchone()[0]
            self.assertEqual(applied, 1)
            profile_count = connection.execute(
                "SELECT count(*) FROM real_preview.private_geocoding_source_profiles WHERE profile_id='geoapify-es-aesan-rgseaa' AND source_id='es.locations' AND country_code='ES' AND enabled"
            ).fetchone()[0]
            self.assertEqual(profile_count, 1)
            retained_countries = connection.execute(
                "SELECT array_agg(country_code::text ORDER BY country_code::text) FROM real_preview.private_geocoding_source_profiles WHERE source_id <> 'es.locations'"
            ).fetchone()[0]
            self.assertEqual(retained_countries, ["DE", "DK", "GB", "GB", "NL", "US"])
            shared_function = connection.execute(
                "SELECT pg_get_functiondef('real_preview.capture_geoapify_private_display()'::regprocedure)"
            ).fetchone()[0]
            self.assertEqual(hashlib.md5(shared_function.encode("utf-8"), usedforsecurity=False).hexdigest(),
                             "3a11e2f75ee9bd2adefae58c0f50aebf")
            shared_trigger = connection.execute(
                "SELECT count(*) FROM pg_trigger WHERE tgrelid='uec.geocode_results'::regclass AND tgname='geocode_results_geoapify_preview_display' AND NOT tgisinternal"
            ).fetchone()[0]
            self.assertEqual(shared_trigger, 1)

            source_record_id, query, candidate_id, source_address = connection.execute("""
                SELECT job.source_record_id,job.query,target.candidate_id,
                       coalesce(location.location_evidence->>'address',location.location_evidence->'address_lines'->>0)
                  FROM uec.geocode_job_current job
                  JOIN uec.source_records source USING(source_record_id)
                  JOIN real_preview.geocode_targets target ON target.job_id=job.job_id
                  JOIN real_preview.candidates candidate ON candidate.candidate_id=target.candidate_id
                  JOIN real_preview.candidate_private_location_evidence location ON location.candidate_id=candidate.candidate_id
                 WHERE source.source_id='es.locations' AND job.provider_id='geoapify' AND job.event_type='queued'
                   AND job.details->>'processing_mode'='private_geoapify_source_profile'
                   AND job.details->>'profile_id'='geoapify-es-aesan-rgseaa'
                   AND candidate.source_id='es.locations' AND candidate.country_code='ES'
                   AND location.location_evidence->>'country_code'='ES'
                   AND coalesce(location.location_evidence->>'address',location.location_evidence->'address_lines'->>0) IS NOT NULL
                   AND NOT EXISTS(SELECT 1 FROM uec.public_access_restricted restricted WHERE restricted.source_record_id=job.source_record_id)
                 LIMIT 1
            """).fetchone()
            self.assertTrue(source_address)

            def feature(address=source_address, country="ES", confidence=0.96):
                return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [-3.7, 40.4]},
                        "properties": {"place_id": "rollback-acceptance", "result_type": "building",
                                       "country_code": country, "address_line1": address,
                                       "rank": {"confidence": confidence}}}

            cases = (
                ("positive", [feature()], 1),
                ("wrong_country", [feature(country="PT")], 0),
                ("wrong_address_number_and_street", [feature(address="Diagnostic Different Street 998")], 0),
                ("ambiguous", [feature(), feature()], 0),
                ("low_confidence", [feature(confidence=0.89)], 0),
            )
            observed = []
            try:
                for label, features, expected in cases:
                    connection.execute("SAVEPOINT spain_bridge_case")
                    response = {"type": "FeatureCollection", "features": features,
                                "_uec_selected_feature_index": 0}
                    result_id = connection.execute("""
                        INSERT INTO uec.geocode_results
                            (source_record_id,provider_id,provider_version,query,provider_address_id,result,
                             precision,match_method,status,attempt_number,retryable,response,queried_at)
                        VALUES (%s,'geoapify','spain-rollback-acceptance',%s,'rollback-address',
                                ST_GeogFromText('SRID=4326;POINT(-3.7 40.4)'), 'building','geoapify_forward',
                                'accepted',1,false,%s,now())
                        RETURNING geocode_result_id
                    """, (source_record_id, query, Jsonb(response))).fetchone()[0]
                    actual = connection.execute(
                        "SELECT count(*) FROM real_preview.geocode_display_evidence WHERE candidate_id=%s AND geocode_result_id=%s",
                        (candidate_id, result_id),
                    ).fetchone()[0]
                    observed.append((label, actual, expected))
                    connection.execute("ROLLBACK TO SAVEPOINT spain_bridge_case")
                    connection.execute("RELEASE SAVEPOINT spain_bridge_case")
                self.assertEqual(observed, [(label, expected, expected) for label, _, expected in cases])
            finally:
                connection.rollback()

            persisted = connection.execute(
                "SELECT count(*) FROM uec.geocode_results WHERE provider_version='spain-rollback-acceptance'"
            ).fetchone()[0]
            self.assertEqual(persisted, 0)


if __name__ == "__main__":
    unittest.main()
