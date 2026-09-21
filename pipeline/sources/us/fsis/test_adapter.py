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

if __name__ == "__main__": unittest.main()
