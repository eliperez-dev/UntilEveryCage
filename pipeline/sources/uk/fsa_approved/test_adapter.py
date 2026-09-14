import tempfile
import unittest
from pathlib import Path

from .adapter import FsaApprovedEstablishmentsAdapter, FsaContractError

FIXTURES = Path(__file__).parent / "fixtures"


class FsaAdapterTests(unittest.TestCase):
    def setUp(self):
        self.adapter = FsaApprovedEstablishmentsAdapter()

    def test_authority_and_nation_are_isolated_and_source_values_preserved(self):
        result = self.adapter.parse_file(FIXTURES / "valid.csv")
        self.assertEqual(len(result.accepted), 3)
        self.assertEqual(result.accepted[0]["normalized"]["establishment_id"], "00017")
        self.assertEqual(result.accepted[0]["normalized"]["nation"], "England")
        self.assertEqual(result.accepted[1]["normalized"]["competent_authority"], "Food Standards Agency")
        self.assertEqual(result.accepted[2]["normalized"]["competent_authority"], "Food Standards Agency Northern Ireland")
        self.assertEqual(result.accepted[0]["source_values"]["source_licence"], "terms-pending")
        self.assertIsNone(result.accepted[0]["normalized"]["coordinates"])

    def test_quarantines_identifier_activity_status_privacy_and_authority_errors(self):
        result = self.adapter.parse_file(FIXTURES / "quarantine.csv")
        reasons = [item["reasons"] for item in result.quarantined]
        self.assertIn(("duplicate_id_within_nation",), reasons)
        self.assertIn(("missing_establishment_id",), reasons)
        self.assertIn(("unknown_activity",), reasons)
        self.assertIn(("unknown_status",), reasons)
        self.assertIn(("address_privacy_risk",), reasons)
        self.assertIn(("authority_nation_mismatch",), reasons)

    def test_schema_drift_fails_closed(self):
        with self.assertRaises(FsaContractError):
            self.adapter.parse_file(FIXTURES / "schema_drift.csv")

    def test_manifest_rerun_is_deterministic_and_release_is_absent(self):
        with tempfile.TemporaryDirectory() as directory:
            first, second = Path(directory) / "one", Path(directory) / "two"
            self.assertEqual(self.adapter.run(FIXTURES / "valid.csv", first), self.adapter.run(FIXTURES / "valid.csv", second))
            self.assertFalse((first / "released" / "records.jsonl").exists())
            self.assertEqual((first / "manifest.json").read_bytes(), (second / "manifest.json").read_bytes())


if __name__ == "__main__":
    unittest.main()
