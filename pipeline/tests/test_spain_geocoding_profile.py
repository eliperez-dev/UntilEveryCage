import unittest
from pathlib import Path

from pipeline.geocoding.geoapify import GeoapifyAdapter


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
        ):
            with self.subTest(required=required):
                self.assertIn(required, sql)
        self.assertNotIn("DROP TABLE", sql.upper())
        self.assertNotIn("DROP TRIGGER", sql.upper())

    def test_accent_normalization_preserves_numeric_and_street_tokens(self):
        self.assertEqual(GeoapifyAdapter._normalize("10 Calle de la Constitución"),
                         GeoapifyAdapter._normalize("10 Calle de la Constitucion"))
        self.assertNotEqual(GeoapifyAdapter._normalize("10 Calle de la Constitución"),
                            GeoapifyAdapter._normalize("11 Calle de la Constitución"))
        self.assertNotEqual(GeoapifyAdapter._normalize("10 Calle de la Constitución"),
                            GeoapifyAdapter._normalize("10 Avenida de la Constitución"))


if __name__ == "__main__":
    unittest.main()
