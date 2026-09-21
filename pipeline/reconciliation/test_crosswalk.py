import json
import tempfile
import unittest
from pathlib import Path

from .crosswalk import compare_v1_v2


class CrosswalkTests(unittest.TestCase):
    def test_exact_matches_and_ambiguous_keys_are_row_free(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "v1.csv").write_text("id,lat\nA,1\nB,\nB,2\nC,3\n", encoding="utf-8")
            v2 = [
                {"source_id": "dk.smiley", "source_record_key": "A", "normalized": {"coordinates": [1, 2], "classification": "facility", "effective_date": "2026-01-01"}},
                {"source_id": "dk.smiley", "source_record_key": "B", "normalized": {"coordinates": None}},
                {"source_id": "dk.smiley", "source_record_key": "B", "normalized": {"coordinates": None}},
                {"source_id": "dk.smiley", "source_record_key": "D", "normalized": {"coordinates": None}, "quarantine_reason": "review"},
            ]
            (root / "v2.jsonl").write_text("\n".join(json.dumps(row) for row in v2), encoding="utf-8")
            report = compare_v1_v2(root / "v1.csv", root / "v2.jsonl", v1_key="id", v2_key="source_record_key", v1_country="DK", v2_source_id="dk.smiley", v1_coordinate_field="lat")
        self.assertEqual(report["counts"], {"v1_rows": 4, "v2_rows": 4, "matched": 1, "ambiguous": 1, "v1_missing_key": 0, "v2_missing_key": 0, "v2_only": 1, "not_observed_in_v2": 1})
        self.assertFalse(report["interpretation"]["not_observed_in_v2_is_closure"])
        self.assertFalse(report["interpretation"]["raw_rows_in_report"])
        self.assertEqual(report["quarantine"]["v2_rows"], 1)

    def test_missing_keys_and_unknown_semantics_are_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "v1.csv").write_text("id\n\n", encoding="utf-8")
            (root / "v2.jsonl").write_text(json.dumps({"normalized": {}}) + "\n", encoding="utf-8")
            report = compare_v1_v2(root / "v1.csv", root / "v2.jsonl", v1_key="id", v2_key="source_record_key", v1_country="IT", v2_source_id="it.853-2004")
        self.assertEqual(report["counts"]["v1_missing_key"], 0)  # csv blank lines are not data rows
        self.assertEqual(report["counts"]["v2_missing_key"], 1)
        self.assertEqual(report["v1_coordinates"], {"not_compared": 0})
        self.assertEqual(report["interpretation"]["identity_decisions_created"], False)


if __name__ == "__main__":
    unittest.main()
