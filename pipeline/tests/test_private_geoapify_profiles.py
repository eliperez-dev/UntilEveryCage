import importlib.util
import unittest
from unittest.mock import patch
from pathlib import Path
import json
import tempfile

from pipeline.geocoding import private_profiles
from pipeline.geocoding.private_profiles import profile_by_id, profile_for_source
from pipeline.geocoding.registry import get_adapter


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
        self.assertEqual(profile_for_source("es.locations")["country_code"], "ES")
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

    def test_spain_profile_queues_only_eligible_address_evidence_without_source_coordinates(self):
        profile = profile_for_source("es.locations")
        base = {"country_code": "ES", "source_scope_eligibility": "eligible",
                "privacy_gate": "restricted-private-evidence", "coordinate_state": "not-supplied"}
        location = {"country_code": "ES", "address": "Synthetic industrial address"}
        self.assertTrue(IMPORTER.private_geocode_queue_eligible(
            "es.locations", base, location, "unmapped_private_observation", profile))
        self.assertFalse(IMPORTER.private_geocode_queue_eligible(
            "es.locations", {**base, "source_scope_eligibility": "out_of_scope"},
            location, "unmapped_private_observation", profile))
        self.assertFalse(IMPORTER.private_geocode_queue_eligible(
            "es.locations", {**base, "country_code": "PT"}, location,
            "unmapped_private_observation", profile))
        self.assertFalse(IMPORTER.private_geocode_queue_eligible(
            "es.locations", base, {}, "unmapped_private_observation", profile))
        self.assertFalse(IMPORTER.private_geocode_queue_eligible(
            "es.locations", base, location, "numeric_source_coordinate", profile))

    def test_spain_private_profile_builds_country_filtered_geoapify_adapter(self):
        with patch.dict("os.environ", {"GEOAPIFY_API_KEY": "synthetic-test-key"}):
            adapter = get_adapter("geoapify", private_source_profile_id="geoapify-es-aesan-rgseaa")
        self.assertEqual(adapter.country_code, "es")
        self.assertTrue(adapter.private_source_profile)
        self.assertTrue(adapter.strict_matching)
        self.assertFalse(adapter.locality_only)
        self.assertFalse(adapter.allow_locality_match)

    def test_spain_municipality_profile_is_explicit_and_keeps_address_default(self):
        address = profile_for_source("es.locations")
        municipality = profile_by_id("geoapify-es-aesan-verified-municipality")
        self.assertEqual(address["profile_id"], "geoapify-es-aesan-rgseaa")
        self.assertEqual(municipality["query_kind"], "verified_municipality_only")
        with patch.dict("os.environ", {"GEOAPIFY_API_KEY": "synthetic-test-key"}):
            adapter = get_adapter("geoapify", private_source_profile_id=municipality["profile_id"])
        self.assertEqual(adapter.country_code, "es")
        self.assertTrue(adapter.locality_only)
        self.assertTrue(adapter.municipality_only)

    def test_profile_registry_rejects_duplicate_non_spain_and_invalid_spain_profiles(self):
        original = json.loads(private_profiles.PROFILE_PATH.read_text(encoding="utf-8"))
        duplicate = original["profiles"][0]
        cases = (
            original["profiles"] + [{**duplicate, "profile_id": "synthetic-duplicate-source"}],
            [row for row in original["profiles"] if row["profile_id"] != "geoapify-es-aesan-verified-municipality"]
            + [{"profile_id": "geoapify-es-aesan-verified-municipality", "source_id": "es.locations",
               "country_code": "PT", "query_kind": "verified_municipality_only", "status": "enabled-private-only"}],
            [row for row in original["profiles"] if row["profile_id"] != "geoapify-es-aesan-verified-municipality"]
            + [{"profile_id": "geoapify-es-aesan-rgseaa-extra", "source_id": "es.locations",
               "country_code": "ES", "status": "enabled-private-only"}],
            [row for row in original["profiles"] if row["profile_id"] != "geoapify-es-aesan-verified-municipality"]
            + [{"profile_id": "geoapify-es-aesan-verified-municipality", "source_id": "de.locations",
               "country_code": "DE", "query_kind": "verified_municipality_only", "status": "enabled-private-only"}],
            [row for row in original["profiles"] if row["source_id"] != "es.locations"]
            + [{"profile_id": "geoapify-es-aesan-verified-municipality", "source_id": "es.locations",
               "country_code": "ES", "query_kind": "verified_municipality_only", "status": "enabled-private-only"}],
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profiles.json"
            for rows in cases:
                with self.subTest(count=len(rows)):
                    path.write_text(json.dumps({**original, "profiles": rows}), encoding="utf-8")
                    with patch.object(private_profiles, "PROFILE_PATH", path):
                        with self.assertRaises(ValueError):
                            private_profiles.profiles()

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
