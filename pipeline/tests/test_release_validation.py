import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "stages" / "validate-release.py"
SPEC = importlib.util.spec_from_file_location("validate_release", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ReleaseValidationTests(unittest.TestCase):
    def test_complete_release_passes(self):
        report = MODULE.evaluate({"release_records": 10, "duplicate_observations": 0, "validation_errors": 0, "review_visible": 0, "coordinate_not_ready": 0, "publication_not_approved": 0, "active_suppression": 0, "rights_not_cleared": 0}, 10)
        self.assertEqual(report["status"], "passed")

    def test_incomplete_or_unsafe_release_is_blocked(self):
        report = MODULE.evaluate({"release_records": 9, "duplicate_observations": 1, "validation_errors": 2, "review_visible": 1, "coordinate_not_ready": 2, "publication_not_approved": 3, "active_suppression": 1, "rights_not_cleared": 2}, 10)
        self.assertEqual(report["status"], "blocked")
        self.assertEqual({finding["code"] for finding in report["findings"]}, {"record_count_mismatch", "duplicate_release_observations", "validation_errors", "review_required_visible", "coordinate_not_ready", "publication_not_approved", "active_suppression", "demonstration_rights_not_cleared"})

    def test_publication_safety_gates_block_candidate(self):
        report = MODULE.evaluate({"release_records": 1, "duplicate_observations": 0, "validation_errors": 0, "review_visible": 0, "coordinate_not_ready": 1, "publication_not_approved": 1, "active_suppression": 1, "rights_not_cleared": 0})
        self.assertEqual(report["status"], "blocked")
        self.assertEqual({finding["code"] for finding in report["findings"]}, {"coordinate_not_ready", "publication_not_approved", "active_suppression"})

    def test_html_report_is_human_readable(self):
        report = {"release_id": "test-release", "status": "passed", "metrics": {"release_records": 2}, "findings": []}
        rendered = MODULE.render_html(report)
        self.assertIn("Release review", rendered)
        self.assertIn("PASSED", rendered)
        self.assertIn("release_records", rendered)

    def test_test_only_release_is_blocked_before_validation(self):
        report = MODULE.evaluate({"release_records": 1, "duplicate_observations": 0, "validation_errors": 0, "review_visible": 0, "coordinate_not_ready": 0, "publication_not_approved": 0, "active_suppression": 0, "test_only": True})
        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["findings"][0]["code"], "test_only_release")

    def test_validation_report_names_test_only_blocker(self):
        report = MODULE.evaluate({"release_records": 0, "duplicate_observations": 0, "validation_errors": 0, "review_visible": 0, "coordinate_not_ready": 0, "publication_not_approved": 0, "active_suppression": 0, "test_only": True})
        self.assertIn("test_only_release", {finding["code"] for finding in report["findings"]})


if __name__ == "__main__":
    unittest.main()
