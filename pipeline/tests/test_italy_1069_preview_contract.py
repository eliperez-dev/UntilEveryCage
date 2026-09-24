"""Contract checks for Italy's private, source-scoped preview integration."""
from __future__ import annotations

import json
import importlib.util
import tempfile
import unittest
from pathlib import Path

from pipeline.sources.first_wave import FirstWaveRefreshAdapter, descriptor_for
from pipeline.sources.italy.it_1069_adapter import HEADERS

ROOT = Path(__file__).resolve().parents[2]
IMPORTER_PATH = ROOT / "pipeline" / "scripts" / "maintenance" / "import-real-preview.py"
SPEC = importlib.util.spec_from_file_location("import_real_preview_1069_contract", IMPORTER_PATH)
import_real_preview = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(import_real_preview)


def sample_csv() -> bytes:
    values = {
        "precedente_bollo_cee": "", "num_identificativo_produzione_commercializzazione": "ABP 42TEST3",
        "ragione_sociale": "Synthetic ABP Test Srl", "indirizzo": "Via Synthetic 1", "comune": "Testown",
        "provincia": "TO", "codice_regione": "010", "regione": "Piemonte",
        "classificazione_stabilimento": "3=Category 3", "codice_impianto_attivita": "BIOGP",
        "descrizione_impianto_attivita": "Biogas plant", "prodotti_abilitati": "MIMC=Manure",
        "specifica_prodotti_abilitati": "", "paesi_export_autorizzato": "", "longitudine": "12.5", "latitudine": "45.2",
        "stato_localizzazione": "1", "cod_fiscale": "SYNTHETIC", "p_iva": "00000000000", "codice_comune": "001001",
        "data_inizio_attivita": "2020-01-01", "data_fine_attivita": "", "stato_attivita": "Autorizzata",
        "data_ultimo_aggiornamento": "2026-09-23",
    }
    return (";".join(HEADERS) + "\n" + ";".join(values[key] for key in HEADERS) + "\n").encode()


class Italy1069PreviewContractTests(unittest.TestCase):
    def test_policy_and_current_terms_gate_are_source_specific(self):
        policy = json.loads((ROOT / "pipeline" / "preview-enabled-sources.json").read_text(encoding="utf-8"))
        config = policy["sources"]["it.1069-2009"]
        terms = json.loads((ROOT / config["terms_review"]).read_text(encoding="utf-8"))
        self.assertTrue(config["enabled"])
        self.assertEqual(config["terms_decision"], "approved")
        self.assertEqual(terms["decision"], "approved")
        self.assertIn("OpenStreetMap", config["display_policy"]["disclosure"])
        self.assertEqual(config["display_policy"]["precision"], "source-precision-unknown")
        self.assertNotIn("it.1069-2009", import_real_preview.LEGACY_ALLOWED)
        self.assertNotIn("it.853-2004", import_real_preview.LEGACY_ALLOWED)

    def test_current_pipeline_writes_source_scoped_preview_handoff(self):
        descriptor = descriptor_for("it.1069-2009")
        adapter = FirstWaveRefreshAdapter(descriptor)
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            root = Path(temporary)
            raw = root / "synthetic.csv"
            raw.write_bytes(sample_csv())
            summary = adapter.refresh(mode="local-artifact", run_dir=root / "source-run", artifact=raw, options={})
            self.assertTrue(summary["candidate_handoff"])
            self.assertEqual(summary["input_rows"], summary["normalized_rows"] + summary["quarantined_rows"])
            self.assertEqual(summary["candidate_observation_rows"], summary["normalized_rows"])
            manifest = json.loads((root / "source-run" / "candidate-handoff" / "manifest.json").read_text())
            rows_path = root / "source-run" / "candidate-handoff" / "normalized" / "records.jsonl"
            self.assertEqual(manifest["source_id"], "it.1069-2009")
            self.assertEqual(manifest["normalized_rows"], summary["candidate_observation_rows"])
            self.assertFalse((root / "source-run" / "candidate-handoff" / "graph-candidates").exists())
            records = [json.loads(line) for line in rows_path.read_text(encoding="utf-8").splitlines()]
            parsed = [import_real_preview.parse_row("it.1069-2009", record) for record in records]
            self.assertEqual(parsed[0][1], "numeric_source_coordinate")
            self.assertEqual(parsed[0][7], "source-precision-unknown")
            self.assertEqual(parsed[0][-1], "ABP 42TEST3")
            self.assertTrue(summary["schema_fingerprint"])


if __name__ == "__main__":
    unittest.main()
