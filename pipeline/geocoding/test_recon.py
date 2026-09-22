import json
import tempfile
import unittest
from pathlib import Path

from pipeline.contracts.geocoding_profile import (
    GeocodingProfileError,
    build_recon_report,
    rank_sources,
    validate_profile,
    validate_profiles,
)
from pipeline.geocoding.recon import build_geocoding_recon, load_profile_registry


ROOT = Path(__file__).parents[2]


class GeocodingProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = json.loads((ROOT / "pipeline/geocoding/profiles.json").read_text(encoding="utf-8"))
        cls.source_registry = json.loads((ROOT / "pipeline/source_registry.json").read_text(encoding="utf-8-sig"))
        cls.status_registry = json.loads((ROOT / "docs/source-status.json").read_text(encoding="utf-8-sig"))
        cls.known_ids = {item["source_id"] for item in cls.source_registry["sources"]}

    def test_checked_in_profiles_validate_and_reference_existing_registry_ids(self):
        validate_profiles(self.payload, known_source_ids=self.known_ids)
        self.assertEqual(len(self.payload["profiles"]), 6)
        self.assertEqual(self.payload["global_fallback_policy"]["default_candidate_provider"], "global.nominatim-self-hosted")
        discovery_ids = {
            item["provider_id"] for item in self.payload["global_fallback_policy"]["provider_discovery_catalog"]
        }
        self.assertTrue(
            {"global.opencage", "global.stadia", "global.locationiq", "global.geoapify", "global.nominatim-public"}
            .issubset(discovery_ids)
        )

    def test_profile_rejects_publication_or_private_query_boundary(self):
        profile = json.loads(json.dumps(self.payload["profiles"][0]))
        profile["publication_boundary"] = "approved-for-release"
        with self.assertRaises(GeocodingProfileError):
            validate_profile(profile, known_source_ids=self.known_ids)
        profile = json.loads(json.dumps(self.payload["profiles"][0]))
        profile["query_minimization"]["private_record_network_authorized"] = True
        with self.assertRaises(GeocodingProfileError):
            validate_profile(profile, known_source_ids=self.known_ids)

    def test_profile_rejects_payload_shaped_fields(self):
        profile = json.loads(json.dumps(self.payload["profiles"][0]))
        profile["providers"][0]["raw_response"] = {"unexpected": True}
        with self.assertRaises(GeocodingProfileError):
            validate_profile(profile, known_source_ids=self.known_ids)

    def test_fallback_order_is_explicit_and_global_candidates_are_present(self):
        for profile in self.payload["profiles"]:
            self.assertEqual([item["state"] for item in profile["fallback_chain"]], ["exact", "coarse", "restricted", "unmapped"])
            provider_ids = {item["provider_id"] for item in profile["providers"]}
            self.assertTrue({"global.nominatim-self-hosted", "global.pelias-self-hosted"}.issubset(provider_ids))

    def test_ranking_is_deterministic_and_tie_breaks_by_source_id(self):
        first = rank_sources(self.source_registry, self.status_registry, self.payload["profiles"])
        second = rank_sources(self.source_registry, self.status_registry, list(reversed(self.payload["profiles"])))
        self.assertEqual(first, second)
        self.assertEqual(first[0]["source_id"], "dk.smiley")
        scores = [item["score"] for item in first]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_report_is_row_free_and_keeps_publication_separate(self):
        report = build_recon_report(self.source_registry, self.status_registry, self.payload)
        self.assertFalse(report["rows_included"])
        self.assertFalse(report["facility_or_address_payloads_included"])
        self.assertIn("dk.smiley", report["deep_tranche"])
        self.assertNotIn("approved-for-release", json.dumps(report))

    def test_integration_build_has_current_source_backlog_and_profile_summaries(self):
        report = build_geocoding_recon()
        self.assertEqual(report["source_count"], 256)
        self.assertEqual(report["profile_count"], 6)
        self.assertEqual(len(report["profile_summaries"]), 6)
        self.assertEqual(report["platform_integration"]["publication_effect"].split(";")[0], "none")

    def test_unknowns_are_explicit_not_empty_guesses(self):
        profile = next(item for item in self.payload["profiles"] if item["country_code"] == "BR")
        self.assertIn(profile["source_coordinate_evidence"][0]["availability"], {"unknown", "not_observed"})
        self.assertTrue(any(token in json.dumps(profile).lower() for token in ("unknown", "not observed", "not verified")))

    def test_loader_rejects_missing_profile_source(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profiles.json"
            broken = json.loads(json.dumps(self.payload))
            broken["profiles"][0]["source_ids"] = ["made.up.source"]
            path.write_text(json.dumps(broken), encoding="utf-8")
            with self.assertRaises(GeocodingProfileError):
                load_profile_registry(path, known_source_ids=self.known_ids)


if __name__ == "__main__":
    unittest.main()
