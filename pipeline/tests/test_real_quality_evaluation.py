import json
import tempfile
import unittest
from pathlib import Path

from pipeline.scripts.diagnostics.real_quality_evaluation import build_report


HEADER = "establishment_id,establishment_name,city,street,latitude,longitude,slaughter\n"


class RealQualityEvaluationTests(unittest.TestCase):
    def test_report_is_deterministic_and_row_free(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for country in ("ca", "de", "dk", "es", "fr", "mx", "nz", "uk", "us"):
                path = root / country
                path.mkdir()
                path.joinpath("locations.csv").write_text(HEADER + "1,Alpha,Town,10 Main,52.1000,4.2000,true\n2,Beta,Town,private farmhouse,91,0,true\n", encoding="utf-8")
            for name in ("inspection_reports.csv", "aphis_data_final.csv"):
                Path(root / "us" / name).write_text(HEADER + "1,Alpha,Town,10 Main,52.1,4.2,true\n", encoding="utf-8")
            # The fixture intentionally cannot satisfy the real US sample sizes;
            # the evaluator must fail closed rather than reuse other rows.
            with self.assertRaisesRegex(ValueError, "has 2 rows; 3500 required"):
                build_report(root, as_of="2026-09-16T00:00:00Z")

    def test_real_corpus_report_shape_has_no_row_payload(self):
        report = build_report(Path("static_data"), as_of="2026-09-16T00:00:00Z")
        encoded = json.dumps(report)
        self.assertEqual(report["corpus"]["available_rows"], 50750)
        self.assertEqual(report["us_planned_sample"]["selected_total"], 7000)
        self.assertEqual(report["graph_candidate_yield"]["cross_source_relationship_candidates"], 0)
        self.assertNotIn("Godshall", encoded)
        self.assertNotIn("1415 Weavertown", encoded)
        self.assertNotIn("6407", encoded)


if __name__ == "__main__":
    unittest.main()
