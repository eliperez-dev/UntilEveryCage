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
        row = result["accepted"][0]; self.assertEqual(row["source_values"]["phone"], "555-0100")
        self.assertIsNone(row["normalized"]["coordinates"]); self.assertEqual(row["normalized"]["country_code"], "US")

    def test_duplicates_missing_name_and_unknown_state_quarantine(self):
        result = FsisMpiAdapter().parse_bytes((ROOT / "fixtures/malformed.csv").read_bytes())
        self.assertEqual(len(result["accepted"]), 0); self.assertEqual(len(result["quarantined"]), 3)
        reasons = [set(item["reasons"]) for item in result["quarantined"]]
        self.assertTrue(all("duplicate_establishment_id" in reason for reason in reasons[:2]))
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

if __name__ == "__main__": unittest.main()
