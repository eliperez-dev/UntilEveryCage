from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from pipeline.contracts.adapter_contract import SourceArtifact
from pipeline.common.orchestrator import run_private_lifecycle
from .acquire_1069 import CATALOG_URL, discover_csv, fetch
from .it_1069_adapter import ADAPTER_VERSION, HEADERS, Italy1069Adapter

ROOT = Path(__file__).resolve().parents[3]


def row(*, recognition: str = "ABP 412TEST3", longitude: str = "12.5", latitude: str = "45.2",
        status: str = "Autorizzata") -> str:
    values = {
        "precedente_bollo_cee": "", "num_identificativo_produzione_commercializzazione": recognition,
        "ragione_sociale": "Synthetic ABP Test Srl", "indirizzo": "Via Synthetic 1", "comune": "Testown",
        "provincia": "TO", "codice_regione": "010", "regione": "Piemonte",
        "classificazione_stabilimento": "3=Category 3", "codice_impianto_attivita": "BIOGP",
        "descrizione_impianto_attivita": "Biogas plant", "prodotti_abilitati": "MIMC=Manure",
        "specifica_prodotti_abilitati": "", "paesi_export_autorizzato": "", "longitudine": longitude,
        "latitudine": latitude, "stato_localizzazione": "1", "cod_fiscale": "SYNTHETIC",
        "p_iva": "00000000000", "codice_comune": "001001", "data_inizio_attivita": "2020-01-01",
        "data_fine_attivita": "", "stato_attivita": status, "data_ultimo_aggiornamento": "2026-09-23",
    }
    return ";".join(values[key] for key in HEADERS)


def csv_bytes(*rows: str) -> bytes:
    return (";".join(HEADERS) + "\n" + "\n".join(rows) + "\n").encode("utf-8")


class Italy1069AdapterTests(unittest.TestCase):
    def test_recognized_record_preserves_source_identity_and_marks_location_unknown(self):
        result = Italy1069Adapter().parse_bytes(csv_bytes(row()))
        self.assertEqual(result["input_rows"], 1)
        self.assertEqual(len(result["accepted"]), 1)
        record = result["accepted"][0]
        normalized = record["normalized"]
        self.assertEqual(record["source_id"], "it.1069-2009")
        self.assertEqual(normalized["regulation"], "EC 1069/2009")
        self.assertEqual(normalized["coordinates"]["precision"], "source-precision-unknown")
        self.assertEqual(normalized["coordinate_provenance_state"], "catalog-notes-some-OSM-contributor-coordinates; row-level-origin-unspecified")
        self.assertIsNone(normalized["address"])
        self.assertNotIn("p_iva", normalized)
        self.assertEqual(normalized["linked_853_recognition_number_state"], "not-supplied-by-current-1069-artifact")
        self.assertEqual(normalized["publication_gate"], "blocked")
        self.assertRegex(result["schema_fingerprint"], r"^[0-9a-f]{64}$")

    def test_invalid_rows_quarantine_and_coordinate_zero_pair_is_not_a_map_point(self):
        result = Italy1069Adapter().parse_bytes(csv_bytes(
            row(recognition="", longitude="12.5", latitude="45.2"),
            row(recognition="ABP 413TEST3", longitude="12.5", latitude="north"),
            row(recognition="ABP 414TEST3", longitude="0", latitude="0"),
            row(recognition="ABP 415TEST3", status="invented"),
        ))
        self.assertEqual(len(result["accepted"]), 2)
        self.assertEqual(len(result["quarantined"]), 2)
        reasons = {reason for item in result["quarantined"] for reason in item["reasons"]}
        self.assertTrue({"missing_1069_recognition_number", "unknown_activity_status"} <= reasons)
        self.assertEqual(result["coordinate_rejections"], {
            "invalid_source_coordinates": 1, "zero_zero_source_coordinates": 1})
        self.assertEqual(result["accepted"][0]["normalized"]["coordinates"], None)
        self.assertEqual(result["accepted"][1]["normalized"]["coordinates"], None)

    def test_schema_drift_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "schema drift"):
            Italy1069Adapter().parse_bytes(csv_bytes(row()).replace(b"codice_impianto_attivita", b"different_header"))

    def test_current_dated_catalog_csv_discovery_is_source_scoped(self):
        html = b'''<a href="/sites/default/files/opendata/STAB_SPOA_9_20260922.csv">old</a>
          <a href="/sites/default/files/opendata/STAB_SPOA_9_20260923.csv">current</a>
          <a href="https://evil.invalid/STAB_SPOA_9_20260924.csv">foreign</a>
          <a href="/sites/default/files/opendata/STAB_POA_8_20260924.csv">853</a>'''
        url, date = discover_csv(html)
        self.assertEqual(url, "https://www.dati.salute.gov.it/sites/default/files/opendata/STAB_SPOA_9_20260923.csv")
        self.assertEqual(date, "2026-09-23")
        with self.assertRaisesRegex(ValueError, "no supported"):
            discover_csv(b'<a href="/sites/default/files/opendata/STAB_POA_8_20260923.csv">wrong source</a>')

    def test_acquisition_archives_only_current_catalog_target_with_hash_and_terms(self):
        catalog = b'<a href="/sites/default/files/opendata/STAB_SPOA_9_20260923.csv">current</a>'
        payload = csv_bytes(row())

        class Response:
            status = 200

            def __init__(self, body: bytes, url: str, content_type: str):
                self.body, self.url = body, url
                self.offset = 0
                self.headers = {"Content-Type": content_type, "Last-Modified": "Wed, 23 Sep 2026 00:00:00 GMT"}

            def read(self, size: int = -1) -> bytes:
                end = len(self.body) if size < 0 else min(len(self.body), self.offset + size)
                chunk = self.body[self.offset:end]
                self.offset = end
                return chunk

            def geturl(self) -> str:
                return self.url

            def __enter__(self):
                return self

            def __exit__(self, *_: object) -> None:
                return None

        def opener(request, timeout):
            url = request.full_url
            if url == CATALOG_URL:
                return Response(catalog, url, "text/html")
            return Response(payload, url, "text/csv")

        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            metadata = fetch(output_root=Path(temp) / "raw", run_id="acquisition-contract-run",
                             terms_review_path=ROOT / "data" / "terms-reviews" / "it.1069-2009.json",
                             opener=opener)
            artifact = Path(metadata["artifact_path"])
            self.assertEqual(metadata["source_id"], "it.1069-2009")
            self.assertEqual(metadata["filename_publication_date"], "2026-09-23")
            self.assertEqual(metadata["byte_size"], len(payload))
            self.assertEqual(metadata["sha256"], hashlib.sha256(payload).hexdigest())
            self.assertEqual(metadata["terms_review"]["decision"], "approved")
            self.assertEqual(artifact.read_bytes(), payload)

    def test_lifecycle_writes_separate_private_candidate_and_quarantine(self):
        content = csv_bytes(row(), row(recognition="ABP 416TEST3", status="unknown"))
        digest = hashlib.sha256(content).hexdigest()
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            root = Path(temp)
            raw = root / "source.csv"
            raw.write_bytes(content)
            adapter = Italy1069Adapter()
            artifact = SourceArtifact(
                "https://www.dati.salute.gov.it/sites/default/files/opendata/STAB_SPOA_9_20260923.csv",
                "2026-09-24T00:00:00Z", digest, len(content), code_version=ADAPTER_VERSION,
                config_version=adapter.schema_version, coverage="Italy 1069/2009 only",
            )
            status = run_private_lifecycle(raw, root / "runs", artifact, adapter)
            run_dir = Path(status["run_dir"])
            manifest = status["manifest"]
            self.assertEqual(status["status"], "candidate-ready")
            self.assertEqual(manifest["input_rows"], manifest["normalized_rows"] + manifest["quarantined_rows"])
            self.assertEqual(manifest["normalized_rows"], 1)
            adapter.write_candidate_handoff(root / "candidate-handoff", artifact, adapter.parse_bytes(content))
            handoff_manifest = json.loads((root / "candidate-handoff" / "manifest.json").read_text())
            self.assertEqual(handoff_manifest["source_id"], "it.1069-2009")
            graph = json.loads((root / "candidate-handoff" / "graph-candidates" / "manifest.json").read_text())
            self.assertEqual(graph["candidate_rows"], 1)
            self.assertEqual(graph["contradictions"], "source-local contradiction/review states preserved; no cross-source merge performed")


if __name__ == "__main__":
    unittest.main()
