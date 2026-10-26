import hashlib
import unittest
import tempfile
from pathlib import Path
from urllib.parse import parse_qs

from .location_enrichment import (_decode_response, append_private_events, fetch_filtered_export,
                                  fetch_registration_results, match_official_result,
                                  UnsupportedAesanProvinceError,
                                  parse_official_results, query_with_verified_municipality,
                                  same_official_province)


class AesanLocationEnrichmentTests(unittest.TestCase):
    def setUp(self):
        self.record = {
            "source_id": "es.locations", "source_record_key": "synthetic-key",
            "source_values": {"N_RGSEAA": "10.025892/CO", "Provincia": "Córdoba"},
            "normalized": {"establishment_id": "10.025892/CO", "province": "Córdoba",
                           "private_location_evidence": {"address": "AVENIDA INDUSTRIAL Nº7"}},
        }
        self.result = {"registration": "10.25892/CO", "address": "Avenida Industrial, 7",
                       "municipality": "Fuente Palmera", "province": "Córdoba"}

    def event(self, results):
        return match_official_result(self.record, results, retrieved_at="2026-10-25T00:00:00Z",
                                     result_url="https://rgsa-web-aesan.mscbs.es/rgsa/resultado_principal.jsp")

    def test_exact_key_adds_verified_municipality_without_replacing_source_address(self):
        event = self.event([self.result])
        self.assertEqual(event["outcome"], "matched")
        self.assertEqual(event["location_evidence_addition"]["municipality"], "Fuente Palmera")
        query = query_with_verified_municipality(self.record, event)
        self.assertEqual(query, "AVENIDA INDUSTRIAL Nº7, Fuente Palmera, Córdoba")
        self.assertEqual(self.record["normalized"]["private_location_evidence"]["address"], "AVENIDA INDUSTRIAL Nº7")

    def test_ambiguous_exact_key_is_rejected(self):
        self.assertEqual(self.event([self.result, self.result])["outcome"], "ambiguous_exact_registration")

    def test_wrong_province_is_rejected(self):
        wrong = {**self.result, "province": "Sevilla"}
        self.assertEqual(self.event([wrong])["outcome"], "province_conflict")

    def test_not_found_is_explicit(self):
        other = {**self.result, "registration": "12.25892/CO"}
        self.assertEqual(self.event([other])["outcome"], "not_found")

    def test_event_history_appends_without_copying_business_or_address_fields(self):
        event = self.event([self.result])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "events.jsonl")
            self.assertEqual(append_private_events(path, [event]), 1)
            self.assertEqual(append_private_events(path, [event]), 1)
            rows = path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(rows), 2)
            self.assertNotIn("PRIVATE NAME", "\n".join(rows))
            self.assertNotIn("AVENIDA INDUSTRIAL", "\n".join(rows))

    def test_official_result_table_extracts_only_allowlisted_location_fields(self):
        html = """<table><tr><th>Nº RGSEAA Registration number</th><th>Razón Social Enterprise name</th>
        <th>Dom. Indl. PhysicalAdress</th><th>Localidad Town</th><th>Provincia Province</th><th>CCAA Region</th></tr>
        <tr><td>10.025892/CO</td><td>PRIVATE NAME</td><td>Street 7</td><td>Town</td><td>Province</td><td>Region</td></tr></table>"""
        rows = parse_official_results(html)
        self.assertEqual(rows, [{"registration": "10.025892/CO", "address": "Street 7",
                                 "municipality": "Town", "province": "Province"}])

    def test_http_declared_legacy_charset_preserves_accented_province(self):
        class Headers:
            def get_content_charset(self): return "iso-8859-1"
        class Response:
            headers = Headers()
            def read(self, limit=-1): return "Córdoba".encode("iso-8859-1")[:limit]
        self.assertEqual(_decode_response(Response()), "Córdoba")

    def test_official_form_posts_all_empty_text_and_select_controls(self):
        form = """<form method="post" action="/rgsa/procesaBusquedaServlet">
        <input type="hidden" name="tipo_buscador" value="1"><input type="hidden" name="pagina" value="1">
        <input name="razon_social" value=""><input name="numero1"><input name="numero2"><input name="numero3">
        <select name="clave"><option value=""></option></select><select name="categoria"></select>
        <select name="actividad"></select><select name="comunidad"></select><select name="provincia"></select>
        <input name="localidad" value=""><input type="checkbox" name="check_autorizaciones">
        <input type="submit" name="Limpiar" value="Limpiar"><input type="submit" name="Buscar" value="Buscar/Search"></form>"""
        response_html = """<table><tr><th>Nº RGSEAA Registration number</th><th>Dom. Indl. PhysicalAdress</th>
        <th>Localidad Town</th><th>Provincia Province</th></tr><tr><td>10.025892/CO</td>
        <td>Street 7</td><td>Town</td><td>Province</td></tr></table>"""
        class Response:
            def __init__(self, body, url): self.body, self.url = body.encode(), url
            def read(self, limit=-1): return self.body[:limit]
            def geturl(self): return self.url
            def __enter__(self): return self
            def __exit__(self, *args): return False
        class Opener:
            def __init__(self): self.requests=[]
            def open(self, request, timeout):
                self.requests.append(request)
                if request.data is None:
                    return Response(form, "https://rgsa-web-aesan.mscbs.es/rgsa/formulario_principal_js.jsp")
                return Response(response_html, "https://rgsa-web-aesan.mscbs.es/rgsa/resultado_principal.jsp")
        opener=Opener()
        responses=fetch_registration_results(["10.025892/CO"],opener=opener)
        posted=parse_qs(opener.requests[1].data.decode(),keep_blank_values=True)
        for field in ("razon_social","numero1","numero2","numero3","clave","categoria","actividad","comunidad","provincia","localidad"):
            self.assertIn(field,posted)
        self.assertNotIn("check_autorizaciones",posted)
        self.assertNotIn("Limpiar",posted)
        self.assertEqual(posted["Buscar"],["Buscar/Search"])
        self.assertEqual(responses[0]["results"][0]["municipality"],"Town")

    def test_enrichment_splits_full_cohort_into_bounded_batches(self):
        from .location_enrichment import enrich_records
        records = []
        for index in range(25):
            key = f"10.{index + 1:06d}/CO"
            records.append({"source_id": "es.locations", "source_record_key": f"key-{index:02}",
                "source_values": {"N_RGSEAA": key, "Provincia": "Córdoba"},
                "normalized": {"establishment_id": key, "province": "Córdoba", "address": "Avenida 1"}})
        calls = []
        def lookup(keys):
            calls.append(len(keys))
            return [{"results": [], "retrieved_at": "2026-10-25T00:00:00Z",
                     "result_url": "https://rgsa-web-aesan.mscbs.es/rgsa/resultado_principal.jsp"}
                    for _ in keys]
        events = enrich_records(records, limit=25, lookup=lookup)
        self.assertEqual(calls, [24, 1])
        self.assertEqual(len(events), 25)
        self.assertTrue(all(event["outcome"] == "not_found" for event in events))

    def test_filtered_excel_export_uses_official_controls_and_blank_registration(self):
        form = """<form method="post" action="/rgsa/procesaBusquedaServlet">
        <input name="numero1"><input name="numero2"><input name="numero3">
        <select name="clave"><option value="">All</option><option value="10">Carnes</option></select>
        <select name="provincia"><option value="">All</option><option value="M">Madrid</option></select>
        <input type="submit" name="Buscar" value="Buscar"></form>"""
        result = """<form method="post" action="/rgsa/resultado_principal_excel.jsp">
        <input type="hidden" name="pagina" value="1"><input type="submit" name="excel" value="Excel">
        </form>"""
        workbook = """<table><tr><th>Nº RGSEAA</th><th>Razón Social</th>
        <th>Dom. Indl. PhysicalAdress</th><th>Localidad Town</th><th>Provincia Province</th></tr>
        <tr><td>10.025892/CO</td><td>Private name</td><td>Street 7</td><td>Town</td><td>Madrid</td></tr></table>"""

        class Headers(dict):
            def get_content_charset(self): return "iso-8859-1"
        class Response:
            def __init__(self, body, url, content_type="text/html"):
                self.body, self.url, self.headers = body.encode("iso-8859-1"), url, Headers({"Content-Type": content_type})
            def read(self, limit=-1): return self.body[:limit]
            def geturl(self): return self.url
            def __enter__(self): return self
            def __exit__(self, *args): return False
        class Opener:
            def __init__(self): self.requests=[]
            def open(self, request, timeout):
                self.requests.append(request)
                if len(self.requests) == 1:
                    return Response(form, "https://rgsa-web-aesan.mscbs.es/rgsa/formulario_principal_js.jsp")
                if len(self.requests) == 2:
                    return Response(result, "https://rgsa-web-aesan.mscbs.es/rgsa/resultado_principal.jsp")
                return Response(workbook, "https://rgsa-web-aesan.mscbs.es/rgsa/resultado_principal_excel.jsp",
                                "application/vnd.ms-excel")

        opener = Opener()
        export = fetch_filtered_export("Madrid", "10", opener=opener, request_interval_seconds=0)
        posted = parse_qs(opener.requests[1].data.decode(), keep_blank_values=True)
        self.assertEqual(posted["provincia"], ["M"])
        self.assertEqual(posted["clave"], ["10"])
        self.assertEqual([posted[f"numero{i}"] for i in range(1, 4)], [[""], [""], [""]])
        self.assertNotIn("Private name", str(export))
        self.assertEqual(export["results"][0]["municipality"], "Town")
        self.assertEqual(export["response_sha256"], hashlib.sha256(workbook.encode("iso-8859-1")).hexdigest())
        self.assertEqual(export["result_page_sha256"], hashlib.sha256(result.encode("iso-8859-1")).hexdigest())
        self.assertEqual(export["response_kind"], "official_excel_export")
        self.assertEqual(export["query_province_option"], "Madrid")
        self.assertEqual(len(opener.requests), 3)

    def test_unsupported_source_province_is_a_specific_one_request_failure(self):
        form = """<form method="post" action="/rgsa/procesaBusquedaServlet">
        <input name="numero1"><input name="numero2"><input name="numero3">
        <select name="clave"><option value="10">Carnes</option></select>
        <select name="provincia"><option value="M">Madrid</option></select>
        <input type="submit" name="Buscar" value="Buscar"></form>"""
        class Headers(dict):
            def get_content_charset(self): return "utf-8"
        class Response:
            def __init__(self, body, url):
                self.body, self.url, self.headers = body.encode(), url, Headers()
            def read(self, limit=-1): return self.body[:limit]
            def geturl(self): return self.url
            def __enter__(self): return self
            def __exit__(self, *args): return False
        class Opener:
            def __init__(self): self.requests = []
            def open(self, request, timeout):
                self.requests.append(request)
                return Response(form, "https://rgsa-web-aesan.mscbs.es/rgsa/formulario_principal_js.jsp")
        opener = Opener()
        with self.assertRaises(UnsupportedAesanProvinceError) as raised:
            fetch_filtered_export("Bilbao", "10", opener=opener, request_interval_seconds=0)
        self.assertEqual(raised.exception.http_requests, 1)
        self.assertEqual(raised.exception.response_bytes, len(form.encode()))
        self.assertEqual(len(opener.requests), 1)

    def test_explicit_official_zero_result_is_resumable_without_export_button(self):
        form = """<form method="post" action="/rgsa/procesaBusquedaServlet">
        <input name="numero1"><input name="numero2"><input name="numero3">
        <select name="clave"><option value="10">Carnes</option></select>
        <select name="provincia"><option value="M">Madrid</option></select>
        <input type="submit" name="Buscar" value="Buscar"></form>"""
        result = "<p>No se han encontrado resultados para la consulta.</p>"
        class Headers(dict):
            def get_content_charset(self): return "utf-8"
        class Response:
            def __init__(self, body, url):
                self.body, self.url, self.headers = body.encode(), url, Headers({"Content-Type": "text/html"})
            def read(self, limit=-1): return self.body[:limit]
            def geturl(self): return self.url
            def __enter__(self): return self
            def __exit__(self, *args): return False
        class Opener:
            def __init__(self): self.requests = []
            def open(self, request, timeout):
                self.requests.append(request)
                if len(self.requests) == 1:
                    return Response(form, "https://rgsa-web-aesan.mscbs.es/rgsa/formulario_principal_js.jsp")
                return Response(result, "https://rgsa-web-aesan.mscbs.es/rgsa/resultado_principal.jsp")
        opener = Opener()
        export = fetch_filtered_export("Madrid", "10", opener=opener, request_interval_seconds=0)
        self.assertEqual(export["results"], [])
        self.assertTrue(export["explicit_zero_results"])
        self.assertEqual(export["http_requests"], 2)
        self.assertEqual(len(opener.requests), 2)

    def test_changed_result_page_without_export_or_explicit_zero_still_fails_closed(self):
        from .location_enrichment import _explicit_empty_search_result
        self.assertFalse(_explicit_empty_search_result(b"<p>Search information unavailable</p>", "utf-8"))

    def test_only_supported_province_name_equivalents_are_accepted(self):
        self.assertTrue(same_official_province("A Coruña", "La Coruña"))
        self.assertTrue(same_official_province("Coruña, A", "La Coruña"))
        self.assertTrue(same_official_province("Bizkaia", "Vizcaya"))
        self.assertTrue(same_official_province("Alicante", "Alicante/Alacant"))
        self.assertTrue(same_official_province("Castellón", "Castellón/Castelló"))
        self.assertTrue(same_official_province("Valencia", "Valencia/València"))
        self.assertTrue(same_official_province("La Rioja", "Rioja, La"))
        self.assertTrue(same_official_province("Las Palmas", "Palmas, Las"))
        self.assertTrue(same_official_province("Comunidad Foral de Navarra", "Navarra"))
        # Bilbao is a city, not a province alias for all of Bizkaia.
        self.assertFalse(same_official_province("Bilbao", "Bizkaia"))
        self.assertFalse(same_official_province("Sevilla", "Córdoba"))


if __name__ == "__main__":
    unittest.main()
