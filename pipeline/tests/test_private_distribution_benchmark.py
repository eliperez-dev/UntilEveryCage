import json
import tempfile
import unittest
from pathlib import Path

from pipeline.scripts.benchmarks.build_private_distribution import build_distribution
from pipeline.scripts.benchmarks.run_api_load_rehearsal import load_distribution


class PrivateDistributionBenchmarkTests(unittest.TestCase):
    def test_report_is_row_free_bounded_and_accepted_by_rehearsal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            normalized = root / "records.jsonl"
            normalized.write_text(
                json.dumps({"normalized": {"country_code": "DK", "activity_categories": ["slaughter"], "coordinates": [10, 55]}}) + "\n"
                + json.dumps({"normalized": {"country_code": "FR", "classification_categories": ["fish_processing"], "display_precision": "city"}}) + "\n",
                encoding="utf-8",
            )
            report = build_distribution([normalized])
            self.assertEqual(report["selection"]["selected_records"], 2)
            self.assertEqual(sum(item["records"] for item in report["distribution"]), 2)
            self.assertNotIn("coordinates", json.dumps(report))
            report_path = root / "distribution.json"
            report_path.write_text(json.dumps(report), encoding="utf-8")
            distribution = load_distribution(report_path)
            self.assertEqual(len(distribution), 2)
            self.assertEqual(distribution[0][2], "slaughter")

    def test_rehearsal_rejects_non_blocked_or_empty_reports(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text(json.dumps({"schema_version": "v2-private-distribution-v1", "corpus_state": "public", "publication_eligibility": "eligible", "distribution": []}), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_distribution(path)


if __name__ == "__main__":
    unittest.main()
