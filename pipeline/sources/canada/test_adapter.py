import hashlib
import io
import json
import zipfile
import tempfile
import unittest
from pathlib import Path

from pipeline.common.orchestrator import run_private_lifecycle
from pipeline.contracts.adapter_contract import SourceArtifact
from pipeline.contracts.graph_candidate_handoff import validate_graph_candidate
from .adapter import CfiaFederalMeatAdapter, OntarioMeatPlantsAdapter

FIXTURES = Path(__file__).parent / "fixtures"


class CanadaAdapterTests(unittest.TestCase):
    def test_cfia_xlsx_preserves_cell_text_and_detects_workbook_schema(self):
        files = {
            "xl/workbook.xml": '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Registry" sheetId="1" r:id="rId1"/></sheets></workbook>',
            "xl/_rels/workbook.xml.rels": '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml" Type="x"/></Relationships>',
            "xl/worksheets/sheet1.xml": '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>Establishment Number</t></is></c><c r="B1" t="inlineStr"><is><t>Operator Name</t></is></c><c r="C1" t="inlineStr"><is><t>Function Code</t></is></c></row><row r="2"><c r="A2" t="inlineStr"><is><t>0007</t></is></c><c r="B2" t="inlineStr"><is><t>Synthetic Federal Plant</t></is></c><c r="C2" t="inlineStr"><is><t>1A</t></is></c></row></sheetData></worksheet>',
        }
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as archive:
            for name, text in files.items(): archive.writestr(name, text)
        result = CfiaFederalMeatAdapter().parse_bytes(buf.getvalue())
        self.assertEqual(len(result["accepted"]), 1)
        self.assertEqual(result["accepted"][0]["source_values"]["Establishment Number"], "0007")
        self.assertEqual(result["delimiter"], "xlsx")
    def test_bilingual_composite_headers_from_live_ontario_file_are_supported(self):
        content = ('"Plant Name_ Nom de l\'usine","Plant Number_No. de l\'usine",'
                   '"Address_Adresse","City_Ville","Province_Province",'
                   '"Postal Code_Code postal","Telephone_Telephone",Latitude,Longitude,'
                   '"Animal Class_Catégorie d\'animaux","Plant Type_Type",'
                   '"Function Codes_Codes de fonction","Status_Statut"\n'
                   'Synthetic Plant,SP-001,"Industrial Road 1",Toronto,ON,M1M 1M1,'
                   '555-0100,43.1,-79.1,Abattoir,Abattoir,1,current\n').encode()
        result = OntarioMeatPlantsAdapter().parse_bytes(content)
        self.assertEqual(len(result["accepted"]), 1)
        self.assertEqual(result["accepted"][0]["normalized"]["activity_categories"], ("slaughter",))

    def test_ontario_is_provincial_and_privacy_safe(self):
        adapter = OntarioMeatPlantsAdapter(); result = adapter.parse_file(FIXTURES / "ontario.csv")
        self.assertEqual(len(result["accepted"]), 2); self.assertEqual(len(result["quarantined"]), 1)
        row = result["accepted"][0]
        self.assertEqual(row["normalized"]["jurisdiction_level"], "provincial"); self.assertEqual(row["normalized"]["jurisdiction"], "Ontario"); self.assertEqual(row["normalized"]["activity_categories"], ("slaughter",)); self.assertIsNone(row["normalized"]["coordinates"])
        self.assertEqual(row["source_values"]["Phone"], "555-0100")

    def test_cfia_function_codes_and_unknown_code_quarantine(self):
        adapter = CfiaFederalMeatAdapter(); result = adapter.parse_file(FIXTURES / "cfia.csv")
        self.assertEqual(len(result["accepted"]), 2); self.assertEqual(len(result["quarantined"]), 1); self.assertEqual(result["accepted"][0]["normalized"]["activity_categories"], ("slaughter", "cutting")); self.assertEqual(result["accepted"][1]["normalized"]["activity_categories"], ("logistics_and_storage",)); self.assertEqual(result["quarantined"][0]["reasons"], ("unknown_function_code",))

    def test_cfia_current_numbered_workbook_code_columns(self):
        result = CfiaFederalMeatAdapter().parse_bytes(
            b"Establishment Number,Operator Name,CODES_1,CODES_3,CODES_6,CODE_7,CODES_9,CODES_10,EXPORT,TRICHINA\n"
            b'0007,Synthetic Slaughter Plant,"a,h,i",fx,x,Y,B/US,A,D,Y\n'
            b"0008,Synthetic Inspection Facility,,,,,B/US,,,\n"
            b"0009,Synthetic Unknown Plant,,q,,,,,,\n"
        )
        self.assertEqual(len(result["accepted"]), 1)
        row = result["accepted"][0]
        self.assertEqual(row["normalized"]["activity_categories"], ("slaughter", "cutting", "processing", "logistics_and_storage"))
        self.assertEqual(row["source_values"]["EXPORT"], "D")
        self.assertEqual({item["reasons"][0] for item in result["quarantined"]}, {"unknown_function_code", "unsupported_or_missing_facility_activity"})

    def test_federal_and_provincial_lifecycles_are_separate(self):
        with tempfile.TemporaryDirectory() as d:
            for adapter, fixture in ((OntarioMeatPlantsAdapter(), "ontario.csv"), (CfiaFederalMeatAdapter(), "cfia.csv")):
                raw = (FIXTURES / fixture).read_bytes(); artifact = SourceArtifact(adapter.source_url, "2026-09-15T00:00:00Z", hashlib.sha256(raw).hexdigest(), len(raw), code_version=adapter.adapter_version, config_version=adapter.schema_version)
                status = run_private_lifecycle(FIXTURES / fixture, Path(d) / adapter.source_id, artifact, adapter)
                self.assertEqual(status["status"], "candidate-ready"); self.assertEqual(status["manifest"]["jurisdiction_level"], adapter.jurisdiction_level); self.assertTrue((Path(status["run_dir"]) / "release-candidate" / "records.jsonl").exists())

    def test_graph_candidates_are_source_scoped_and_only_explicit_federal_edges_are_emitted(self):
        with tempfile.TemporaryDirectory() as d:
            for adapter, fixture, expected_graph_candidates, expected_relationships in ((OntarioMeatPlantsAdapter(), "ontario.csv", 2, {}), (CfiaFederalMeatAdapter(), "cfia.csv", 3, {"operator": 3, "regulator": 3})):
                raw = (FIXTURES / fixture).read_bytes(); artifact = SourceArtifact(adapter.source_url, "2026-09-15T00:00:00Z", hashlib.sha256(raw).hexdigest(), len(raw), code_version=adapter.adapter_version, config_version=adapter.schema_version)
                status = run_private_lifecycle(FIXTURES / fixture, Path(d) / adapter.source_id, artifact, adapter)
                run = Path(status["run_dir"]); graph_root = run / "graph-candidates"
                summary = json.loads((graph_root / "manifest.json").read_text(encoding="utf-8"))
                self.assertEqual(summary["candidate_count"], expected_graph_candidates)
                self.assertEqual(summary["relationship_counts"], expected_relationships)
                candidates = [path / "graph-candidate.json" for path in graph_root.iterdir() if path.is_dir()]
                self.assertEqual(len(candidates), expected_graph_candidates)
                candidate = json.loads(candidates[0].read_text(encoding="utf-8"))
                validate_graph_candidate(candidate)
                self.assertEqual(candidate["publication"]["publication_status"], "not_eligible")
                if adapter.jurisdiction_level == "provincial":
                    self.assertEqual(candidate["relationships"], [])

    def test_graph_candidate_rerun_is_byte_deterministic(self):
        raw = (FIXTURES / "cfia.csv").read_bytes(); adapter = CfiaFederalMeatAdapter()
        artifact = SourceArtifact(adapter.source_url, "2026-09-15T00:00:00Z", hashlib.sha256(raw).hexdigest(), len(raw), code_version=adapter.adapter_version, config_version=adapter.schema_version)
        with tempfile.TemporaryDirectory() as d:
            first = run_private_lifecycle(FIXTURES / "cfia.csv", Path(d) / "first", artifact, adapter)
            second = run_private_lifecycle(FIXTURES / "cfia.csv", Path(d) / "second", artifact, adapter)
            def payloads(status):
                return sorted(path.read_bytes() for path in (Path(status["run_dir"]) / "graph-candidates").glob("*/graph-candidate.json"))
            self.assertEqual(payloads(first), payloads(second))


if __name__ == "__main__": unittest.main()
