import tempfile
import unittest
from pathlib import Path

from pipeline.scripts.diagnostics.real_corpus_regression import build_report


class RealCorpusRegressionTests(unittest.TestCase):
    def _write(self, root: Path, country: str, rows: str) -> None:
        path = root / country
        path.mkdir(parents=True)
        (path / "locations.csv").write_text(rows, encoding="utf-8")

    def test_report_is_deterministic_and_row_free(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write(root, "aa", "establishment_id,establishment_name,city,latitude,longitude,slaughter\n1,Alpha,Town,52.1,4.2,true\n,No ID,Town,52.2,4.3,true\n")
            first = build_report(root, countries=("aa",), max_records=10, as_of="2026-09-16T00:00:00Z")
            second = build_report(root, countries=("aa",), max_records=10, as_of="2026-09-16T00:00:00Z")
            self.assertEqual(first, second)
            self.assertEqual(first["selection"]["selected_records"], 2)
            self.assertEqual(first["funnel"]["accepted_private"], 1)
            self.assertEqual(first["funnel"]["quarantined"], 1)
            self.assertEqual(first["coverage"]["source_profile_count"], 1)
            self.assertNotIn("Alpha", str(first))

    def test_selection_is_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write(root, "aa", "establishment_id,establishment_name,city\n" + "\n".join(f"{i},Name {i},Town" for i in range(20)) + "\n")
            report = build_report(root, countries=("aa",), max_records=7)
            self.assertEqual(report["selection"]["available_records"], 20)
            self.assertEqual(report["selection"]["selected_records"], 7)
            self.assertTrue(report["funnel"]["row_count_reconciles"])


if __name__ == "__main__":
    unittest.main()
