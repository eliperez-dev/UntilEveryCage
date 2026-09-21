import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "diagnostics" / "coordinate-coverage.py"
SPEC = importlib.util.spec_from_file_location("coordinate_coverage", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class CoordinateCoverageTests(unittest.TestCase):
    def test_states_prioritize_restriction_and_distinguish_exact_from_coarse(self):
        self.assertEqual(MODULE.coordinate_state({"coordinates": {"latitude": 1, "longitude": 2}}), "source_supplied")
        self.assertEqual(MODULE.coordinate_state({"coordinates": {"latitude": 0, "longitude": 0}}), "source_supplied")
        self.assertEqual(MODULE.coordinate_state({"coordinates": {"latitude": 91, "longitude": 2}}), "unresolved")
        self.assertEqual(MODULE.coordinate_state({"coordinates": {"latitude": True, "longitude": 2}}), "unresolved")
        self.assertEqual(MODULE.coordinate_state({"geocode": {"status": "accepted", "result": {"x": 2}, "precision": "exact"}}), "geocoded_exact")
        self.assertEqual(MODULE.coordinate_state({"geocode": {"status": "accepted", "result": {"x": 2}}}), "unresolved")
        self.assertEqual(MODULE.coordinate_state({"geocode": {"status": "review_required", "result": {"x": 2}}}), "approximate_coarse")
        self.assertEqual(MODULE.coordinate_state({"geocode": {"status": "accepted", "result": {"x": 2}, "precision": "city"}}), "approximate_coarse")
        self.assertEqual(MODULE.coordinate_state({"geocode": {"status": "accepted", "result": {"x": 2}}, "restricted": True}), "restricted")
        self.assertEqual(MODULE.coordinate_state({}), "unresolved")

    def test_report_counts_observations_and_unique_facilities_without_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "input.jsonl"
            source.write_text("\n".join(json.dumps(item) for item in [
                {"facility_id": "a", "coordinates": {"latitude": 1, "longitude": 2}},
                {"facility_id": "a", "geocode": {"status": "unresolved"}, "name": "PRIVATE"},
                {"facility_id": "b", "geocode": {"status": "review_required", "result": {"x": 1}}},
                {"facility_id": "c", "privacy_status": "restricted", "address": "PRIVATE"},
            ]) + "\n", encoding="utf-8")
            report = MODULE.build_report(source)
            self.assertEqual(report["observations"], 4)
            self.assertEqual(report["unique_facilities"], 3)
            self.assertEqual(report["coordinate_states"], {"source_supplied": 1, "geocoded_exact": 0, "approximate_coarse": 1, "unresolved": 1, "restricted": 1})
            encoded = json.dumps(report)
            self.assertNotIn("PRIVATE", encoded)
            self.assertNotIn('"facility_id"', encoded)


if __name__ == "__main__":
    unittest.main()
