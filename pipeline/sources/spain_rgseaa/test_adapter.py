import hashlib
import importlib.util
import json
import tempfile
import unittest
import zipfile
from io import BytesIO
from pathlib import Path

from pipeline.contracts.adapter_contract import SourceArtifact
from pipeline.geocoding.source_queue import source_geocode_query

from .adapter import ANIMAL_ORIGIN_KEYS, HEADERS, RgseaaAdapter, SOURCE_ID


def workbook(rows, headers=HEADERS):
    shared = []
    indexes = {}

    def add(value):
        if value not in indexes:
            indexes[value] = len(shared)
            shared.append(value)
        return indexes[value]

    title = add("Listado de empresas alimentarias inscritas en España (RGSEAA)\n(actualizado a 1 de septiembre de 2026)")
    values = [add(value) for value in headers]
    for row in rows:
        values.extend(add(value) for value in row)
    strings = "".join(f'<si><t>{value}</t></si>' for value in shared)
    sheet_rows = [f'<row r="1"><c r="A1" t="s"><v>{title}</v></c></row>',
                  '<row r="2">' + "".join(f'<c r="{chr(65+i)}2" t="s"><v>{v}</v></c>' for i, v in enumerate(values[:7])) + '</row>']
    for rownum, start in enumerate(range(7, len(values), 7), start=3):
        row_values = values[start:start+7]
        sheet_rows.append(f'<row r="{rownum}">' + "".join(
            f'<c r="{chr(65+i)}{rownum}" t="s"><v>{v}</v></c>' for i, v in enumerate(row_values)) + '</row>')
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("xl/workbook.xml", '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Hoja1" sheetId="1" r:id="rId1"/></sheets></workbook>')
        archive.writestr("xl/_rels/workbook.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>')
        archive.writestr("xl/sharedStrings.xml", f'<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">{strings}</sst>')
        archive.writestr("xl/worksheets/sheet1.xml", f'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>{"".join(sheet_rows)}</sheetData></worksheet>')
    return buffer.getvalue()


class RgseaaAdapterTests(unittest.TestCase):
    def test_private_business_name_does_not_clear_publication_or_explicit_restrictions(self):
        script = Path(__file__).parents[2] / "scripts" / "maintenance" / "import-real-preview.py"
        spec = importlib.util.spec_from_file_location("spain_private_name_import", script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        row = RgseaaAdapter().parse_bytes(workbook([
            ("10.00001", "PRIVATE BUSINESS", "Industrial Address", "Madrid", "Madrid", "10", "Meat"),
        ]))["accepted"][0]
        self.assertEqual(module.parse_row(SOURCE_ID, row)[11], "PRIVATE BUSINESS")
        self.assertEqual(row["normalized"]["privacy_gate"], "restricted-private-evidence")
        self.assertEqual(row["normalized"]["publication_gate"], "blocked")
        for gate in ("blocked", "restricted-withheld-address", "restricted"):
            row["normalized"]["privacy_gate"] = gate
            self.assertIsNone(module.parse_row(SOURCE_ID, row)[11])

    def test_uses_exact_workbook_schema_and_official_animal_origin_keys(self):
        raw = workbook([
            ("10.00001", "PRIVATE BUSINESS", "Industrial Address", "Province Name", "Autonomous Community", "10", "Carnes y derivados"),
            ("20.00002", "NON-ANIMAL", "Other Address", "Madrid", "Madrid", "20", "Harinas y derivados"),
        ])
        result = RgseaaAdapter().parse_bytes(raw)
        self.assertEqual(result["input_rows"], 2)
        self.assertEqual(result["candidate_rows"], 1)
        self.assertEqual(result["source_update_date"], "2026-09-01")
        self.assertEqual(ANIMAL_ORIGIN_KEYS, {"10", "12", "14", "15"})
        eligible, other = result["accepted"]
        self.assertEqual(eligible["source_id"], SOURCE_ID)
        self.assertEqual(eligible["normalized"]["source_classification_code"], "10")
        self.assertEqual(eligible["normalized"]["name"], "PRIVATE BUSINESS")
        self.assertEqual(eligible["normalized"]["privacy_gate"], "restricted-private-evidence")
        self.assertEqual(eligible["normalized"]["publication_gate"], "blocked")
        self.assertEqual(eligible["normalized"]["address"], "Industrial Address")
        self.assertEqual(eligible["normalized"]["coordinate_state"], "not-supplied")
        self.assertEqual(eligible["source_values"]["Razon_Social"], "PRIVATE BUSINESS")
        self.assertEqual(other["normalized"]["source_scope_eligibility"], "out_of_scope")

    def test_scope_handoff_preserves_eligible_business_name_privately(self):
        raw = workbook([
            ("10.00001", "PRIVATE BUSINESS", "Industrial Address", "Province Name", "Autonomous Community", "10", "Carnes y derivados"),
            ("20.00002", "NON-ANIMAL", "Other Address", "Madrid", "Madrid", "20", "Harinas y derivados"),
        ])
        result = RgseaaAdapter().parse_bytes(raw)
        artifact = SourceArtifact("https://www.aesan.gob.es/dam/jcr%3A0e74247c-5a4e-4c79-863b-b5dae6e79ada/260901_Industrias_RGSEAA.xlsx",
                                  "2026-10-25T00:00:00Z", hashlib.sha256(raw).hexdigest(), len(raw))
        self.assertEqual(result["candidate_rows"], 1)
        row = next(row for row in result["accepted"] if row["normalized"]["source_scope_eligibility"] == "eligible")
        self.assertEqual(row["normalized"]["source_classification_label"], "Carnes y derivados")
        self.assertTrue(artifact.sha256)
        with tempfile.TemporaryDirectory() as directory:
            RgseaaAdapter().write_candidate_handoff(directory, artifact, result)
            handoff = Path(directory, "normalized", "records.jsonl").read_text(encoding="utf-8")
            self.assertIn("PRIVATE BUSINESS", handoff)
            self.assertNotIn("NON-ANIMAL", handoff)
            handed_row = json.loads(handoff)
            self.assertEqual(handed_row["source_values"], {})
            self.assertEqual(handed_row["normalized"]["name"], "PRIVATE BUSINESS")
            self.assertEqual(handed_row["normalized"]["publication_gate"], "blocked")
            self.assertEqual(handed_row["normalized"]["source_classification_code"], "10")
            self.assertEqual(handed_row["normalized"]["source_classification_label"], "Carnes y derivados")
            self.assertEqual(handed_row["normalized"]["private_location_evidence"]["address"],
                             "Industrial Address")
            self.assertEqual(handed_row["normalized"]["province"], "Province Name")
            self.assertEqual(handed_row["normalized"]["private_location_evidence"]["region"],
                             "Autonomous Community")
            query = source_geocode_query(handed_row)
            self.assertEqual(query, "Industrial Address, Province Name, Autonomous Community, ES")
            self.assertNotIn("PRIVATE BUSINESS", query)

    def test_schema_drift_fails_closed(self):
        raw = workbook([("10.00001", "NAME", "ADDRESS", "Madrid", "Madrid", "10", "Carnes")],
                       headers=("NEW_FIELD", *HEADERS[1:]))
        with self.assertRaisesRegex(ValueError, "schema drift"):
            RgseaaAdapter().parse_bytes(raw)


if __name__ == "__main__":
    unittest.main()
