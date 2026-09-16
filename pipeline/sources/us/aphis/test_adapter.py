import unittest
from pathlib import Path
from .adapter import AphisContractError, AphisPublicSearchAdapter

ROOT=Path(__file__).parent

class AphisAdapterTests(unittest.TestCase):
    def test_profiles_remain_distinct(self):
        adapter=AphisPublicSearchAdapter()
        for profile in ("registrations","annual_reports","inspections"):
            with self.subTest(profile=profile):
                result=adapter.parse_bytes((ROOT/f"fixtures/{profile}.csv").read_bytes())
                self.assertEqual(result["profile"],profile); self.assertEqual(len(result["accepted"]),1)
                row=result["accepted"][0]
                self.assertEqual(row["normalized"]["evidence_type"],profile)
                self.assertIsNone(row["normalized"]["establishment_id"])
                self.assertEqual(row["normalized"]["publication_gate"],"blocked")

    def test_annual_report_requires_year_and_duplicate_ids_quarantine(self):
        raw=(ROOT/"fixtures/annual_reports.csv").read_text(encoding="utf-8").replace(",2025,", ",,")
        result=AphisPublicSearchAdapter().parse_bytes(raw.encode())
        self.assertEqual(len(result["quarantined"]),1); self.assertIn("missing_report_year",result["quarantined"][0]["reasons"])

    def test_annual_reports_use_year_in_observation_identity(self):
        raw=(ROOT/"fixtures/annual_reports.csv").read_text(encoding="utf-8")
        second=raw.splitlines()[1].replace(",2025,", ",2024,")
        result=AphisPublicSearchAdapter().parse_bytes((raw + second + "\n").encode())
        self.assertEqual(len(result["accepted"]),2)
        self.assertNotEqual(result["accepted"][0]["source_record_key"], result["accepted"][1]["source_record_key"])

    def test_unsupported_profile_fails_closed(self):
        with self.assertRaises(AphisContractError): AphisPublicSearchAdapter().parse_bytes(b"Name,Value\nA,B\n")

if __name__ == "__main__": unittest.main()
