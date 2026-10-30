import unittest
from pathlib import Path

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

if __name__ == "__main__":
    unittest.main()
