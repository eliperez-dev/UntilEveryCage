import json
import tempfile
import unittest
from pathlib import Path

from .legacy_compare import compare_legacy


class FsisLegacyComparisonTests(unittest.TestCase):
    def _legacy(self, root: Path) -> Path:
        path = root / "legacy.csv"
        path.write_text(
            "establishment_id,establishment_name,slaughter,processing\n"
            "A,Alpha,Yes,\n"
            "A,Alpha duplicate,,Yes\n"
            "B,Beta,No,Yes\n"
            ",Missing,No,No\n",
            encoding="utf-8",
        )
        return path

    def test_missing_current_is_explicitly_not_observed_not_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            report = compare_legacy(self._legacy(Path(directory)))
        self.assertEqual(report["legacy"]["rows"], 4)
        self.assertEqual(report["legacy"]["source_native_establishments"], 2)
        self.assertEqual(report["legacy"]["duplicate_identity_aliases"], 1)
        self.assertEqual(report["comparison"]["status"], "current-not-observed")
        self.assertIsNone(report["comparison"]["not_observed"])
        self.assertFalse(report["comparison"]["not_observed_means_closure"])
        self.assertFalse(report["row_payloads_included"])

    def test_current_exact_key_comparison_reports_additions_and_not_observed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            legacy = self._legacy(root)
            current = root / "current.jsonl"
            current.write_text(
                json.dumps({"source_values": {"directory": {"establishment_id": "A"}}})
                + "\n"
                + json.dumps({"source_values": {"directory": {"establishment_id": "C"}}})
                + "\n",
                encoding="utf-8",
            )
            report = compare_legacy(legacy, current_records_path=current)
        self.assertEqual(report["comparison"]["status"], "exact-key-set-comparison")
        self.assertEqual(report["comparison"]["additions"], 1)
        self.assertEqual(report["comparison"]["not_observed"], 1)
        self.assertEqual(report["comparison"]["unresolved_current_rows"], 1)


if __name__ == "__main__":
    unittest.main()
