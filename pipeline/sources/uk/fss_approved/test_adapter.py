import json
import tempfile
import unittest
from pathlib import Path

from .adapter import CONFIG, FssApprovedEstablishmentsAdapter, FssContractError

FIXTURES = Path(__file__).parent / "fixtures"


class FssAdapterTests(unittest.TestCase):
    def setUp(self):
        self.adapter = FssApprovedEstablishmentsAdapter()

    def test_preserves_source_values_and_leading_zeroes(self):
        result = self.adapter.parse_file(FIXTURES / "valid.csv")
        self.assertEqual(len(result.accepted), 2)
        self.assertEqual(result.accepted[0]["normalized"]["approval_number"], "001234")
        self.assertEqual(result.accepted[1]["normalized"]["species"], "unknown")
        self.assertEqual(result.accepted[0]["source_values"]["trading_name"], "North Star Foods")
        self.assertIsNone(result.accepted[0]["normalized"]["coordinates"])
        self.assertFalse(result.release_allowed)

    def test_quarantines_duplicate_activity_status_remarks_and_privacy(self):
        result = self.adapter.parse_file(FIXTURES / "quarantine.csv")
        self.assertEqual(len(result.accepted), 0)
        self.assertEqual(result.quarantined[0]["reasons"], ("duplicate_id",))
        self.assertEqual(result.quarantined[2]["reasons"], ("unknown_activity",))
        self.assertEqual(result.quarantined[3]["reasons"], ("remarks_present", "address_privacy_risk"))

    def test_schema_drift_fails_closed(self):
        with self.assertRaises(FssContractError):
            self.adapter.parse_file(FIXTURES / "schema_drift.csv")

    def test_inspected_live_export_profile_skips_preamble_and_classifies(self):
        row = ["", "FSS-TEST-1", "Synthetic Scotland Foods", "Industrial Estate", "", "", "", "AB1 2CD", "CP (Cutting Plant); CS (Cold Store)"] + [""] * 19 + ["pig", "", "Food Standards Scotland", "Aberdeen City", "No"]
        content = ("\n\nApproved Establishments in Scotland\n11 August 2026\n\n" + ",".join(CONFIG["live_columns"]) + "\n" + ",".join(row) + "\n").encode("cp1252")
        result = self.adapter.parse_bytes(content)
        self.assertEqual(len(result.accepted), 1)
        self.assertEqual(result.accepted[0]["source_row"], 7)
        self.assertEqual(result.accepted[0]["normalized"]["nation"], "Scotland")
        self.assertEqual(result.accepted[0]["normalized"]["activity_categories"], ("cutting", "logistics_and_storage"))
        self.assertEqual(result.coverage_counts, {"Scotland": 1})

    def test_run_is_deterministic_and_has_no_release(self):
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "one"
            second = Path(directory) / "two"
            a = self.adapter.run(FIXTURES / "valid.csv", first)
            b = self.adapter.run(FIXTURES / "valid.csv", second)
            self.assertEqual(a, b)
            self.assertFalse((first / "released" / "records.jsonl").exists())
            self.assertEqual((first / "normalized" / "records.jsonl").read_bytes(), (second / "normalized" / "records.jsonl").read_bytes())

    def test_failed_run_leaves_prior_output_untouched(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            (root / "run-status.json").parent.mkdir(parents=True)
            (root / "run-status.json").write_text("previous\n", encoding="utf-8")
            with self.assertRaises(FssContractError):
                self.adapter.run(FIXTURES / "schema_drift.csv", root)
            self.assertEqual((root / "run-status.json").read_text(encoding="utf-8"), "previous\n")


if __name__ == "__main__":
    unittest.main()
