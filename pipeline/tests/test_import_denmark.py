import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "stages" / "import-denmark.py"
SPEC = importlib.util.spec_from_file_location("import_denmark", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class DenmarkImporterTests(unittest.TestCase):
    def test_current_acquisition_metadata_aliases_are_accepted(self):
        metadata = {"final_url": "https://example.invalid/data", "artifact": "Smileydata.xml", "byte_size": 12}
        self.assertEqual(MODULE.metadata_value(metadata, "source_url", "final_url"), "https://example.invalid/data")
        self.assertEqual(MODULE.metadata_value(metadata, "artifact_path", "artifact"), "Smileydata.xml")
        self.assertEqual(MODULE.metadata_value(metadata, "bytes", "byte_size"), 12)
    def test_single_point_requires_explicit_coordinate_review(self):
        item = {
            "acceptance": "accepted_single_point",
            "response": [{"x": 12.5, "y": 55.6}],
        }
        self.assertIsNone(MODULE.point_from_geocode(item))
        self.assertEqual(MODULE.geocode_status(item), "review_required")
        item["coordinate_review_status"] = "approved"
        self.assertEqual(MODULE.point_from_geocode(item), (12.5, 55.6))
        self.assertEqual(MODULE.geocode_status(item), "accepted")

    def test_non_unique_results_are_not_promoted(self):
        item = {
            "acceptance": "review_multiple_points",
            "response": [{"x": 12.5, "y": 55.6}, {"x": 12.6, "y": 55.7}],
        }
        self.assertIsNone(MODULE.point_from_geocode(item))
        self.assertEqual(MODULE.geocode_status(item), "review_required")

    def test_geocoder_failures_are_retryable_status_records(self):
        item = {"status": "failed", "acceptance": "unresolved"}
        self.assertEqual(MODULE.geocode_status(item), "unresolved")
        self.assertEqual(MODULE.geocode_status({"status": "failed"}), "failed")


if __name__ == "__main__":
    unittest.main()
