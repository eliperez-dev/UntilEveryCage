import json
import hashlib
import tempfile
import unittest
from pathlib import Path

from .adapter_registry import load
from .orchestrator import register_input, run_registered_input, run_registered_typed_input
from pipeline.sources.uk.fss_approved.adapter import FssApprovedEstablishmentsAdapter
from pipeline.sources.italy.it_853_adapter import Italy853Adapter


class SharedPipelineTests(unittest.TestCase):
    def test_registered_typed_adapter_compatibility(self):
        header = "precedente_bollo_cee;num_identificativo_produzione_commercializzazione;ragione_sociale;indirizzo;comune;provincia;codice_regione;regione;classificazione_stabilimento;codice_impianto_attivita;descrizione_impianto_attivita;prodotti_abilitati;specifica_prodotti;paesi_export_autorizzato;longitudine;latitudine;stato_localizzazione;cod_fiscale;p_iva;codice_comune;data_inizio_attivita;data_fine_attivita;stato_attivita;data_ultimo_aggiornamento;num_identificativo_produzione_commercializzazione_2"
        row = ";A;Name;;Town;;010;Piemonte;X;10;Activity;P;S;IT;12;45;1;tax;vat;001001;;;Autorizzata;2026-09-13;\n"
        raw = (header + "\n" + row).encode()
        with tempfile.TemporaryDirectory() as directory:
            raw_path = Path(directory) / "italy.csv"
            raw_path.write_bytes(raw)
            config = {"source_url": "https://example.test/italy", "retrieved_at_utc": "2026-09-14T00:00:00Z",
                      "checksum_sha256": hashlib.sha256(raw).hexdigest(), "byte_size": len(raw),
                      "code_version": "test", "config_version": "test"}
            status = run_registered_typed_input(raw_path, Path(directory) / "runs", config, Italy853Adapter())
            self.assertEqual(status["status"], "candidate-ready")
            self.assertEqual(status["manifest"]["source_id"], "it.853-2004")

    def test_registry_and_suppression_are_shared(self):
        root = Path(__file__).parents[1]
        registry = load(root / "adapter-capabilities.json")
        self.assertIn("fss_approved_establishments", {entry["source_id"] for entry in registry["adapters"]})
        adapter = FssApprovedEstablishmentsAdapter()
        with tempfile.TemporaryDirectory() as directory:
            staging = Path(directory) / "staging"
            raw = (root / "sources/uk/fss_approved/fixtures/valid.csv").read_bytes()
            artifact, metadata = register_input(raw, staging, {"source_id": adapter.source_id})
            self.assertEqual(artifact.read_bytes(), raw)
            status = run_registered_input(artifact, Path(directory) / "runs", metadata, adapter.run,
                                          suppressed_ids={(adapter.source_id, "Scotland", "001234")})
            self.assertEqual(status["status"], "candidate-ready")
            self.assertEqual(status["suppressed_count"], 1)
            candidate = (Path(status["run_dir"]) / "release-candidate/records.jsonl").read_text()
            self.assertNotIn("001234", candidate)
            self.assertIn("078901", candidate)
            self.assertEqual((status["manifest"]["release_state"]), "not-created")
            self.assertEqual((status["prior_eligible_release"]), None)

    def test_equal_bytes_keep_distinct_acquisition_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            first, first_meta = register_input(b"synthetic", directory, {"retrieved_at": "first"})
            second, second_meta = register_input(b"synthetic", directory, {"retrieved_at": "second"})
            self.assertEqual(first, second)
            self.assertNotEqual(first_meta["acquisition_manifest"], second_meta["acquisition_manifest"])
            self.assertEqual(json.loads(Path(first_meta["acquisition_manifest"]).read_text())["retrieved_at"], "first")
            self.assertEqual(json.loads(Path(second_meta["acquisition_manifest"]).read_text())["retrieved_at"], "second")

    def test_restricted_and_failed_reruns_do_not_reuse_candidate_path(self):
        adapter = FssApprovedEstablishmentsAdapter()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw, metadata = register_input((Path(__file__).parents[1] / "sources/uk/fss_approved/fixtures/valid.csv").read_bytes(), root / "staging", {"source_id": adapter.source_id})
            ready = run_registered_input(raw, root / "runs", metadata, adapter.run)
            old_candidate = Path(ready["run_dir"]) / "release-candidate/records.jsonl"
            self.assertTrue(old_candidate.exists())
            restricted = run_registered_input(raw, root / "runs", {**metadata, "terms_status": "pending_confirmation"}, adapter.run)
            self.assertNotEqual(ready["run_dir"], restricted["run_dir"])
            self.assertFalse((Path(restricted["run_dir"]) / "release-candidate/records.jsonl").exists())
            def fail(*_args):
                raise ValueError("synthetic failure")
            failed = run_registered_input(raw, root / "runs", metadata, fail)
            self.assertNotEqual(ready["run_dir"], failed["run_dir"])
            self.assertFalse((Path(failed["run_dir"]) / "release-candidate/records.jsonl").exists())
            self.assertTrue(old_candidate.exists())


if __name__ == "__main__":
    unittest.main()
