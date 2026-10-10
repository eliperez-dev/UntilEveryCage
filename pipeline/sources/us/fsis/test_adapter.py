import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from pipeline.contracts.adapter_contract import SourceArtifact
from .adapter import FsisContractError, FsisMpiAdapter

ROOT = Path(__file__).parent

class FsisAdapterTests(unittest.TestCase):
    def test_valid_fixture_preserves_source_values_and_blocks_coordinates(self):
        raw = (ROOT / "fixtures/valid.csv").read_bytes(); adapter = FsisMpiAdapter(); result = adapter.parse_bytes(raw)
        self.assertEqual(result["input_rows"], 2); self.assertEqual(len(result["accepted"]), 2); self.assertFalse(result["quarantined"])
        row = result["accepted"][0]; self.assertEqual(row["source_values"]["directory"]["phone"], "555-0100")
        self.assertEqual(row["normalized"]["coordinates"]["latitude"], 32.1); self.assertEqual(row["normalized"]["country_code"], "US")
        self.assertEqual(row["normalized"]["coordinate_gate"], "review_required")

    def test_directory_and_demographics_reconcile_on_exact_native_keys(self):
        result = FsisMpiAdapter().parse_sources(
            (ROOT / "fixtures/valid.csv").read_bytes(),
            (ROOT / "fixtures/demographics.csv").read_bytes(),
        )
        self.assertEqual(len(result["accepted"]), 2)
        self.assertEqual(result["matched_demographic_rows"], 2)
        row = result["accepted"][0]["normalized"]
        self.assertEqual(row["species_slaughtered"]["beef_cow_slaughter"], "Yes")
        self.assertEqual(row["processing_activities"]["raw_intact_beef_processing"], "Yes")
        self.assertEqual(row["inspection_attributes"]["inspection_system_nsis"], "Yes")
        self.assertEqual(result["accepted"][0]["source_values"]["demographics"]["establishment_id"], "FSIS-001")
        self.assertEqual(result["source_metrics"]["source_native_establishments"], 2)
        self.assertEqual(result["source_metrics"]["duplicate_directory_aliases"], 0)
        self.assertEqual(result["source_metrics"]["category_coverage"]["slaughter_rows"], 2)
        self.assertEqual(result["source_metrics"]["category_coverage"]["processing_rows"], 2)

    def test_negative_flags_and_volume_codes_are_preserved_without_activity_inference(self):
        directory = (
            b"establishment_id,establishment_name,processing_volume_category,slaughter_volume_category,dbas,grant_date,district\n"
            b"FSIS-100,Fixture Plant,2.0,3.0,Fixture DBA,2026-01-01,001\n"
        )
        demographics = (
            b"establishment_id,beef_cow_slaughter,raw_intact_beef_processing\n"
            b"FSIS-100,No,No\n"
        )
        result = FsisMpiAdapter().parse_sources(directory, demographics)
        normalized = result["accepted"][0]["normalized"]
        self.assertEqual(normalized["species_slaughtered"]["beef_cow_slaughter"], "No")
        self.assertEqual(normalized["processing_activities"]["raw_intact_beef_processing"], "No")
        self.assertEqual(normalized["activity_categories"], ())
        self.assertEqual(normalized["activity_volume_codes"]["processing_volume_category"],
                         {"code": "2.0", "unit": None, "unit_state": "not_supplied_by_source"})
        self.assertEqual(normalized["dba_names"], "Fixture DBA")
        self.assertEqual(normalized["administrative_facts"]["grant_date"], "2026-01-01")
        self.assertEqual(result["source_metrics"]["category_coverage"]["no_activity_category_rows"], 1)

    def test_ordinal_slaughter_only_class_never_becomes_a_slaughter_flag(self):
        directory = b"establishment_id,establishment_name\nFSIS-101,Fixture Plant\n"
        demographics = (
            b"establishment_id,slaughter_only_class,beef_cow_slaughter\n"
            b"FSIS-101,1,Yes\n"
        )
        normalized = FsisMpiAdapter().parse_sources(directory, demographics)["accepted"][0]["normalized"]
        self.assertNotIn("slaughter_only_class", normalized["species_slaughtered"])
        self.assertEqual(normalized["species_slaughtered"]["beef_cow_slaughter"], "Yes")

    def test_unmatched_demographics_are_quarantined_not_dropped(self):
        demographic = b"establishment_number,goat_slaughter\nNOT-IN-DIRECTORY,Yes\n"
        result = FsisMpiAdapter().parse_sources((ROOT / "fixtures/valid.csv").read_bytes(), demographic)
        self.assertEqual(len(result["accepted"]), 2)
        self.assertEqual(result["orphan_demographic_rows"], 1)
        self.assertIn("unmatched_demographic_identity", result["quarantined"][-1]["reasons"])

    def test_demographic_identifier_conflict_does_not_join_on_one_matching_alias(self):
        demographic = (
            b"establishment_id,establishment_number,beef_cow_slaughter\n"
            b"FSIS-001,WRONG-NUMBER,Yes\n"
            b"FSIS-002,P002,Yes\n"
        )
        result = FsisMpiAdapter().parse_sources((ROOT / "fixtures/valid.csv").read_bytes(), demographic)
        self.assertEqual(len(result["accepted"]), 1)
        self.assertEqual(result["matched_demographic_rows"], 1)
        reasons = [reason for item in result["quarantined"] for reason in item["reasons"]]
        self.assertIn("conflicting_demographic_identity", reasons)

    def test_multiline_csv_fields_and_header_only_exports_fail_closed(self):
        multiline = b"establishment_id,establishment_name,state\nFSIS-100,\"Plant\nNorth\",TX\n"
        result = FsisMpiAdapter().parse_bytes(multiline)
        self.assertEqual(result["accepted"][0]["normalized"]["canonical_name"], "Plant\nNorth")
        with self.assertRaises(FsisContractError):
            FsisMpiAdapter().parse_bytes(b"establishment_id,establishment_name,state\n")

    def test_duplicates_missing_name_and_unknown_state_quarantine(self):
        result = FsisMpiAdapter().parse_bytes((ROOT / "fixtures/malformed.csv").read_bytes())
        self.assertEqual(len(result["accepted"]), 0); self.assertEqual(len(result["quarantined"]), 3)
        reasons = [set(item["reasons"]) for item in result["quarantined"]]
        self.assertTrue(all("duplicate_establishment_identity" in reason for reason in reasons[:2]))
        self.assertIn("unknown_state", reasons[2]); self.assertIn("missing_establishment_name", reasons[2])

    def test_schema_drift_fails_closed(self):
        with self.assertRaises(FsisContractError): FsisMpiAdapter().parse_bytes(b"wrong,header\n1,2\n")

    def test_run_is_deterministic_and_private(self):
        raw=(ROOT/"fixtures/valid.csv").read_bytes(); artifact=SourceArtifact("https://example.invalid/fsis.csv","2026-09-15T00:00:00Z",hashlib.sha256(raw).hexdigest(),len(raw),effective_date="2026-09-01",code_version="test",config_version="test")
        with tempfile.TemporaryDirectory() as directory:
            manifest=FsisMpiAdapter().run(ROOT/"fixtures/valid.csv",directory,artifact)
            self.assertEqual(manifest["release_state"],"not-created"); self.assertEqual(manifest["publication_state"],"private-candidate")
            self.assertEqual(manifest["input_rows"],manifest["normalized_rows"]+manifest["quarantined_rows"])
            self.assertTrue((Path(directory)/"parsed/records.jsonl").exists()); self.assertEqual(json.loads((Path(directory)/"normalized/records.jsonl").read_text().splitlines()[0])["normalized"]["publication_gate"],"blocked")
            self.assertEqual(manifest["source_profile"], "fsis-mpi-directory-only")
            self.assertFalse(manifest["demographics_parity"]["complete"])

if __name__ == "__main__": unittest.main()
