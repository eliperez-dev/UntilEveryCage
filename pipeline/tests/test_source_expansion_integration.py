from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import unittest

from pipeline.common.refresh_runner import RefreshCatalog
from pipeline.source_runtime_classification import require_production_preview_source

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


if __name__ == "__main__":
    unittest.main()
