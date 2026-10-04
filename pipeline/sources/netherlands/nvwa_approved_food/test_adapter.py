from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from pipeline.contracts.adapter_contract import SourceArtifact
from pipeline.contracts.source_lifecycle import atomic_json
from .acquire import _soap_request
from .adapter import CONFIG, LIST_CODES, NvwaApprovedFoodAdapter, NvwaContractError, _parse_response


def _row(key: str | None, product: str = "beef", name: str = "Synthetic Example") -> str:
    fields = {"plaats":"Exampletown","adres":"1 Sample Street","remark":"",
        "aanvangsdatum":"2020-01-01","specificatiecode":"SYN","opheffingsdatum":"",
        "transportNl":"","diersoortNl":"rund","postcode":"1234 AB",
        "onderzoekLaboratorium":"","transportEn":"","bijzonderheden":"",
        "activiteit":"slaughter","regelgeving":"EC 853/2004","categorie":"Synthetic",
        "erkenningssoort":"approval","handelsnaam":name,"erkenningsnummer":key,
        "diersoortEn":"bovine","producttype":product}
    items = "".join(f"<{k}>{v}</{k}>" for k,v in fields.items() if v is not None)
    return f"<CvgErkendbedrijfUser>{items}</CvgErkendbedrijfUser>"


def _response(rows: list[str]) -> bytes:
    return ("<Envelope><Body><response><erkendebedrijven><array>"+"".join(rows)+
        "</array></erkendebedrijven><pagination><cvgOffset>0</cvgOffset><cvgLimit>10000</cvgLimit>"+
        f"<cvgTotal>{len(rows)}</cvgTotal><cvgReturned>{len(rows)}</cvgReturned>"+
        "</pagination></response></Body></Envelope>").encode()


def _bundle(root: Path, rows_by_list: dict[str, list[str]]) -> Path:
    control=b"<config>"+b"".join(f'<list code="{c}" label="Synthetic {c}"/>'.encode() for c in LIST_CODES)+b"</config>"
    (root/"control.xml").write_bytes(control)
    artifacts=[{"kind":"control","file":"control.xml","sha256":hashlib.sha256(control).hexdigest(),"byte_size":len(control)}]
    for code in LIST_CODES:
        raw=_response(rows_by_list.get(code,[])); name=f"{code}-page.xml"; (root/name).write_bytes(raw)
        parsed,_=_parse_response(raw,list_code=code)
        artifacts.append({"kind":"soap","file":name,"list_code":code,"offset":0,"observation_rows":len(parsed),
            "sha256":hashlib.sha256(raw).hexdigest(),"byte_size":len(raw)})
    path=root/"bundle-manifest.json"
    atomic_json(path,{"bundle_version":"nvwa-approved-food-bundle-v1","source_id":CONFIG["source_id"],
        "retrieved_at_utc":"2026-10-03T00:00:00Z","artifacts":artifacts})
    return path


def _artifact(path: Path) -> SourceArtifact:
    raw=path.read_bytes()
    return SourceArtifact(CONFIG["source_url"],"2026-10-03T00:00:00Z",hashlib.sha256(raw).hexdigest(),len(raw),
        code_version=CONFIG["adapter_version"],config_version=CONFIG["config_version"],coverage=CONFIG["coverage"])

class AdapterTests(unittest.TestCase):
    def test_repeated_observations_and_cross_list_identity_stay_separate(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[4]) as temporary:
            root=Path(temporary)
            source=_bundle(root,{"overig_303":[_row("NL-SYN-1"),_row("NL-SYN-1", "pork"),_row("NL-SYN-2")],
                "overig_304":[_row("NL-SYN-1")]})
            run=root/"run"; manifest=NvwaApprovedFoodAdapter().run(source,run,_artifact(source))
            rows=[json.loads(line) for line in (run/"normalized"/"records.jsonl").read_text().splitlines()]
            self.assertEqual(len(rows),4)
            self.assertEqual(len({row["source_record_key"] for row in rows}),4)
            self.assertEqual(len([row for row in rows if row["normalized"]["establishment_id"]=="NL-SYN-1"]),3)
            self.assertEqual(rows[0]["normalized"]["facility_grouping_key"], "overig_303|NL-SYN-1")
            self.assertEqual(rows[3]["normalized"]["facility_grouping_key"], "overig_304|NL-SYN-1")
            self.assertNotEqual(rows[0]["normalized"]["facility_grouping_key"], rows[3]["normalized"]["facility_grouping_key"])
            self.assertEqual(len({row["normalized"]["trading_name"] for row in rows}),1)
            self.assertEqual(manifest["observation_rows_by_list"]["overig_303"],3)
            self.assertEqual(manifest["unique_recognition_numbers_by_list"]["overig_303"],2)
            self.assertNotIn("unique_recognition_numbers",manifest)

    def test_missing_key_quarantines_and_address_stays_private(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[4]) as temporary:
            root=Path(temporary); source=_bundle(root,{"overig_309":[_row(None)],"overig_310":[_row("NL-SYN-4")]})
            run=root/"run"; manifest=NvwaApprovedFoodAdapter().run(source,run,_artifact(source))
            bad=[json.loads(line) for line in (run/"quarantined"/"records.jsonl").read_text().splitlines()]
            good=json.loads((run/"normalized"/"records.jsonl").read_text().splitlines()[0])["normalized"]
            self.assertEqual(manifest["quarantined_rows"],1)
            self.assertEqual(bad[0]["reasons"],["missing_recognition_number"])
            self.assertEqual(good["private_location_evidence"]["address_lines"],["1 Sample Street"])
            self.assertEqual(good["private_location_evidence"]["country_code"],"NL")
            self.assertEqual(good["source_scope_eligibility"],"eligible")
            self.assertEqual(good["privacy_gate"],"pending")
            self.assertIsNone(good["coordinates"])

    def test_unknown_source_field_is_retained_and_marks_drift(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[4]) as temporary:
            root=Path(temporary)
            item=_row("NL-SYN-5").replace("</CvgErkendbedrijfUser>","<newField>future</newField></CvgErkendbedrijfUser>")
            source=_bundle(root,{"overig_308":[item]}); run=root/"run"
            manifest=NvwaApprovedFoodAdapter().run(source,run,_artifact(source))
            parsed=json.loads((run/"parsed"/"records.jsonl").read_text().splitlines()[0])
            self.assertEqual(manifest["schema_status"],"schema-drift")
            self.assertIn("newField",parsed["source_values"])

    def test_wsdl_request_and_soap_fault_handling(self):
        request=_soap_request("overig_306",offset=120,limit=10000); root=ET.fromstring(request)
        self.assertIn("overig_306","".join(root.itertext()))
        self.assertIn("120","".join(root.itertext()))
        self.assertIn(b"http://nl/minlnv/cvg/Berichtenboek.wsdl/types/",request)
        for collection in ("categorieen", "diersoorten", "activiteiten", "producten"):
            self.assertIn(f"<typ:{collection}/>", request.decode())
            self.assertNotIn(f"<typ:{collection} xsi:nil=", request.decode())
        with self.assertRaises(NvwaContractError):
            _parse_response(b"<Envelope><Body><Fault/></Body></Envelope>",list_code="overig_303")

    def test_repeated_xml_observations_can_exceed_service_pagination_count(self):
        raw = _response([_row("NL-SYN-6"), _row("NL-SYN-6", "pork")])
        raw = raw.replace(b"<cvgTotal>2</cvgTotal><cvgReturned>2</cvgReturned>",
                          b"<cvgTotal>1</cvgTotal><cvgReturned>1</cvgReturned>")
        observations, pagination = _parse_response(raw, list_code="overig_303")
        self.assertEqual(len(observations), 2)
        self.assertEqual(pagination["cvgReturned"], 1)

if __name__ == "__main__":
    unittest.main()
