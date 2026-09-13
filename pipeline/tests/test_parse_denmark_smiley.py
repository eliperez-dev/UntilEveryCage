import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "stages" / "parse-denmark-smiley.py"
SPEC = importlib.util.spec_from_file_location("parse_denmark_smiley", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


XML = """<?xml version="1.0" encoding="utf-8"?>
<Root><Row><ID_nummer>123</ID_nummer><Virksomhed>Test Fisk</Virksomhed><Geo_Lat>55.6</Geo_Lat><Geo_Lng>12.5</Geo_Lng><URL>https://example.test/123</URL></Row>
<Row><ID_nummer>124</ID_nummer><Virksomhed>Adresse Only</Virksomhed><Adresse>Testvej 1</Adresse><Geo_Lat /><Geo_Lng /></Row></Root>
"""


class DenmarkParserTests(unittest.TestCase):
    def test_parse_preserves_source_fields_and_nulls(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.xml"
            output_dir = root / "staging"
            source.write_text(XML, encoding="utf-8")
            output = MODULE.parse_file(source, output_dir, "https://example.test/source.xml", progress_every=1)
            rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
            metadata = json.loads((output_dir / "run-metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["source_record_key"], "123")
            self.assertEqual(rows[0]["fields"]["Virksomhed"], "Test Fisk")
            self.assertIsNone(rows[0]["fields"].get("Adresse"))
            self.assertEqual(metadata["rows_parsed"], 2)
            self.assertEqual(metadata["rows_missing_coordinates"], 1)
            self.assertEqual(metadata["status"], "success")
            self.assertEqual(len(metadata["input_sha256"]), 64)

    def test_normalization_preserves_source_and_maps_current_schema(self):
        envelope = {
            "source_id": "dk.smiley",
            "source_artifact_sha256": "a" * 64,
            "fields": {"ID_nummer": "123", "Virksomhed": "Test Fisk", "Adresse": "Testvej 1", "Postnummer": "1000", "By": "København", "FVST_branchenummer": "DD.47.23.00", "Seneste_kontrol_dato": "02/09/2024"},
        }
        script = Path(__file__).parents[1] / "scripts" / "stages" / "normalize-denmark-smiley.py"
        spec = importlib.util.spec_from_file_location("normalize_denmark_smiley", script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        result = module.normalize_record(envelope)
        self.assertEqual(result["source_record_key"], "123")
        self.assertEqual(result["name"], "Test Fisk")
        self.assertEqual(result["address"]["country_code"], "DK")
        self.assertEqual(result["activity"]["code"], "DD.47.23.00")
        self.assertEqual(result["latest_inspection_date"], "2024-09-02")
        self.assertIsNone(result["coordinates"]["latitude"])
        self.assertEqual(result["source_fields"]["Adresse"], "Testvej 1")

    def test_invalid_xml_fails_without_success_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "invalid.xml"
            source.write_text("<document><row>", encoding="utf-8")
            with self.assertRaises(Exception):
                MODULE.parse_file(source, root / "staging", "https://example.test/source.xml")
            self.assertFalse((root / "staging" / "run-metadata.json").exists())


if __name__ == "__main__":
    unittest.main()
