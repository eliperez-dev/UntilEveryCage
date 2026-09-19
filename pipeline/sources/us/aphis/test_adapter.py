import unittest
import hashlib
import tempfile
from pathlib import Path

from pipeline.contracts.adapter_contract import SourceArtifact
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

    def test_current_compact_annual_export_shape_is_supported(self):
        raw = (
            "Customer Number,Certificate Number,Year,Dogs,Cats\n"
            '"2","87-R-0002","2025","","278"\n'
        ).encode()
        result = AphisPublicSearchAdapter().parse_bytes(raw)
        self.assertEqual(result["profile"], "annual_reports")
        self.assertEqual(len(result["accepted"]), 1)
        normalized = result["accepted"][0]["normalized"]
        self.assertIsNone(normalized["account_name"])
        self.assertEqual(normalized["report_year"], "2025")
        self.assertIn("Cats", normalized["animal_use_fields_present"])

    def test_current_registrant_export_shape_is_supported(self):
        raw = (
            "Account Name,Customer Number,Certificate Number,Registration Type,Certificate Status,Status Date\n"
            '"Synthetic Registrant","2","87-R-0002","Class R - Research Facility","Active","2026-01-01"\n'
        ).encode()
        result = AphisPublicSearchAdapter().parse_bytes(raw)
        self.assertEqual(result["profile"], "registrations")
        self.assertEqual(len(result["accepted"]), 1)

    def test_current_inspection_export_shape_is_supported(self):
        raw = (
            "Customer Number,Certificate Number,Inspection Date,Direct NCIs,Non-Critical NCIs,Critical NCIs,Teachable Moments,Site Name,Legal Name,License-Registration Type,City,State,Zip\n"
            '"2","87-R-0002","2026-08-21","","","","","Site","Legal","Class R - Research Facility","Austin","Texas","78701"\n'
        ).encode()
        result = AphisPublicSearchAdapter().parse_bytes(raw)
        self.assertEqual(result["profile"], "inspections")
        self.assertEqual(len(result["accepted"]), 1)
        self.assertEqual(result["accepted"][0]["normalized"]["status_date"], "2026-08-21")

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

    def test_inspections_use_status_date_in_observation_identity(self):
        raw = (ROOT / "fixtures/inspections.csv").read_text(encoding="utf-8")
        second = raw.splitlines()[1].replace("2026-02-01", "2026-03-01")
        result = AphisPublicSearchAdapter().parse_bytes((raw + second + "\n").encode())
        self.assertEqual(len(result["accepted"]), 2)
        self.assertNotEqual(result["accepted"][0]["source_record_key"], result["accepted"][1]["source_record_key"])

    def test_inspections_preserve_same_day_distinct_sites_with_provisional_identity(self):
        header = "Customer Number,Certificate Number,Inspection Date,Site Name,Legal Name,City,State,Zip,Direct NCIs\n"
        raw = (
            header
            + '"2","87-R-0002","2026-08-21","North Site","Lab","Austin","TX","78701","0"\n'
            + '"2","87-R-0002","2026-08-21","South Site","Lab","Austin","TX","78701","1"\n'
        ).encode()
        result = AphisPublicSearchAdapter().parse_bytes(raw)
        self.assertEqual(len(result["accepted"]), 2)
        self.assertEqual(len(result["quarantined"]), 0)
        self.assertNotEqual(result["accepted"][0]["source_record_key"], result["accepted"][1]["source_record_key"])
        self.assertEqual(result["accepted"][0]["normalized"]["event_identity_unresolved"], True)
        self.assertEqual(result["accepted"][0]["normalized"]["event_identity_review_state"], "review_required")
        self.assertEqual(result["accepted"][0]["normalized"]["provisional_event_key"], result["accepted"][1]["normalized"]["provisional_event_key"])

    def test_inspections_exact_duplicate_rows_remain_explicitly_quarantined(self):
        raw = (
            "Customer Number,Certificate Number,Inspection Date,Site Name,Direct NCIs\n"
            '"2","87-R-0002","2026-08-21","Same Site","0"\n'
            '"2","87-R-0002","2026-08-21","Same Site","0"\n'
        ).encode()
        result = AphisPublicSearchAdapter().parse_bytes(raw)
        self.assertEqual(len(result["accepted"]), 0)
        self.assertEqual(len(result["quarantined"]), 2)
        self.assertEqual(result["quarantined"][0]["reasons"], ("duplicate_observation_id",))

    def test_inspections_use_explicit_native_report_id_when_present(self):
        raw = (
            "Customer Number,Certificate Number,Inspection Date,Inspection Report ID,Site Name\n"
            '"2","87-R-0002","2026-08-21","R-1","North Site"\n'
            '"2","87-R-0002","2026-08-21","R-2","South Site"\n'
        ).encode()
        result = AphisPublicSearchAdapter().parse_bytes(raw)
        self.assertEqual(len(result["accepted"]), 2)
        self.assertIn("Inspection Report ID=R-1", result["accepted"][0]["source_record_key"])
        self.assertFalse(result["accepted"][0]["normalized"]["event_identity_unresolved"])

    def test_unsupported_profile_fails_closed(self):
        with self.assertRaises(AphisContractError): AphisPublicSearchAdapter().parse_bytes(b"Name,Value\nA,B\n")

    def test_customer_variants_and_source_values_are_preserved(self):
        result = AphisPublicSearchAdapter().parse_bytes((ROOT / "fixtures/annual_reports.csv").read_bytes())
        record = result["accepted"][0]
        normalized = record["normalized"]
        self.assertEqual(normalized["customer_number_x"], "Synthetic Laboratory")
        self.assertEqual(normalized["customer_number_y"], "2")
        self.assertEqual(record["source_values"]["Customer Number_x"], "Synthetic Laboratory")
        self.assertIn("Cats", normalized["animal_use_fields_present"])
        self.assertEqual(normalized["awa_coverage_state"], "source_profile_only_unknown_completeness")

    def test_amendment_versions_are_distinct_evidence(self):
        lines = (ROOT / "fixtures/annual_reports.csv").read_text(encoding="utf-8").splitlines()
        lines[0] += ",Amendment Number"
        lines[1] += ",1"
        lines.append(lines[1].rsplit(",1", 1)[0] + ",2")
        result = AphisPublicSearchAdapter().parse_bytes(("\n".join(lines) + "\n").encode())
        self.assertEqual(len(result["accepted"]), 2)
        self.assertEqual({row["normalized"]["evidence_type"] for row in result["accepted"]}, {"amendments"})
        self.assertNotEqual(result["accepted"][0]["source_record_key"], result["accepted"][1]["source_record_key"])

    def test_short_rows_fail_closed_as_schema_drift(self):
        with self.assertRaises(AphisContractError):
            AphisPublicSearchAdapter().parse_bytes(b"Account Name,Certificate Number,Certificate Status\nOnly One Cell\n")

    def test_multiline_csv_fields_and_header_only_exports_fail_closed(self):
        multiline = (
            b"Account Name,Customer Number,Certificate Number,License Type,Certificate Status,Status Date\n"
            b"\"Synthetic\nRegistrant\",1,00-B-0001,Class B,Active,2026-01-01\n"
        )
        result = AphisPublicSearchAdapter().parse_bytes(multiline)
        self.assertEqual(result["accepted"][0]["normalized"]["account_name"], "Synthetic\nRegistrant")
        with self.assertRaises(AphisContractError):
            AphisPublicSearchAdapter().parse_bytes(
                b"Account Name,Customer Number,Certificate Number,License Type,Certificate Status,Status Date\n"
            )

    def test_run_is_idempotent_and_reconciles_every_row(self):
        raw = (ROOT / "fixtures/inspections.csv").read_bytes()
        artifact = SourceArtifact("https://example.invalid/aphis.csv", "2026-09-15T00:00:00Z", hashlib.sha256(raw).hexdigest(), len(raw), code_version="test", config_version="test")
        with tempfile.TemporaryDirectory() as directory:
            first = AphisPublicSearchAdapter().run(ROOT / "fixtures/inspections.csv", Path(directory) / "one", artifact)
            second = AphisPublicSearchAdapter().run(ROOT / "fixtures/inspections.csv", Path(directory) / "two", artifact)
            self.assertEqual(first["normalized_sha256"], second["normalized_sha256"])
            self.assertEqual(first["parsed_sha256"], second["parsed_sha256"])
            self.assertEqual(first["input_rows"], first["normalized_rows"] + first["quarantined_rows"])
            self.assertEqual(first["release_state"], "not-created")

if __name__ == "__main__": unittest.main()
