import tempfile
import unittest
from pathlib import Path

from .v1_inventory import inventory_v1


class V1InventoryTests(unittest.TestCase):
    def test_reports_aggregate_legacy_quality_without_claiming_currentness(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "locations.csv"
            path.write_text("establishment_id,latitude,longitude\nA,1,2\nA,,\n,3,4\n", encoding="utf-8")
            report = inventory_v1(path)
        self.assertEqual(report["counts"], {"rows": 3, "keys_present": 2, "keys_missing": 1, "duplicate_keys": 1, "coordinate_pairs_present": 2})
        self.assertEqual(report["comparison_status"], "blocked_no_private_v2_artifact")
        self.assertFalse(report["interpretation"]["v1_rows_are_current"])
        self.assertFalse(report["interpretation"]["missing_v2_means_closed"])


if __name__ == "__main__":
    unittest.main()
