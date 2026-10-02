import unittest

from .adapter import CataloniaFeedSandachAdapter, EXPORT_HEADERS, SOURCE_ID


class CataloniaFeedSandachTests(unittest.TestCase):
    def sample(self):
        return (",".join('"' + value.replace('"', '""') + '"' for value in EXPORT_HEADERS) +
                '\n"PRIVATE NAME","PRIVATE STREET","Barcelona","08001","08019","Barcelonès","13","Barcelona","REG-1","Feed activity","AA","2026-01-01","PRIVATE COMPANY"\n').encode()

    def test_retains_official_location_fields_for_private_enrichment(self):
        result = CataloniaFeedSandachAdapter().parse_bytes(self.sample())
        self.assertEqual(result["input_rows"], 1)
        self.assertEqual(len(result["accepted"]), 1)
        row = result["accepted"][0]
        self.assertEqual(row["source_id"], SOURCE_ID)
        self.assertEqual(row["source_values"], {})
        self.assertEqual(row["normalized"]["address"], "PRIVATE STREET")
        self.assertEqual(row["normalized"]["postal_code"], "08001")
        self.assertEqual(row["normalized"]["municipality_code"], "08019")
        self.assertNotIn("coordinates", row["normalized"])
        self.assertEqual(row["normalized"]["coordinate_state"], "not-supplied")
        serialized = str(row)
        self.assertIn("PRIVATE STREET", serialized)
        for private_value in ("PRIVATE NAME", "PRIVATE COMPANY"):
            self.assertNotIn(private_value, serialized)

    def test_fails_closed_on_schema_drift(self):
        bad = self.sample().replace(b"Nom establiment", b"Unknown field")
        with self.assertRaisesRegex(ValueError, "schema drift"):
            CataloniaFeedSandachAdapter().parse_bytes(bad)

    def test_quarantines_missing_required_identity_without_exposing_values(self):
        raw = self.sample().replace(b"REG-1", b"")
        result = CataloniaFeedSandachAdapter().parse_bytes(raw)
        self.assertEqual(len(result["accepted"]), 0)
        self.assertEqual(len(result["quarantined"]), 1)
        self.assertNotIn("PRIVATE NAME", str(result["quarantined"]))


if __name__ == "__main__":
    unittest.main()
