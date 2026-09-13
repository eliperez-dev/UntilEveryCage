import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("city_refs", ROOT / "pipeline/scripts/stages/fetch-denmark-city-references.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class CityReferenceTests(unittest.TestCase):
    def test_normalize_preserves_official_identity_and_visual_center(self):
        records = MODULE.normalize([{
            "id": "abc",
            "primærtnavn": "Testby",
            "visueltcenter": [10.1, 55.2],
        }], "2026-09-13T00:00:00Z", MODULE.URL)
        self.assertEqual(records[0]["source_reference_id"], "abc")
        self.assertEqual(records[0]["reference_longitude"], 10.1)
        self.assertEqual(records[0]["reference_latitude"], 55.2)
        self.assertIsNone(records[0]["postal_code"])

    def test_normalize_skips_records_without_visual_center(self):
        self.assertEqual(MODULE.normalize([{"id": "missing"}], "now", MODULE.URL), [])


if __name__ == "__main__":
    unittest.main()
