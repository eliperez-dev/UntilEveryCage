from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import unittest

from pipeline.common.refresh_runner import RefreshCatalog, RefreshRunner
from pipeline.contracts.refresh import RefreshRequest
from pipeline.source_runtime_classification import require_production_preview_source
from pipeline.taxonomy_crosswalk import crosswalk_document, project_observation

ROOT = Path(__file__).parents[2]
IMPORTER_PATH = ROOT / "pipeline" / "scripts" / "maintenance" / "import-real-preview.py"
SPEC = importlib.util.spec_from_file_location("source_expansion_preview_importer", IMPORTER_PATH)
IMPORTER = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(IMPORTER)


class SourceExpansionIntegrationTests(unittest.TestCase):
    def test_all_three_sources_dispatch_through_the_shared_refresh_catalog(self):
        catalog = RefreshCatalog()
        expected = {
            "no.fiskeridir.aquaculture": ("NorwayAquacultureRefreshAdapter", "no"),
            "gb.scot.marine.aquaculture": ("ScotlandAquacultureRefreshAdapter", "gb"),
            "us.epa.echo-animal-production": ("EpaEchoAnimalRefreshAdapter", "us"),
        }
        for source_id, (adapter_path, country) in expected.items():
            with self.subTest(source_id=source_id):
                registered = catalog.adapters[source_id]
                self.assertEqual(type(registered.adapter).__name__, adapter_path)
                self.assertEqual(registered.capabilities.country_code, country)
                self.assertTrue(registered.capabilities.live_callable)
                self.assertEqual(catalog.operation_metadata(source_id)["live_access"],
                                 "source-specific-acquisition-hook-registered")
                self.assertFalse(require_production_preview_source(source_id)["public_release"])

    def test_georisques_registers_as_terms_gated_source_without_enabling_preview(self):
        catalog = RefreshCatalog()
        source_id = "fr.georisques.icpe.animal"
        registered = catalog.adapters[source_id]
        self.assertEqual(type(registered.adapter).__name__, "FirstWaveRefreshAdapter")
        self.assertEqual(registered.capabilities.country_code, "fr")
        self.assertTrue(registered.capabilities.live_callable)
        self.assertEqual(registered.capabilities.operational_classification, "terms-blocked")
        self.assertEqual(catalog.operation_metadata(source_id)["live_access"],
                         "source-specific-acquisition-hook-registered")
        policy = json.loads((ROOT / "pipeline" / "preview-enabled-sources.json").read_text(encoding="utf-8"))["sources"][source_id]
        self.assertFalse(policy["enabled"])
        self.assertFalse(policy["public_release"])
        self.assertEqual(policy["terms_decision"], "pending")
        self.assertTrue({"name", "address", "coordinates", "activity_status_source",
                         "source_classification_codes"}.issubset(policy["allowed_preview_fields"]))

    def test_georisques_runs_through_normal_shared_fixture_dispatch(self):
        output = ROOT / ".georisques-shared-refresh-test"
        shutil.rmtree(output, ignore_errors=True)
        try:
            result = RefreshRunner().run(RefreshRequest(
                source_ids=("fr.georisques.icpe.animal",), mode="fixture", output_root=output,
                options={"run_id": "synthetic-contract"},
            ))
            source = result["results"][0]
            self.assertEqual(source["status"], "succeeded")
            self.assertEqual(source["summary"]["lifecycle_status"], "candidate-ready")
            self.assertTrue(source["summary"]["candidate_handoff"])
            self.assertFalse(source["publication"]["published"])
        finally:
            shutil.rmtree(output, ignore_errors=True)

    def test_georisques_exact_rubric_taxonomy_has_no_mining_projection(self):
        source_id = "fr.georisques.icpe.animal"
        projected = project_observation({"source_id": source_id, "normalized": {
            "source_classification_codes": ["2101", "2210", "2510"]}})
        self.assertEqual(projected["taxonomy_mapping_status"], "mapped")
        self.assertEqual({item["primary"] for item in projected["taxonomy_assignments"]},
                         {"animal_keeping_and_production", "slaughter"})
        self.assertEqual(projected["taxonomy_mapping_method"], "direct")
        document = crosswalk_document(source_id)
        self.assertIn("2101", {code for rule in document["rules"] for code in rule["source_codes"]})
        self.assertNotIn("2510", {code for rule in document["rules"] for code in rule["source_codes"]})

    def test_preview_contracts_keep_source_specific_metadata_and_private_boundaries(self):
        policies = json.loads((ROOT / "pipeline" / "preview-enabled-sources.json").read_text(encoding="utf-8"))["sources"]
        for source_id in ("no.fiskeridir.aquaculture", "gb.scot.marine.aquaculture",
                          "us.epa.echo-animal-production"):
            policy = policies[source_id]
            self.assertTrue(policy["enabled"])
            self.assertFalse(policy["public_release"])
            self.assertTrue(policy["terms_review"])
            self.assertIn("coordinates", policy["allowed_preview_fields"])
        scotland = policies["gb.scot.marine.aquaculture"]["allowed_preview_fields"]
        self.assertTrue({"source_status_code", "source_status", "source_projected_coordinates",
                         "source_feature_count", "source_feature_rows"}.issubset(scotland))
        epa = policies["us.epa.echo-animal-production"]["allowed_preview_fields"]
        self.assertTrue({"industry_classification_basis", "regulated_program", "cafo_status",
                         "operating_status", "coordinate_provenance_state"}.issubset(epa))
        self.assertEqual(IMPORTER.SOURCE_MEDIA_TYPES["no.fiskeridir.aquaculture"], "application/geo+json")
        self.assertEqual(IMPORTER.SOURCE_MEDIA_TYPES["gb.scot.marine.aquaculture"], "application/geo+json")
        self.assertEqual(IMPORTER.SOURCE_MEDIA_TYPES["us.epa.echo-animal-production"], "application/zip")
        self.assertEqual(IMPORTER.SOURCE_MEDIA_TYPES["fr.georisques.icpe.animal"], "application/json")

    def test_georisques_private_parse_retains_native_name_address_and_unmapped_coordinates(self):
        source_id = "fr.georisques.icpe.animal"
        normalized = {
            "establishment_id": "SYNTHETIC-AIOT", "name": "Ferme privée synthétique",
            "trading_name": "Ferme privée synthétique", "address": "1 Rue Exemple",
            "postal_code": "01000", "municipality": "Commune Synthétique", "country_code": "FR",
            "coordinates": {"longitude": 5.0, "latitude": 46.0,
                            "precision": "source-coordinate-crs-unverified"},
            "source_classification_codes": ["2101"], "source_classification_labels": ["cattle holdings"],
            "activity_categories": ["animal_keeping"], "activity_status_source": "source value",
            "privacy_gate": "pending-review", "in_default_map_scope": False,
            "map_scope_reason": "pending coordinate CRS review",
        }
        parsed = IMPORTER.parse_row(source_id, {
            "source_id": source_id, "source_record_key": "SYNTHETIC-AIOT|row-1",
            "source_values": {"raisonSociale": "Ferme privée synthétique"}, "normalized": normalized,
        })
        self.assertEqual(parsed[11], "Ferme privée synthétique")
        self.assertEqual(parsed[18], "1 Rue Exemple")
        self.assertEqual((parsed[5], parsed[6]), (46.0, 5.0))
        self.assertFalse(parsed[16])


if __name__ == "__main__":
    unittest.main()
