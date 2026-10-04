import importlib.util
import unittest
from pathlib import Path

from pipeline.geocoding.private_profiles import profile_by_id, profile_for_source


ROOT = Path(__file__).parents[1]
IMPORTER_PATH = ROOT / "scripts/maintenance/import-real-preview.py"
SPEC = importlib.util.spec_from_file_location("private_profile_importer", IMPORTER_PATH)
IMPORTER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(IMPORTER)


class PrivateGeoapifyProfileTests(unittest.TestCase):
    def test_only_enabled_source_profiles_are_resolvable(self):
        self.assertEqual(profile_for_source("fsa_approved_establishments")["country_code"], "GB")
        self.assertEqual(profile_for_source("fss_approved_establishments")["country_code"], "GB")
        self.assertEqual(profile_for_source("dk.smiley")["country_code"], "DK")
        self.assertEqual(profile_for_source("nl.nvwa.approved-food")["country_code"], "NL")
        self.assertIsNone(profile_for_source("unknown.source"))
        self.assertEqual(profile_by_id("geoapify-gb-fss-approved-establishments")["source_id"],
                         "fss_approved_establishments")

    def test_queue_gate_requires_source_country_location_and_eligibility(self):
        profile = profile_for_source("fss_approved_establishments")
        base = {"country_code": "GB", "privacy_gate": "privacy-review-required"}
        location = {"country_code": "GB", "address_lines": ["Industrial Road"]}
        self.assertTrue(IMPORTER.private_geocode_queue_eligible(
            "fss_approved_establishments", base, location, "unmapped_private_observation", profile))
        self.assertFalse(IMPORTER.private_geocode_queue_eligible(
            "other.source", base, location, "unmapped_private_observation", profile))
        self.assertFalse(IMPORTER.private_geocode_queue_eligible(
            "fss_approved_establishments", {**base, "country_code": "IE"}, location,
            "unmapped_private_observation", profile))
        self.assertFalse(IMPORTER.private_geocode_queue_eligible(
            "fss_approved_establishments", {**base, "privacy_gate": "restricted-withheld-address"},
            location, "unmapped_private_observation", profile))
        self.assertFalse(IMPORTER.private_geocode_queue_eligible(
            "fss_approved_establishments", {**base, "source_scope_eligibility": "excluded"},
            location, "unmapped_private_observation", profile))
        self.assertFalse(IMPORTER.private_geocode_queue_eligible(
            "fss_approved_establishments", base, {}, "unmapped_private_observation", profile))
        self.assertFalse(IMPORTER.private_geocode_queue_eligible(
            "fss_approved_establishments", base, location, "numeric_source_coordinate", profile))

    def test_fsa_and_nvwa_profiles_apply_their_source_country_and_restriction_gates(self):
        fsa = profile_for_source("fsa_approved_establishments")
        fsa_base = {"country_code": "GB", "privacy_gate": "privacy-review-required"}
        fsa_location = {"country_code": "GB", "address_lines": ["Synthetic Industrial Road"]}
        self.assertTrue(IMPORTER.private_geocode_queue_eligible(
            "fsa_approved_establishments", fsa_base, fsa_location,
            "city_postal", fsa))
        self.assertFalse(IMPORTER.private_geocode_queue_eligible(
            "fsa_approved_establishments", {**fsa_base, "privacy_gate": "restricted-withheld-address"},
            fsa_location, "city_postal", fsa))

        nvwa = profile_for_source("nl.nvwa.approved-food")
        nvwa_base = {"country_code": "NL", "privacy_gate": "pending",
                     "source_scope_eligibility": "eligible"}
        nvwa_location = {"country_code": "NL", "address_lines": ["Synthetic Source Road"]}
        self.assertTrue(IMPORTER.private_geocode_queue_eligible(
            "nl.nvwa.approved-food", nvwa_base, nvwa_location,
            "city_postal", nvwa))
        self.assertFalse(IMPORTER.private_geocode_queue_eligible(
            "nl.nvwa.approved-food", {**nvwa_base, "country_code": "GB"},
            nvwa_location, "city_postal", nvwa))
        self.assertFalse(IMPORTER.private_geocode_queue_eligible(
            "nl.nvwa.approved-food", {**nvwa_base, "source_scope_eligibility": "excluded"},
            nvwa_location, "city_postal", nvwa))

    def test_denmark_requires_exact_policy_core_category_and_explicit_source_eligibility(self):
        profile = profile_for_source("dk.smiley")
        base = {
            "country_code": "DK", "privacy_gate": "pending", "coordinates": None,
            "private_geocode_scope": "animal_product_production_and_processing",
            "private_geocode_scope_policy_id": "denmark-private-geocode-scope-v1",
            "classification_optional_filter": "production-and-processing",
            "classification_review_status": "approved",
            "activity_categories": ["slaughter"],
            "source_address_eligible": True,
        }
        location = {"country_code": "DK", "address": "Synthetic Road 1",
                    "address_lines": ["Synthetic Road 1"]}
        eligible = IMPORTER.private_geocode_queue_eligible(
            "dk.smiley", base, location, "unmapped_private_observation", profile)
        self.assertTrue(eligible)

        self.assertFalse(IMPORTER.private_geocode_queue_eligible(
            "dk.smiley", {**base, "private_geocode_scope": "out_of_scope"},
            location, "unmapped_private_observation", profile))
        self.assertFalse(IMPORTER.private_geocode_queue_eligible(
            "dk.smiley", {**base, "private_geocode_scope_policy_id": "other-policy"},
            location, "unmapped_private_observation", profile))
        self.assertFalse(IMPORTER.private_geocode_queue_eligible(
            "dk.smiley", {**base, "activity_categories": ["general_food_business"]},
            location, "unmapped_private_observation", profile))
        self.assertFalse(IMPORTER.private_geocode_queue_eligible(
            "dk.smiley", {**base, "source_address_eligible": False},
            location, "unmapped_private_observation", profile))
        self.assertFalse(IMPORTER.private_geocode_queue_eligible(
            "dk.smiley", {**base, "source_address_restricted": True},
            location, "unmapped_private_observation", profile))
        self.assertFalse(IMPORTER.private_geocode_queue_eligible(
            "dk.smiley", {**base, "coordinates": {"latitude": 56.0, "longitude": 10.0}},
            location, "unmapped_private_observation", profile))
        self.assertFalse(IMPORTER.private_geocode_queue_eligible(
            "dk.smiley", {key: value for key, value in base.items()
                          if key != "source_address_eligible"},
            location, "unmapped_private_observation", profile))

    def test_migration_contains_private_only_source_country_match_and_restriction_gates(self):
        sql = (ROOT / "migrations/060_private_geoapify_source_profiles.sql").read_text(encoding="utf-8")
        for required in (
            "CREATE TABLE real_preview.private_geocoding_source_profiles",
            "profile.country_code = candidate.country_code",
            "profile.source_id = candidate.source_id",
            "queued.details->>'processing_mode' = 'private_geoapify_source_profile'",
            "queued.details->>'profile_id' = profile.profile_id",
            "FROM uec.public_access_restricted restricted",
            "viable_match_count <> 1",
            "confidence_score < 0.90",
            "private preview only",
        ):
            with self.subTest(required=required):
                self.assertIn(required, sql)


if __name__ == "__main__":
    unittest.main()
