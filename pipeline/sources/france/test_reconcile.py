import tempfile
import unittest
from pathlib import Path

from .reconcile import reconcile, write_reconciliation
from .refresh import refresh


class FranceReconciliationTests(unittest.TestCase):
    def test_reconciles_two_scopes_without_claiming_unique_facilities(self):
        fixtures = Path(__file__).parent / "fixtures"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = refresh(section="I", raw_path=fixtures / "section_i.csv", run_dir=root / "i", retrieved_at_utc="2026-09-19T00:00:00Z")
            second = refresh(section="II", raw_path=fixtures / "section_ii.csv", run_dir=root / "ii", retrieved_at_utc="2026-09-19T00:00:00Z")
            report = reconcile(first["report"]["run_dir"], second["report"]["run_dir"])
            self.assertEqual(report["totals"]["input_rows"], 5)
            self.assertEqual(report["totals"]["normalized_rows"], 3)
            self.assertEqual(report["totals"]["quarantined_rows"], 2)
            self.assertTrue(report["totals"]["partition_valid"])
            self.assertIsNone(report["totals"]["unique_facility_count"])
            self.assertEqual(report["cross_section_overlap"]["shared_provisional_approval_number_count"], 0)
            self.assertEqual(report["sources"][0]["coordinate_state_counts"], {"not-supplied-by-source": 3})
            self.assertEqual(report["sources"][0]["identity_conflict_counts"]["rows_flagged"], 0)
            self.assertEqual(report["sources"][1]["quarantine_reason_counts"], {"missing_approval_number": 1})

            output = root / "reconciliation.json"
            write_reconciliation(first["report"]["run_dir"], second["report"]["run_dir"], output)
            self.assertIn('"unique_facility_count": null', output.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
