import json
import tempfile
import unittest
from pathlib import Path

from .aphis_wave2 import run_wave2


ROOT = Path(__file__).parent


class AphisWave2Tests(unittest.TestCase):
    def test_private_wave_is_bounded_and_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_root = root / "inputs"
            input_root.mkdir()
            (input_root / "ExportData-registrations.csv").write_text(
                "Account Name,Customer Number,Certificate Number,Registration Type,Certificate Status,Status Date\n"
                '"Synthetic Registrant","2","00-R-0002","Class R - Research Facility","Active","2026-01-01"\n',
                encoding="utf-8",
            )
            (input_root / "ExportData-annual_reports.csv").write_text(
                "Customer Number,Certificate Number,Year,Dogs,Cats\n"
                '"2","00-R-0002","2025","","1"\n',
                encoding="utf-8",
            )
            (input_root / "ExportData-inspections.csv").write_text(
                "Customer Number,Certificate Number,Inspection Date,Direct NCIs,Non-Critical NCIs,Critical NCIs,Teachable Moments,Site Name,Legal Name,License-Registration Type,City,State,Zip\n"
                '"2","00-R-0002","2026-02-01","","","","","Synthetic Site","Synthetic Registrant","Class R - Research Facility","Testville","TX","75001"\n',
                encoding="utf-8",
            )

            report = run_wave2(input_root=input_root, run_dir=root / "run")
            self.assertEqual(report["captured_for"], "private/test-only")
            self.assertGreaterEqual(report["graph_projection"]["candidate_relationships"], 2)
            self.assertTrue(report["controls"]["weak_name_address_similarity_not_asserted"])
            self.assertTrue(report["controls"]["suppressed_rows_do_not_enter_candidates"])
            self.assertTrue(report["controls"]["rerun_idempotency_key_equal"])
            self.assertFalse(report["controls"]["public_exposure"])
            self.assertTrue(all(
                result["profiles"][-1] == query["relationship_profile"]
                for query in report["bounded_queries"]
                for result in query["results"]
            ))
            self.assertEqual(
                json.loads((root / "run" / "wave2-report.json").read_text(encoding="utf-8"))["publication"]["publication_status"],
                "not_eligible",
            )


if __name__ == "__main__":
    unittest.main()
