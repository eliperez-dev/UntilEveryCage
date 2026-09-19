import csv
import unittest
from pathlib import Path

from pipeline.statistics.catalog import validate_catalog
from pipeline.statistics.faostat import build_entry


FIXTURE = Path(__file__).parent / "fixtures" / "synthetic_faostat.csv"


class FaostatIngestionTests(unittest.TestCase):
    def rows(self):
        with FIXTURE.open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))

    def test_selects_leaf_rows_converts_thousands_and_ignores_aggregate_rows(self):
        entry = build_entry(
            self.rows(),
            artifact_path="private/synthetic-faostat.csv",
            sha256="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
            byte_size=42,
            retrieved_at_utc="2026-09-15T00:00:00Z",
        )
        self.assertEqual(entry["estimate"]["central"], 72064)
        self.assertEqual(len(entry["components"]), 16)
        self.assertEqual(validate_catalog({"schema_version": "aggregate-statistics-catalog-v1", "statistics": [entry]})["status"], "passed")
        self.assertEqual(entry["components"][4]["source_flag"], "E")

    def test_missing_leaf_row_is_rejected(self):
        rows = self.rows()
        rows = [row for row in rows if row["Item"] != "Meat of turkeys, fresh or chilled"]
        with self.assertRaisesRegex(ValueError, "missing selected FAOSTAT rows"):
            build_entry(rows, artifact_path="private/synthetic.csv", sha256="0" * 64, byte_size=1, retrieved_at_utc="2026-09-15T00:00:00Z")

    def test_source_unit_must_match_selected_definition(self):
        rows = self.rows()
        rows[4]["Unit"] = "An"
        with self.assertRaisesRegex(ValueError, "expected unit"):
            build_entry(rows, artifact_path="private/synthetic.csv", sha256="0" * 64, byte_size=1, retrieved_at_utc="2026-09-15T00:00:00Z")


if __name__ == "__main__":
    unittest.main()
