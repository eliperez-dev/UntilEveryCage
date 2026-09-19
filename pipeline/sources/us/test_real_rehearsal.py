import csv
import unittest
from pathlib import Path

from .real_rehearsal import build_ledger_rows, row_free_metrics


ROOT = Path(__file__).resolve().parents[3]


def _rows(path: Path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


class UsRealRehearsalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fsis = ROOT / "static_data/us/locations.csv"
        cls.inspections = ROOT / "static_data/us/inspection_reports.csv"
        cls.annual = ROOT / "static_data/us/aphis_data_final.csv"
        cls.ledger, cls.skipped = build_ledger_rows(_rows(cls.fsis), _rows(cls.inspections), _rows(cls.annual))
        cls.report = row_free_metrics(fsis_path=cls.fsis, inspection_path=cls.inspections, annual_path=cls.annual, ledger_rows=cls.ledger, skipped=cls.skipped)

    def test_real_strata_reconcile_and_keep_federal_state_boundary(self):
        self.assertEqual(self.report["strata"], {"fsis_locations": 7101, "aphis_inspections": 4507, "aphis_annual_reports": 1013})
        self.assertTrue(self.report["quality"]["input_rows_reconciled_to_source_local_graph_or_skip"])
        self.assertFalse(self.report["source_boundaries"]["state_programs"]["included"])
        self.assertEqual(self.report["source_boundaries"]["fsis"]["jurisdiction"], "federal")

    def test_graph_exercises_source_local_edges_without_cross_source_matching(self):
        counts = self.report["graph"]["relationship_counts"]
        self.assertGreater(counts["establishment_approval_for"], 7000)
        self.assertGreater(counts["inspection_observes"], 4000)
        self.assertGreater(counts["aggregate_describes"], 1000)
        self.assertGreater(counts["regulatory_authority_for"], 12000)
        self.assertEqual(self.report["graph"]["cross_source_identity_joins_attempted"], 0)
        self.assertEqual(self.report["graph"]["name_address_phone_coordinate_joins_attempted"], 0)

    def test_candidate_gates_and_row_free_report(self):
        self.assertEqual(self.report["publication_eligibility"], "blocked")
        self.assertFalse(self.report["graph"]["all_candidates"]["auto_merge"])
        self.assertEqual(self.report["graph"]["all_candidates"]["publication_gate"], "blocked")
        serialized = str(self.report)
        for forbidden in ("Godshall", "Auburn University", "street", "latitude", "longitude", "source_values", "display_name"):
            self.assertNotIn(forbidden, serialized)


if __name__ == "__main__":
    unittest.main()
