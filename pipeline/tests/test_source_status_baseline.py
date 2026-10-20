"""CI-discovered consistency checks for the source-status evidence baseline."""

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class SourceStatusBaselineTests(unittest.TestCase):
    def load_status(self):
        return json.loads((ROOT / "docs" / "source-status.json").read_text(encoding="utf-8"))

    def load_registry_ids(self):
        registry = json.loads((ROOT / "pipeline" / "source_registry.json").read_text(encoding="utf-8"))
        return {source["source_id"] for source in registry["sources"]}

    def test_status_covers_exactly_the_source_registry_ids(self):
        payload = self.load_status()
        ids = {source["source_id"] for source in payload["sources"]}
        self.assertEqual(ids, self.load_registry_ids())

    def test_status_values_are_explicit_and_conservative(self):
        payload = self.load_status()
        vocab = payload["status_vocabulary"]
        for source in payload["sources"]:
            self.assertIn(source["metadata"], vocab["metadata"])
            self.assertIn(source["acquisition"], vocab["acquisition"])
            self.assertIn(source["runtime_health"], vocab["runtime_health"])
            self.assertIn(source["publication_eligibility"], vocab["publication_eligibility"])
            self.assertTrue(source["evidence"])
            self.assertTrue(source["next_action"])
            self.assertIsInstance(source["metadata"], str)
            self.assertIsInstance(source["next_action"], str)
        for source in payload["sources"]:
            if source["runtime_health"] == "healthy":
                self.assertTrue(source.get("runtime_health_scope"))
                self.assertTrue(source.get("runtime_health_evidence"))
        self.assertTrue(all(source["publication_eligibility"] != "eligible" for source in payload["sources"]))

    def test_json_is_authority_and_markdown_is_only_a_router(self):
        markdown = (ROOT / "docs" / "source-status.md").read_text(encoding="utf-8")
        self.assertIn("sole authoritative record", markdown)
        self.assertIn("source-status.json", markdown)
        self.assertIn("runtime_health: healthy", markdown)
        self.assertIn("freshness SLA", markdown)
        self.assertNotIn("| Source |", markdown)
        self.assertNotIn("## Current baseline", markdown)

    def test_sweden_blocker_is_explicit_and_conservative(self):
        payload = self.load_status()
        source = next(item for item in payload["sources"]
                      if item["source_id"] == "se.jordbruksverket.slaughterhouses")
        self.assertEqual(source["metadata"], "verified")
        self.assertEqual(source["acquisition"], "blocked")
        self.assertEqual(source["runtime_health"], "not_run")
        self.assertEqual(source["publication_eligibility"], "blocked")
        self.assertIn("reuse permission is unresolved", source["next_action"])

    def test_new_sources_have_metadata_capture_and_separate_health_and_publication(self):
        payload = self.load_status()
        by_id = {item["source_id"]: item for item in payload["sources"]}
        for source_id in ("no.fiskeridir.aquaculture", "us.epa.echo-animal-production", "gb.scot.marine.aquaculture"):
            source = by_id[source_id]
            details = source["metadata_details"]
            for field in ("publisher", "publisher_url", "country_code", "jurisdiction_scope", "coverage", "license_reference", "notes"):
                self.assertTrue(details.get(field), (source_id, field))
            self.assertEqual(source["metadata"], "verified")
            self.assertEqual(source["acquisition"], "verified")
            self.assertIn(source["runtime_health"], {"not_run", "healthy"})
            if source["runtime_health"] == "healthy":
                self.assertIn("Latest measured successful live refresh", source["runtime_health_scope"])
                runtime_snapshot = source.get("latest_successful_runtime_snapshot")
                run_id = runtime_snapshot["run_id"] if runtime_snapshot else source["latest_private_capture"]["private_e2e_run_id"]
                self.assertIn(run_id, source["runtime_health_evidence"])
            self.assertEqual(source["publication_eligibility"], "blocked")
            self.assertEqual(source["private_e2e"], "strict_private_preview_e2e_passed_once")
            self.assertTrue(source["e2e_verified"])
            self.assertEqual(source["latest_private_capture"]["disposable_database_import"], "verified_once_in_approved_disposable_clone")
            self.assertEqual(source["latest_private_capture"]["private_preview_candidates"], source["latest_private_capture"]["private_rust_map_feed_candidates"])
            self.assertEqual(source["latest_private_capture"]["public_rows"], 0)

        expansion = payload["latest_source_expansion_private_e2e"]
        self.assertEqual(expansion["source_qualified_candidate_observations_sum"], 12318)
        self.assertFalse(expansion["global_deduplication_performed"])
        self.assertTrue(expansion["public_baseline_after_import"]["unchanged"])
        self.assertEqual(expansion["public_baseline_after_import"]["approved_manifest_sha256"], "8c961c0e11902cf916e9242875610f66fbfd4103d8e761b3dd00e5e4a804cdd1")
        self.assertIn("refresh --source <source_id>", expansion["operator_command"])
        self.assertIn("disposable local clone", expansion["scope"])

        epa = by_id["us.epa.echo-animal-production"]
        capture = epa["latest_private_capture"]
        self.assertEqual(capture["input_rows"], capture["normalized_candidates"] + capture["quarantined_rows"])
        self.assertEqual(capture["input_rows"], 8510)
        self.assertEqual(capture["current_count_and_ids_recheck"], 8510)
        self.assertEqual(capture["count_difference_from_earlier_observation"], 144)
        self.assertIn("not a confirmed CAFO", epa["metadata_details"]["coverage"])
        self.assertIn("earlier exploratory count", epa["next_action"])

        scotland = by_id["gb.scot.marine.aquaculture"]
        scotland_capture = scotland["latest_private_capture"]
        self.assertEqual(scotland["runtime_health"], "healthy")
        self.assertEqual(scotland["publication_eligibility"], "blocked")
        self.assertEqual(scotland_capture["input_feature_rows"], 8308)
        self.assertEqual(scotland_capture["unique_site_groups"], 3074)
        self.assertEqual(scotland_capture["animal_site_candidates"], 2124)
        self.assertEqual(scotland_capture["fishery_site_groups_excluded"], 950)
        self.assertEqual(scotland_capture["animal_feature_observations"], 5210)
        self.assertEqual(scotland_capture["candidate_status_groups"], {"active": 676, "inactive": 489, "deregistered": 959})
        self.assertEqual(scotland_capture["features_with_source_coordinates"], 8308)
        self.assertIn("not current-farm claims", scotland["next_action"])

        epa = by_id["us.epa.echo-animal-production"]
        self.assertEqual(epa["runtime_health"], "healthy")
        self.assertEqual(epa["publication_eligibility"], "blocked")

    def test_evidence_paths_exist_and_exclude_private_roots(self):
        payload = self.load_status()
        for source in payload["sources"]:
            for evidence in source["evidence"]:
                self.assertFalse(evidence.startswith((".codex/", "data/terms-reviews/", "philosophy/")))
                self.assertTrue((ROOT / evidence).exists(), evidence)


if __name__ == "__main__":
    unittest.main()
