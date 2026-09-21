import copy
import json
import unittest
from pathlib import Path

from pipeline.statistics.catalog import StatisticsCatalogError, load_catalog, validate_catalog


ROOT = Path(__file__).parents[2]
MANIFEST = ROOT / "data" / "manifests" / "animal-scale-statistics-catalog.json"
FIXTURE = Path(__file__).parent / "fixtures" / "synthetic_catalog.json"


class StatisticsCatalogTests(unittest.TestCase):
    def load(self, path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    def test_private_faostat_manifest_is_valid(self):
        catalog = load_catalog(MANIFEST)
        self.assertEqual(catalog["statistics"][0]["estimate"]["central"], 87892277479)
        self.assertEqual(validate_catalog(catalog)["status"], "passed")

    def test_synthetic_fixture_is_valid(self):
        report = validate_catalog(self.load(FIXTURE))
        self.assertEqual(report["statistics_count"], 1)

    def test_missing_dimension_is_rejected(self):
        catalog = self.load(FIXTURE)
        del catalog["statistics"][0]["period"]["kind"]
        with self.assertRaisesRegex(StatisticsCatalogError, "period.kind"):
            validate_catalog(catalog)

    def test_period_order_is_rejected(self):
        catalog = self.load(FIXTURE)
        catalog["statistics"][0]["period"]["start"] = "2025-01-01"
        with self.assertRaisesRegex(StatisticsCatalogError, "period"):
            validate_catalog(catalog)

    def test_unit_conversion_must_produce_whole_count(self):
        catalog = self.load(FIXTURE)
        catalog["statistics"][0]["components"][0]["conversion_to_central_unit"] = 1.5
        with self.assertRaisesRegex(StatisticsCatalogError, "converted component"):
            validate_catalog(catalog)

    def test_component_overlap_is_rejected(self):
        catalog = self.load(FIXTURE)
        catalog["statistics"][0]["components"][1]["overlap_group"] = "synthetic birds"
        with self.assertRaisesRegex(StatisticsCatalogError, "overlap_group"):
            validate_catalog(catalog)

    def test_aggregate_total_must_reconcile(self):
        catalog = self.load(FIXTURE)
        catalog["statistics"][0]["estimate"]["central"] = 2002
        with self.assertRaisesRegex(StatisticsCatalogError, "does not equal"):
            validate_catalog(catalog)

    def test_numeric_range_requires_two_bounds(self):
        catalog = self.load(FIXTURE)
        catalog["statistics"][0]["estimate"]["type"] = "range"
        catalog["statistics"][0]["uncertainty"]["kind"] = "numeric-range"
        with self.assertRaisesRegex(StatisticsCatalogError, "low and high"):
            validate_catalog(catalog)

    def test_citation_must_be_secure_and_declared(self):
        catalog = self.load(FIXTURE)
        catalog["statistics"][0]["citations"][0]["url"] = "http://example.org/source"
        with self.assertRaisesRegex(StatisticsCatalogError, "HTTPS"):
            validate_catalog(catalog)

    def test_revision_requires_new_version_metadata(self):
        catalog = self.load(FIXTURE)
        del catalog["statistics"][0]["revision"]["released_date"]
        with self.assertRaisesRegex(StatisticsCatalogError, "released_date"):
            validate_catalog(catalog)

    def test_copy_with_ambiguous_status_is_not_publishable(self):
        catalog = copy.deepcopy(self.load(FIXTURE))
        catalog["statistics"][0]["status"] = "published"
        with self.assertRaisesRegex(StatisticsCatalogError, "validated-private"):
            validate_catalog(catalog)


if __name__ == "__main__":
    unittest.main()
