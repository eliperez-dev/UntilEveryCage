import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "stages" / "validate-release.py"
SPEC = importlib.util.spec_from_file_location("validate_release", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ReleaseValidationTests(unittest.TestCase):
    def test_complete_release_passes(self):
        report = MODULE.evaluate({"release_records": 10, "duplicate_observations": 0, "validation_errors": 0, "review_visible": 0}, 10)
        self.assertEqual(report["status"], "passed")

    def test_incomplete_or_unsafe_release_is_blocked(self):
        report = MODULE.evaluate({"release_records": 9, "duplicate_observations": 1, "validation_errors": 2, "review_visible": 1}, 10)
        self.assertEqual(report["status"], "blocked")
        self.assertEqual({finding["code"] for finding in report["findings"]}, {"record_count_mismatch", "duplicate_release_observations", "validation_errors", "review_required_visible"})

    def test_html_report_is_human_readable(self):
        report = {"release_id": "test-release", "status": "passed", "metrics": {"release_records": 2}, "findings": []}
        rendered = MODULE.render_html(report)
        self.assertIn("Release review", rendered)
        self.assertIn("PASSED", rendered)
        self.assertIn("release_records", rendered)


if __name__ == "__main__":
    unittest.main()
