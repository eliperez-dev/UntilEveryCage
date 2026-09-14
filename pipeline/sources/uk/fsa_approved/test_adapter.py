import tempfile
import hashlib
import json
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
            raw = (FIXTURES / "valid.csv").read_bytes()
            artifact = {"source_url": "https://example.invalid/fsa", "retrieved_at_utc": "2026-09-14T00:00:00Z", "checksum_sha256": hashlib.sha256(raw).hexdigest(), "byte_size": len(raw), "effective_date": "2026-09-01"}
            self.assertEqual(self.adapter.run(FIXTURES / "valid.csv", first, artifact), self.adapter.run(FIXTURES / "valid.csv", second, artifact))
            self.assertFalse((first / "released" / "records.jsonl").exists())
            self.assertEqual((first / "manifest.json").read_bytes(), (second / "manifest.json").read_bytes())

    def test_source_artifact_is_required_and_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            source = FIXTURES / "valid.csv"
            with self.assertRaises(FsaContractError):
                self.adapter.run(source, Path(directory) / "missing-artifact")
            raw = source.read_bytes()
            artifact = {"source_url": "https://example.invalid/fsa", "retrieved_at_utc": "2026-09-14T00:00:00Z", "checksum_sha256": "0" * 64, "byte_size": len(raw)}
            with self.assertRaises(FsaContractError):
                self.adapter.run(source, Path(directory) / "bad-hash", artifact)

    def test_monthly_profile_enforces_withholding_coverage_duplicates_and_coordinates(self):
        monthly = "AppNo,TradingName,Country,CompetentAuthority,X,Y,AddressWithheld,All_Activities,Address1,Town,Postcode\nA-1,Example,Wales,Food Standards Agency,-3.18,51.48,No,CP,Industrial Road,Cardiff,CF1\nA-2,Withheld,England,Food Standards Agency,-0.12,51.50,Yes,SH,Private Road,London,SW1\nA-2,Duplicate,England,Food Standards Agency,-0.11,51.51,No,CP,Second Road,London,SW2\nA-3,Out of scope,Jersey,Food Standards Agency,-2.1,49.2,No,CP,Island Road,St Helier,JE1\n"
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "monthly.csv"
            raw = monthly.encode("cp1252")
            source.write_bytes(raw)
            artifact = {"source_url": "https://example.invalid/monthly.csv", "retrieved_at_utc": "2026-09-14T00:00:00Z", "checksum_sha256": hashlib.sha256(raw).hexdigest(), "byte_size": len(raw), "effective_date": "2026-09-01"}
            result = self.adapter.parse_bytes(raw)
            self.assertEqual(result.profile, "monthly")
            self.assertEqual(len(result.accepted), 1)
            self.assertEqual(len(result.quarantined), 3)
            withheld = next(item for item in result.quarantined if item["record"]["normalized"]["privacy_gate"] == "restricted-withheld-address")
            self.assertIsNone(withheld["record"]["normalized"]["coordinates"])
            manifest = self.adapter.run(source, Path(directory) / "run", artifact)
            self.assertEqual(manifest["release_state"], "not-created")
            self.assertEqual(manifest["coverage_counts"], {"England": 2, "Jersey": 1, "Wales": 1})

    def test_monthly_generic_facility_building_name_is_not_privacy_quarantine(self):
        monthly = "AppNo,TradingName,Country,CompetentAuthority,X,Y,AddressWithheld,All_Activities,Address1,Town,Postcode\nA-1,House Foods,England,Food Standards Agency,-0.12,51.50,No,CP,House Farm,London,SW1\n"
        result = self.adapter.parse_bytes(monthly.encode("cp1252"))
        self.assertEqual(len(result.accepted), 1)
        self.assertEqual(result.accepted[0]["normalized"]["address_lines"], ("House Farm", None, None))

    def test_monthly_explicit_private_address_indicator_remains_quarantined(self):
        monthly = "AppNo,TradingName,Country,CompetentAuthority,X,Y,AddressWithheld,All_Activities,Address1,Town,Postcode\nA-1,Private Foods,England,Food Standards Agency,-0.12,51.50,No,CP,Flat 2,London,SW1\n"
        result = self.adapter.parse_bytes(monthly.encode("cp1252"))
        self.assertEqual(len(result.accepted), 0)
        self.assertEqual(result.quarantined[0]["reasons"], ("address_privacy_risk",))


if __name__ == "__main__":
    unittest.main()
