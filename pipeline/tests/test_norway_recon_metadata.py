import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NORWAY_IDS = {
    "no.mattilsynet.approved-food", "no.mattilsynet.feed-abp", "no.fiskeridir.aquaculture",
    "no.landbruksdirektoratet.farm-register", "no.mattilsynet.animal-experiments",
    "no.miljodirektoratet.prtr-permits", "no.brreg.organizations", "no.ssb.meat-and-animal-use",
}

class NorwayReconMetadataTests(unittest.TestCase):
    def test_sources_are_registered_and_document_is_row_free(self):
        registry = json.loads((ROOT / "pipeline/source_registry.json").read_text(encoding="utf-8"))
        self.assertTrue(NORWAY_IDS.issubset({s["source_id"] for s in registry["sources"]}))
        doc = (ROOT / "docs/country-recon-no.md").read_text(encoding="utf-8")
        self.assertIn("row-free", doc)
        self.assertIn("fully automated", doc)
        self.assertNotIn("Approval ID |", doc)

    def test_sources_are_conservative(self):
        status = json.loads((ROOT / "docs/source-status.json").read_text(encoding="utf-8"))
        by_id = {s["source_id"]: s for s in status["sources"]}
        for source_id in NORWAY_IDS:
            self.assertEqual(by_id[source_id]["publication_eligibility"], "blocked")
            if source_id == "no.fiskeridir.aquaculture":
                self.assertEqual(by_id[source_id]["acquisition"], "verified")
                self.assertEqual(by_id[source_id]["runtime_health"], "healthy")
                self.assertIn("no recurring reliability", by_id[source_id]["runtime_health_scope"])
                capture = by_id[source_id]["latest_private_capture"]
                self.assertEqual(capture["input_rows"], 1781)
                self.assertEqual(capture["normalized_candidates"], 1684)
                self.assertEqual(capture["quarantined_rows"], 97)
                self.assertEqual(capture["disposable_database_import"], "verified_once_in_approved_disposable_clone")
                self.assertEqual(capture["private_database"], "uec_real_preview_test_sources_20261020")
                self.assertEqual(capture["preview_import_status"], "imported")
                self.assertEqual(capture["private_preview_candidates"], 1684)
                self.assertEqual(capture["private_rust_map_feed_candidates"], 1684)
                self.assertEqual(capture["public_rows"], 0)
                self.assertTrue(capture["receipt_manifest"].endswith("refresh-ec0cda27754ff947/manifest.json"))
                snapshot = by_id[source_id]["latest_successful_runtime_snapshot"]
                self.assertEqual(snapshot["run_id"], "refresh-cfc009483f56e2c9")
                self.assertEqual(snapshot["source_native_names"], 1781)
                self.assertEqual(snapshot["normalized_candidates_with_native_name"], 1684)
                self.assertEqual(snapshot["private_api_display_name_candidates"], 1684)
                self.assertEqual(snapshot["public_rows"], 0)
                self.assertTrue(snapshot["approved_public_baseline"]["unchanged"])
            else:
                self.assertIn(by_id[source_id]["acquisition"], {"not_run", "blocked"})

if __name__ == "__main__":
    unittest.main()
