import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from pipeline.common.orchestrator import run_private_lifecycle
from pipeline.contracts.adapter_contract import SourceArtifact
from .adapter import FranceDgalSectionIAdapter, FranceDgalSectionIIAdapter

FIXTURES = Path(__file__).parent / "fixtures"


class FranceAdapterTests(unittest.TestCase):
    def test_bilingual_composite_headers_from_live_dgal_file_are_supported(self):
        content = ('"Numero de département","Numéro agrément/Approval number","SIRET",'
                   '"Raison SOCIALE - Enseigne commerciale/Name","Adresse/Adress",'
                   '"Code postal/Postal code","Commune/Town","Catégorie/Category",'
                   '"Activités associées/Associated activities","Espèce/Specy"\n'
                   '01,"01.000.001",,"Synthetic Facility","Industrial Road 1",01000,'
                   'Synthetic Town,SH,ABATTOIR,BOVINE\n').encode()
        result = FranceDgalSectionIAdapter().parse_bytes(content)
        self.assertEqual(len(result["accepted"]), 1)
        self.assertEqual(result["accepted"][0]["normalized"]["activity_categories"], ("slaughter",))
        self.assertEqual(result["accepted"][0]["normalized"]["address_state"], "source-value-present-pending-review")

    def test_shared_siret_across_approval_or_category_is_review_signal_not_quarantine(self):
        content = ("approval_number;legal_name;siret;commune;category;associated activities\n"
                   "FR-1;Shared One;12345678901234;Town;SH;Abattage\n"
                   "FR-2;Shared Two;12345678901234;Town;CP;Découpe\n").encode()
        result = FranceDgalSectionIAdapter().parse_bytes(content)
        self.assertEqual(len(result["accepted"]), 2)
        self.assertEqual(len(result["quarantined"]), 0)
        self.assertEqual(result["identity_conflicted_siret_groups"], 1)
        self.assertEqual(result["identity_conflicted_rows"], 2)
        self.assertTrue(all(row["normalized"]["identity_conflict_state"].startswith("shared-siret") for row in result["accepted"]))

    def test_section_i_preserves_source_and_quarantines_duplicate(self):
        adapter = FranceDgalSectionIAdapter(); result = adapter.parse_file(FIXTURES / "section_i.csv")
        self.assertEqual(len(result["accepted"]), 2); self.assertEqual(len(result["quarantined"]), 1)
        row = result["accepted"][0]
        self.assertEqual(row["normalized"]["source_section"], "I"); self.assertEqual(row["normalized"]["activity_categories"], ("slaughter",))
        self.assertEqual(row["source_values"]["SIRET"], "12345678901234"); self.assertIsNone(row["normalized"]["address"]); self.assertIsNone(row["normalized"]["coordinates"])
        self.assertEqual(result["quarantined"][0]["reasons"], ("duplicate_source_row",))

    def test_section_ii_missing_identity_is_quarantined(self):
        result = FranceDgalSectionIIAdapter().parse_file(FIXTURES / "section_ii.csv")
        self.assertEqual(len(result["accepted"]), 1); self.assertIn("missing_approval_number", result["quarantined"][0]["reasons"])

    def test_category_codes_are_tokenized_and_source_rows_have_distinct_graph_keys(self):
        content = ("approval_number;legal_name;commune;category;associated activities\n"
                   "FR-1;Fresh Foods;Town;FRESH;\n"
                   "FR-2;Cut Foods;Town;CP;Découpe\n").encode()
        result = FranceDgalSectionIAdapter().parse_bytes(content)
        self.assertEqual(len(result["accepted"]), 1)
        self.assertIn("unknown_category_code", result["quarantined"][0]["reasons"])
        self.assertIn("source_record_key", result["accepted"][0])

    def test_schema_drift_and_lifecycle_are_closed(self):
        adapter = FranceDgalSectionIAdapter(); raw = (FIXTURES / "section_i.csv").read_bytes(); artifact = SourceArtifact(adapter.source_url, "2026-09-15T00:00:00Z", hashlib.sha256(raw).hexdigest(), len(raw), code_version=adapter.adapter_version, config_version=adapter.schema_version)
        with self.assertRaises(ValueError): adapter.parse_bytes(raw.replace("N° d'agrément".encode(), b"wrong"))
        with tempfile.TemporaryDirectory() as d:
            status = run_private_lifecycle(FIXTURES / "section_i.csv", Path(d) / "runs", artifact, adapter); root = Path(status["run_dir"])
            self.assertEqual(status["status"], "candidate-ready"); self.assertTrue((root / "operator-review-packet.json").exists()); self.assertFalse((root / "released").exists())
            self.assertFalse(json.loads((root / "operator-review-packet.json").read_text())["row_payloads_included"])


if __name__ == "__main__": unittest.main()
