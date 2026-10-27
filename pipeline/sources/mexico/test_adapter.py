from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
import urllib.parse
import urllib.error
from pathlib import Path

from pipeline.contracts.adapter_contract import SourceArtifact
from pipeline.sources.mexico.acquire import DenueAcquisitionError, fetch
from pipeline.sources.mexico.adapter import API_BASE, ACTIVITY_CODES, DenueAdapter
from pipeline.sources.mexico.adapter import ACTIVITY_CATEGORIES
from pipeline.sources.mexico.refresh import DenueRefreshAdapter


def _record(activity: str, identifier: str = "91") -> dict:
    return {
        "CLEE": "01001731161100091", "Id": identifier,
        "Nombre": "Synthetic establishment", "Razon_social": "Synthetic operator",
        "Clase_actividad": "Synthetic activity", "Estrato": "11 a 30 personas",
        "Tipo_vialidad": "CALLE", "Calle": "Synthetic Road", "Num_Exterior": "10",
        "Num_Interior": "", "Colonia": "Test", "CP": "00000",
        "Ubicacion": "Synthetic municipality, state", "Tipo": "Fijo",
        "Longitud": "-99.1", "Latitud": "19.4", "CLASE_ACTIVIDAD_ID": activity,
        "SECTOR_ACTIVIDAD_ID": "31", "SUBSECTOR_ACTIVIDAD_ID": "311",
        "RAMA_ACTIVIDAD_ID": "3116", "Fecha_Alta": "2022-01",
        "AreaGeo": "010010001", "Telefono": "discard-me", "Correo_e": "discard-me",
    }


class _Response:
    status = 200
    headers = {"Content-Type": "application/json; charset=utf-8"}

    def __init__(self, value, url=None, final_url=None):
        self.body = json.dumps(value).encode("utf-8")
        self.url = final_url or url

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def geturl(self):
        return self.url

    def read(self, size=-1):
        if size < 0:
            size = len(self.body)
        body, self.body = self.body[:size], self.body[size:]
        return body


class _Opener:
    def __init__(self, *, count_total=2, records=None, count_envelope=None,
                 page_envelope=None, empty_markers=None, final_url=None):
        self.requests = []
        self.count_total = count_total
        self.records = records if records is not None else {
            "311611": [_record("311611", "91")],
            "311612": [_record("311612", "92")],
        }
        self.count_envelope = count_envelope
        self.page_envelope = page_envelope
        self.empty_markers = empty_markers or {}
        self.final_url = final_url

    def urlopen(self, request, timeout):
        self.requests.append(request)
        parts = urllib.parse.urlsplit(request.full_url)
        segments = [urllib.parse.unquote(part) for part in parts.path.split("/") if part]
        method = segments[5]
        if method == "Cuantificar":
            activity, state = segments[6], segments[7]
            value = self.count_envelope if self.count_envelope is not None else [
                {"AE": activity, "AG": state, "Total": str(self.count_total)}]
            return _Response(value, request.full_url, self.final_url)
        if method == "BuscarAreaAct":
            if self.page_envelope is not None:
                return _Response(self.page_envelope, request.full_url, self.final_url)
            activity = segments[14]
            if activity in self.empty_markers:
                return _Response(self.empty_markers[activity], request.full_url, self.final_url)
            start, end = int(segments[16]), int(segments[17])
            rows = self.records.get(activity, [])
            return _Response(rows[start - 1:end], request.full_url, self.final_url)
        raise AssertionError("unexpected endpoint")


class MexicoDenueTests(unittest.TestCase):
    def test_bounded_state_activity_acquisition_preserves_token_free_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            opener = _Opener()
            result = fetch(output_root=directory, token="synthetic-token",
                           states=("01",), opener=opener, page_size=1)
            artifact = json.loads(Path(result["artifact_path"]).read_text(encoding="utf-8"))
            self.assertEqual(result["input_rows"], 2)
            self.assertEqual(result["request_count"], 7)
            self.assertEqual([row["CLASE_ACTIVIDAD_ID"] for row in artifact["records"]],
                             ["311611", "311612"])
            self.assertEqual(artifact["activity_codes"], list(ACTIVITY_CODES))
            self.assertNotIn("Telefono", artifact["records"][0])
            self.assertNotIn("Correo_e", artifact["records"][0])
            self.assertNotIn("synthetic-token", Path(result["artifact_path"]).read_text(encoding="utf-8"))
            self.assertTrue(all("synthetic-token" in request.full_url for request in opener.requests))

    def test_preflight_record_limit_stops_before_record_pages(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(DenueAcquisitionError, "record limit"):
                fetch(output_root=directory, token="synthetic-token", states=("01",),
                      max_records=1, opener=_Opener())
            self.assertFalse((Path(directory) / "raw" / "denue-api.json").exists())

    def test_acquisition_rejects_count_mismatch_and_api_error_envelope(self):
        with tempfile.TemporaryDirectory() as directory:
            one_record = {"311611": [_record("311611", "91")]}
            with self.assertRaisesRegex(DenueAcquisitionError, "reconcile"):
                fetch(output_root=directory, token="synthetic-token", states=("01",),
                      opener=_Opener(records=one_record))
            with self.assertRaisesRegex(DenueAcquisitionError, "count response schema"):
                fetch(output_root=directory, token="synthetic-token", states=("01",),
                      opener=_Opener(count_envelope={"error": "invalid token"}))
            with self.assertRaisesRegex(DenueAcquisitionError, "page count or schema"):
                fetch(output_root=directory, token="synthetic-token", states=("01",),
                      opener=_Opener(page_envelope={"error": "invalid query"}))

    def test_detail_pages_normalize_only_exact_official_empty_markers(self):
        records = {code: [] for code in ACTIVITY_CODES}
        records["311611"] = [_record("311611", "91")]
        records["311611"][0]["AreaGeo"] = "040010001"
        with tempfile.TemporaryDirectory() as directory:
            result = fetch(output_root=directory, token="synthetic-token", states=("04",),
                           opener=_Opener(count_total=1, records=records,
                                          empty_markers={"311612": "No hay resultados.",
                                                         "311613": '"No hay resultados. "'}))
            self.assertEqual(result["input_rows"], 1)

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(DenueAcquisitionError, "page count or schema"):
                fetch(output_root=directory, token="synthetic-token", states=("04",),
                      opener=_Opener(count_total=1, records=records,
                                     empty_markers={"311612": "No hay resultados"}))

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(DenueAcquisitionError, "page count or schema"):
                fetch(output_root=directory, token="synthetic-token", states=("04",),
                      opener=_Opener(count_total=1, records=records,
                                     empty_markers={"311612": '"Unrelated response. "'}))

    def test_acquisition_rejects_repeated_wrong_state_and_wrong_class_records(self):
        wrong_state = _record("311611", "91")
        wrong_state["AreaGeo"] = "020010001"
        scenarios = (
            ({"311611": [_record("311611", "91")],
              "311612": [_record("311612", "91")]}, "repeated"),
            ({"311611": [wrong_state],
              "311612": [_record("311612", "92")]}, "state scope"),
            ({"311611": [_record("311612", "91")],
              "311612": [_record("311612", "92")]}, "class scope"),
        )
        for records, error in scenarios:
            with self.subTest(error=error), tempfile.TemporaryDirectory() as directory:
                with self.assertRaisesRegex(DenueAcquisitionError, error):
                    fetch(output_root=directory, token="synthetic-token", states=("01",),
                          opener=_Opener(records=records))
                self.assertFalse((Path(directory) / "raw" / "denue-api.json").exists())

    def test_acquisition_rejects_response_redirecting_official_token_path(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(DenueAcquisitionError, "approved official HTTPS host"):
                fetch(output_root=directory, token="synthetic-token", states=("01",),
                      opener=_Opener(final_url="https://example.invalid/collect"))

    def test_sanitized_source_fields_activity_and_location_are_preserved(self):
        payload = {
            "source_id": "mx.locations", "schema_version": "denue-api-v1",
            "activity_codes": list(ACTIVITY_CODES), "retrieved_at_utc": "2026-01-01T00:00:00Z",
            "records": [_record("311611"), _record("311611"), _record("999999", "93")],
            "preflight_counts": [],
        }
        result = DenueAdapter().parse_bytes(json.dumps(payload).encode("utf-8"))
        self.assertEqual(len(result["accepted"]), 1)
        self.assertEqual(len(result["quarantined"]), 2)
        normalized = result["accepted"][0]["normalized"]
        self.assertEqual(normalized["establishment_id"], "91")
        self.assertEqual(normalized["activity_class_id"], "311611")
        self.assertEqual(normalized["coordinates"], {"latitude": 19.4, "longitude": -99.1})
        self.assertIn("Synthetic Road", normalized["facility_address"])
        self.assertEqual(result["accepted"][0]["source_values"]["CLEE"], "01001731161100091")
        self.assertNotIn("Telefono", result["accepted"][0]["source_values"])
        self.assertNotIn("Correo_e", result["accepted"][0]["source_values"])

        incomplete = _record("311611", "94")
        incomplete.pop("Longitud")
        payload["records"] = [incomplete]
        incomplete_result = DenueAdapter().parse_bytes(json.dumps(payload).encode("utf-8"))
        self.assertIsNone(incomplete_result["accepted"][0]["normalized"]["coordinates"])
        self.assertEqual(incomplete_result["accepted"][0]["normalized"]["coordinate_state"],
                         "incomplete-source-coordinate")

    def test_classification_categories_and_mexico_coordinate_envelope(self):
        records = [_record(code, str(index)) for index, code in enumerate(ACTIVITY_CODES, start=1)]
        foreign = _record("311611", "99")
        foreign["Latitud"], foreign["Longitud"] = "40.7", "-74.0"
        records.append(foreign)
        payload = {"source_id": "mx.locations", "schema_version": "denue-api-v1",
                   "activity_codes": list(ACTIVITY_CODES), "records": records}
        result = DenueAdapter().parse_bytes(json.dumps(payload).encode("utf-8"))
        self.assertEqual([row["normalized"]["activity_categories"] for row in result["accepted"]],
                         [ACTIVITY_CATEGORIES[code] for code in ACTIVITY_CODES])
        rejected = result["quarantined"][0]["record"]
        self.assertEqual(rejected["source_values"]["Latitud"], "40.7")
        self.assertIsNone(rejected["normalized"]["coordinates"])
        self.assertEqual(rejected["normalized"]["coordinate_state"],
                         "outside-mexico-coordinate-envelope")

    def test_refresh_hook_runs_synthetic_artifact_through_lifecycle_and_handoff(self):
        payload = {"source_id": "mx.locations", "schema_version": "denue-api-v1",
                   "activity_codes": list(ACTIVITY_CODES),
                   "retrieved_at_utc": "2026-01-01T00:00:00Z",
                   "preflight_counts": [{"count": 1}], "records": [_record("311611")]}
        raw = (json.dumps(payload) + "\n").encode("utf-8")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "denue.json"
            artifact.write_bytes(raw)
            facts = {"retrieved_at_utc": "2026-01-01T00:00:00Z",
                     "sha256": hashlib.sha256(raw).hexdigest(), "byte_size": len(raw),
                     "preflight_rows": 1, "request_count": 5, "response_bytes": 1234,
                     "activity_counts": {"31161": 1}}
            summary = DenueRefreshAdapter().refresh(
                mode="local-artifact", run_dir=root / "refresh", artifact=artifact,
                options={"acquisition": facts},
            )
            self.assertEqual(summary["input_rows"], 1)
            self.assertEqual(summary["source_artifact_sha256"], facts["sha256"])
            self.assertIn(summary["lifecycle_status"], {"candidate-ready", "staged-restricted"})
            if summary["candidate_handoff"]:
                handoff = root / "refresh" / "candidate-handoff" / "manifest.json"
                self.assertTrue(handoff.exists())
                self.assertEqual(summary["candidate_observation_rows"], 1)

    def test_refresh_hook_requires_terms_review_and_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            hook = DenueRefreshAdapter()
            with self.assertRaisesRegex(ValueError, "terms review"):
                hook.acquire(run_dir=Path(directory), options={})
            artifact = Path(directory) / "denue.json"
            artifact.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "provenance"):
                hook.refresh(mode="local-artifact", run_dir=Path(directory) / "refresh",
                             artifact=artifact, options={})

    def test_lifecycle_verifies_artifact_provenance_and_keeps_release_blocked(self):
        payload = {
            "source_id": "mx.locations", "schema_version": "denue-api-v1",
            "activity_codes": list(ACTIVITY_CODES), "retrieved_at_utc": "2026-01-01T00:00:00Z",
            "records": [_record("311611")], "preflight_counts": [],
        }
        raw = (json.dumps(payload) + "\n").encode("utf-8")
        with tempfile.TemporaryDirectory() as directory:
            raw_path = Path(directory) / "raw.json"
            raw_path.write_bytes(raw)
            artifact = SourceArtifact(API_BASE, "2026-01-01T00:00:00Z",
                                      hashlib.sha256(raw).hexdigest(), len(raw))
            manifest = DenueAdapter().run(raw_path, Path(directory) / "run", artifact)
            self.assertEqual(manifest["input_rows"], manifest["normalized_rows"] + manifest["quarantined_rows"])
            self.assertEqual(manifest["release_state"], "not-created")
            self.assertEqual(manifest["publication_state"], "private-candidate")
            self.assertEqual(manifest["source_url"], API_BASE)

    def test_candidate_handoff_uses_shared_private_contract(self):
        payload = {
            "source_id": "mx.locations", "schema_version": "denue-api-v1",
            "activity_codes": list(ACTIVITY_CODES), "retrieved_at_utc": "2026-01-01T00:00:00Z",
            "records": [_record("311611")], "preflight_counts": [],
        }
        raw = (json.dumps(payload) + "\n").encode("utf-8")
        with tempfile.TemporaryDirectory() as directory:
            artifact = SourceArtifact(API_BASE, "2026-01-01T00:00:00Z",
                                      hashlib.sha256(raw).hexdigest(), len(raw))
            parsed = DenueAdapter().parse_bytes(raw)
            manifest = DenueAdapter().write_candidate_handoff(Path(directory) / "handoff", artifact, parsed)
            self.assertEqual(manifest["contract_version"], "candidate-handoff-v1")
            self.assertEqual(manifest["profile"], "mx-denue-scian-31161")
            self.assertEqual(manifest["normalized_rows"], 1)
            self.assertEqual(manifest["release_state"], "not-created")
            self.assertTrue((Path(directory) / "handoff/graph-candidates/manifest.json").exists())

    def test_error_does_not_echo_tokenized_request_url(self):
        class FailingOpener:
            def urlopen(self, request, timeout):
                raise urllib.error.URLError(request.full_url)

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(DenueAcquisitionError) as raised:
                fetch(output_root=directory, token="secret-token", states=("01",), opener=FailingOpener())
            self.assertNotIn("secret-token", str(raised.exception))
            self.assertNotIn("secret-token", repr(raised.exception.__cause__))


if __name__ == "__main__":
    unittest.main()
