import json
import tempfile
import unittest
from pathlib import Path

from .reconcile import build_v1_crosswalk


class UsCrosswalkTests(unittest.TestCase):
    def test_crosswalk_is_exact_row_free_and_does_not_inherit_v1_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "v1.csv").write_text("establishment_id,name\nFSIS-001,Legacy name\nFSIS-999,Not observed\n", encoding="utf-8")
            rows = [
                {"entity_type": "facility", "source_id": "us.fsis", "source_native_id": "FSIS-001", "observation_date": "2026-09-01"},
                {"entity_type": "operator", "source_id": "us.aphis", "source_native_id": "registrations:customer:1", "observation_date": "2026-09-01"},
            ]
            (root / "entities.jsonl").write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
            report = build_v1_crosswalk(root / "v1.csv", root / "entities.jsonl")
        self.assertEqual(report["counts"]["matched"], 1)
        self.assertEqual(report["counts"]["not_observed_in_v2"], 1)
        self.assertFalse(report["interpretation"]["not_observed_in_v2_is_closure"])
        self.assertFalse(report["interpretation"]["v1_identity_assumptions_inherited"])
        self.assertFalse(report["interpretation"]["raw_rows_in_report"])


if __name__ == "__main__":
    unittest.main()
