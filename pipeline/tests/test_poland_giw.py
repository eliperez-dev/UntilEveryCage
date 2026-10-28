"""Synthetic GIW parsing, acquisition and private source contracts."""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from urllib.parse import parse_qs, urlsplit

from pipeline.contracts.adapter_contract import SourceArtifact
from pipeline.sources.poland.adapter import (ADAPTER_VERSION, SCHEMA_VERSION, SOURCE_ID,
    SOURCE_URL, GiwApprovedFoodAdapter, RegisterPage, address_parts, bundle_digest)
from pipeline.sources.poland.acquire import SourceRedirect, fetch
from pipeline.taxonomy_crosswalk import project_observation, crosswalk_document


def page(section=2, *, count=1, number=1, wni="00123456", name="Synthetic Foods", address="Example Street 12\n00-001 Exampletown", category="SH", species="B", extra=False):
    start = (number-1)*20 + 1
    cells = [str(start), wni, name, address.replace("\n", "<br>"), category, species, "", "", ""]
    header = "<tr>" + "".join("<th>"+v+"</th>" for v in ("No.", "Appr.No.", "Name of establishment", "Address", "kat.", "Animal species", "Associated activities", "Remarks", "Article 44")) + "</tr>"
    row = "<tr>"+"".join(f'<td rowspan="{2 if extra and i not in (4,5) else 1}">{v}</td>' for i,v in enumerate(cells))+"</tr>"
    if extra: row += "<tr><td>CP</td><td>P</td></tr>"
    return (f'<select name="sekcja"><option selected value="{section}">Section {section}</option></select>'
            f'<span>count: {count}</span><table id="spiMainTable">'+header+(row if count else "")+'</table>').encode()


class Response(io.BytesIO):
    status = 200
    headers = {"Content-Type": "text/html; charset=utf-8"}
    def __init__(self, raw, url): super().__init__(raw); self.url=url
    def geturl(self): return self.url


class Opener:
    def __init__(self, fault=None): self.fault=fault; self.calls=0
    def open(self, request, timeout=45):
        self.calls+=1
        args = parse_qs(urlsplit(request.full_url).query)
        if args.get("poprzedniaSekcja") != args.get("sekcja"):
            raise AssertionError("GIW requires the published previous-section parameter to retain pagination")
        section, number = int(args["sekcja"][0]), int(args["pagenbr"][0])
        raw = page(section=section, wni=f"00{section:06d}")
        if self.fault == "section": raw=page(section=99)
        if self.fault == "drift" and self.calls%2==0: raw=page(section=section, name="Changed Synthetic Name")
        return Response(raw, request.full_url)


class PolandGiwTests(unittest.TestCase):
    def test_native_identifier_variants_and_long_names_are_not_lost(self):
        from pipeline.sources.poland.adapter import valid_approval_identifier, display_label
        for value in ("00123456","001234567","1-00123456"):
            self.assertTrue(valid_approval_identifier(value))
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)
                (root/"section-02-page-0001.html").write_bytes(page(wni=value,name="Synthetic Foods "*20))
                parsed=GiwApprovedFoodAdapter().parse(root)
                row=parsed["accepted"][0]
                self.assertEqual(row["normalized"]["establishment_id"],value)
                self.assertGreater(len(row["normalized"]["trading_name"]),200)
                self.assertEqual(len(display_label(row["normalized"]["trading_name"])),200)
        self.assertFalse(valid_approval_identifier("missing"))

    def test_rowspans_preserve_two_activities_and_leading_zero_identity(self):
        p=RegisterPage(page(extra=True))
        self.assertEqual(len(p.data),2)
        self.assertEqual(p.ordinals,{1})
        self.assertEqual({r["wni"] for r in p.data},{"00123456"})
        self.assertEqual({r["category"] for r in p.data},{"SH","CP"})
        self.assertEqual({r["species"] for r in p.data},{"B","P"})

    def test_address_keeps_original_lines_and_explicit_postcode_town(self):
        result=address_parts("Example Street 12\n00-001 Exampletown")
        self.assertEqual(result["postal_code"],"00-001")
        self.assertEqual(result["city"],"Exampletown")
        self.assertEqual(result["address_lines"],["Example Street 12"])
        self.assertIsNone(address_parts("Example Industrial Estate")["city"])
        reversed_address=address_parts("00-001 Exampletown\nul. Example Street 12")
        self.assertEqual(reversed_address["address_lines"],["Example Street 12"])
        self.assertEqual(reversed_address["city"],"Exampletown")
        inline_address=address_parts("00-001 Exampletown, ul. Example Street 12")
        self.assertEqual(inline_address["address_lines"],["Example Street 12"])
        self.assertEqual(inline_address["city"],"Exampletown")
        rural_address=address_parts("00-001 Examplevillage 12")
        self.assertEqual(rural_address["city"],"Examplevillage")
        self.assertEqual(rural_address["address_lines"],["Examplevillage 12"])

    def test_schema_and_invalid_utf8_fail_closed(self):
        for raw in (b'not a register', page().replace(b'Appr.No.',b'Unexpected'), b'\xff'):
            with self.assertRaises(ValueError): RegisterPage(raw)

    def test_eight_column_sections_and_empty_sections_are_explicit(self):
        raw=page(section=3)
        raw=raw.replace(b'<th>Article 44</th>',b'').replace(b'<td rowspan="1"></td></tr>',b'</tr>')
        p=RegisterPage(raw)
        self.assertEqual(p.data[0]["article_44"],"")
        empty=RegisterPage(b'<select name="sekcja"><option selected value="8">Section VII</option></select>count: 0 No entries')
        self.assertEqual(empty.count,0)
        self.assertEqual(empty.data,[])

    def test_ambiguous_source_addresses_are_retained_but_not_geocode_eligible(self):
        from pipeline.sources.poland.adapter import approval_group_facts
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"section-02-page-0001.html").write_bytes(page())
            (root/"section-03-page-0001.html").write_bytes(page(section=3,address="Other Road 23\n00-002 Exampletown"))
            parsed=GiwApprovedFoodAdapter().parse(root)
        summary=approval_group_facts(parsed["accepted"])["00123456"]
        self.assertEqual(summary["source_scope_eligibility"],"ambiguous_source_address")
        self.assertEqual(len(summary["source_approval_details"]),2)

    def test_poland_profile_and_query_never_use_establishment_names(self):
        from pipeline.geocoding.private_profiles import profile_for_source
        from pipeline.geocoding.source_queue import source_geocode_query
        profile=profile_for_source(SOURCE_ID)
        self.assertEqual(profile["country_code"],"PL")
        row={"source_id":SOURCE_ID,"source_values":{"name":"Never send this company"},
             "normalized":{"country_code":"PL","private_location_evidence":address_parts("00-001 Exampletown\nul. Example Street 12")}}
        query=source_geocode_query(row)
        self.assertEqual(query,"Example Street 12, Exampletown, 00-001, Poland")
        self.assertNotIn("Never send",query)

    def test_poland_geocoder_checks_country_bounds_and_address_without_network(self):
        from pipeline.geocoding.geoapify import GeoapifyAdapter
        def outcome(*,country="pl",coords=(20,52),address="Example Street 12",confidence=.99):
            payload={"features":[{"type":"Feature","geometry":{"type":"Point","coordinates":list(coords)},
                "properties":{"country_code":country,"result_type":"building","address_line1":address,
                              "rank":{"confidence":confidence}}}]}
            def opener(request,timeout):
                args=parse_qs(urlsplit(request.full_url).query)
                self.assertEqual(args["filter"],["countrycode:pl"])
                self.assertEqual(args["bias"],["countrycode:none"])
                return io.BytesIO(json.dumps(payload).encode())
            return GeoapifyAdapter(api_key="synthetic",opener=opener,country_code="pl",private_source_profile=True).geocode("Example Street 12, Exampletown, 00-001, Poland")
        self.assertEqual(outcome().status,"accepted")
        for parameters in ({"country":"de"},{"coords":(0,0)},{"address":"Other Street 12"},{"confidence":.5}):
            with self.subTest(parameters=parameters):
                result=outcome(**parameters)
                self.assertNotEqual(result.status,"accepted")
                self.assertIsNone(result.latitude)

    def test_full_section_fetch_rechecks_and_preserves_response_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            facts=fetch(output_root=root,run_id="synthetic",terms_review_path=Path(__file__).parents[1]/"sources/poland/terms-review.json",opener=Opener(),pause_seconds=0)
            self.assertEqual(facts["page_count"],17)
            self.assertEqual(facts["request_count"],34)
            self.assertEqual(facts["approval_observations"],17)
            self.assertEqual(bundle_digest(Path(facts["artifact_path"])),(facts["artifact_sha256"],facts["artifact_byte_size"]))

    def test_source_selected_page_size_is_followed_not_assumed_to_be_twenty(self):
        class VariablePages(Opener):
            def open(self, request, timeout=30):
                args=parse_qs(urlsplit(request.full_url).query)
                section,number=int(args["sekcja"][0]),int(args["pagenbr"][0])
                if section != 3: return super().open(request,timeout)
                if number == 2: self_test.assertEqual(args["onpage"],["25"])
                base=page(section=3,count=26)
                header=base.split(b'<table id="spiMainTable">')[1].split(b'</tr>')[0]+b'</tr>'
                rows=[]
                for ordinal in range((number-1)*25+1,min(number*25,26)+1):
                    vals=[str(ordinal),f"00{ordinal:06d}","Synthetic Foods","00-001 Exampletown<br>Example Street 12","SH","B","","",""]
                    rows.append('<tr>'+''.join('<td>'+v+'</td>' for v in vals)+'</tr>')
                raw=base.split(b'<table id="spiMainTable">')[0]+b'<table id="spiMainTable">'+header+''.join(rows).encode()+b'</table><a href="index.php?pagenbr=2">Last</a>'
                return Response(raw,request.full_url)
        self_test=self
        with tempfile.TemporaryDirectory() as tmp:
            facts=fetch(output_root=Path(tmp),run_id="synthetic",terms_review_path=Path(__file__).parents[1]/"sources/poland/terms-review.json",opener=VariablePages(),pause_seconds=0)
            section=next(s for s in facts["sections"] if s["section"]==3)
            self.assertEqual(section["page_size"],25)
            self.assertEqual(section["unique_veterinary_identifiers"],26)
            self.assertEqual(section["page_count"],2)
            recovered=fetch(output_root=Path(tmp),run_id="synthetic",terms_review_path=Path(__file__).parents[1]/"sources/poland/terms-review.json",opener=VariablePages(),pause_seconds=0)
            self.assertEqual(recovered["recovered_partial_pages"],1)
            self.assertEqual(recovered["artifact_sha256"],facts["artifact_sha256"])

    def test_import_rechecks_page_bytes_and_section_totals(self):
        from pipeline.sources.poland.validation import validate_acquisition
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            facts=fetch(output_root=root/"acquisition",run_id="synthetic",terms_review_path=Path(__file__).parents[1]/"sources/poland/terms-review.json",opener=Opener(),pause_seconds=0)
            manifest={"source_url":SOURCE_URL,"retrieved_at_utc":facts["retrieved_at_utc"],
                      "checksum_sha256":facts["artifact_sha256"],"normalized_sha256":"synthetic","normalized_rows":17}
            summary={"input_rows":17,"normalized_rows":17,"quarantined_rows":0,"candidate_handoff_sha256":"synthetic"}
            validate_acquisition(root,"synthetic",manifest,summary,1)
            metadata=root/"acquisition"/SOURCE_ID/"synthetic/acquisition-metadata.json"
            facts["sections"][0]["establishment_entries"]=2
            metadata.write_text(json.dumps(facts),encoding="utf-8")
            with self.assertRaises(ValueError): validate_acquisition(root,"synthetic",manifest,summary,1)
            facts["sections"][0]["establishment_entries"]=1
            metadata.write_text(json.dumps(facts),encoding="utf-8")
            source_page=Path(facts["artifact_path"])/"section-01-page-0001.html"
            source_page.write_bytes(source_page.read_bytes()+b' ')
            with self.assertRaises(ValueError): validate_acquisition(root,"synthetic",manifest,summary,1)

    def test_wrong_section_and_mid_fetch_changes_fail_closed(self):
        for fault in ("section","drift"):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(ValueError):
                    fetch(output_root=Path(tmp),run_id="synthetic",terms_review_path=Path(__file__).parents[1]/"sources/poland/terms-review.json",opener=Opener(fault),pause_seconds=0)

    def test_numbered_entries_can_share_a_source_approval_identity(self):
        class RepeatedApproval(Opener):
            def open(self, request, timeout=30):
                section=int(parse_qs(urlsplit(request.full_url).query)["sekcja"][0])
                raw=page(section=section,count=2)
                row=raw.split(b'</tr>')[1]+b'</tr>'
                row=row.replace(b'>1</td>',b'>2</td>',1).replace(b'>SH</td>',b'>CP</td>')
                return Response(raw.replace(b'</table>',row+b'</table>'),request.full_url)
        with tempfile.TemporaryDirectory() as tmp:
            facts=fetch(output_root=Path(tmp),run_id="synthetic",terms_review_path=Path(__file__).parents[1]/"sources/poland/terms-review.json",opener=RepeatedApproval(),pause_seconds=0)
            self.assertEqual(facts["source_establishment_section_entries"],34)
            self.assertTrue(all(s["unique_veterinary_identifiers"]==1 for s in facts["sections"]))
            parsed=GiwApprovedFoodAdapter().parse(Path(facts["artifact_path"]))
            self.assertEqual(len(parsed["accepted"]),34)
            self.assertEqual(len({r["normalized"]["establishment_id"] for r in parsed["accepted"]}),1)

    def test_source_numbering_gaps_are_declared_not_invented(self):
        class SourceGap(Opener):
            def open(self, request, timeout=30):
                section=int(parse_qs(urlsplit(request.full_url).query)["sekcja"][0])
                raw=page(section=section,count=2).replace(b'>1</td>',b'>2</td>',1)
                return Response(raw,request.full_url)
        with tempfile.TemporaryDirectory() as tmp:
            facts=fetch(output_root=Path(tmp),run_id="synthetic",terms_review_path=Path(__file__).parents[1]/"sources/poland/terms-review.json",opener=SourceGap(),pause_seconds=0)
            self.assertEqual(facts["approval_observations"],17)
            self.assertEqual(facts["source_establishment_section_entries"],34)
            self.assertTrue(all(s["source_omitted_ordinals"]==[1] for s in facts["sections"]))
            self.assertTrue(all(s["observed_establishment_entries"]==1 for s in facts["sections"]))

    def test_source_identity_groups_sections_without_losing_observations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"section-02-page-0001.html").write_bytes(page(extra=True))
            (root/"section-03-page-0001.html").write_bytes(page(section=3))
            parsed=GiwApprovedFoodAdapter().parse(root)
            self.assertEqual(len(parsed["accepted"]),3)
            self.assertEqual({r["normalized"]["establishment_id"] for r in parsed["accepted"]},{"00123456"})
            self.assertEqual(len({r["source_record_key"] for r in parsed["accepted"]}),3)
            rows=parsed["accepted"]
            self.assertEqual(project_observation(rows[0])["taxonomy_display_category"],"slaughter")
            self.assertEqual(project_observation(rows[1])["taxonomy_display_category"],"processing_and_preparation")
            self.assertTrue(crosswalk_document(SOURCE_ID)["rules"])

    def test_replay_is_deterministic_and_original_address_is_not_stripped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); source=root/"raw"; source.mkdir()
            (source/"section-02-page-0001.html").write_bytes(page())
            digest,size=bundle_digest(source)
            artifact=SourceArtifact(SOURCE_URL,"2026-10-28T00:00:00Z",digest,size,code_version=ADAPTER_VERSION,config_version=SCHEMA_VERSION)
            adapter=GiwApprovedFoodAdapter()
            a=adapter.run(source,root/"a",artifact); b=adapter.run(source,root/"b",artifact)
            self.assertEqual(a["normalized_sha256"],b["normalized_sha256"])
            row=json.loads((root/"a/normalized/records.jsonl").read_text())
            self.assertEqual(row["source_values"]["address"],"Example Street 12\n00-001 Exampletown")
            self.assertIsNone(row["normalized"]["coordinates"])
            self.assertEqual(a["release_state"],"not-created")

    def test_missing_identifier_is_quarantined_not_assigned_an_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/"section-02-page-0001.html").write_bytes(page(wni=""))
            parsed=GiwApprovedFoodAdapter().parse(root)
            self.assertFalse(parsed["accepted"])
            self.assertEqual(parsed["quarantined"][0]["reasons"],["invalid_wni"])

    def test_redirects_never_escape_the_public_giw_host(self):
        from urllib.request import Request
        for url in ("http://zywnosc.wetgiw.gov.pl/spi/zatw/index.php", "https://other.invalid/file"):
            with self.assertRaises(ValueError): SourceRedirect().redirect_request(Request(SOURCE_URL),None,302,"redirect",{},url)


if __name__=="__main__": unittest.main()
