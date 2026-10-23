import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from pipeline.scripts.export_private_graph_handoffs import _write_source


class PrivateGraphExportTests(unittest.TestCase):
    def test_same_artifact_italian_business_id_and_legal_name_keep_provenance(self):
        source_id = "it.853-2004"
        artifact_sha = "a" * 64
        normalized = {
            "establishment_id": "REC-1", "country_code": "IT",
            "name": "Synthetic Ragione Sociale", "trading_name": "Synthetic Ragione Sociale",
            "location_role": "recognized-establishment-location",
        }
        source_values = {
            "num_identificativo_produzione_commercializzazione": "REC-1",
            "ragione_sociale": "Synthetic Ragione Sociale", "p_iva": "IT00000000001",
            "cod_fiscale": "PERSONAL-FISCAL-CODE-MUST-NOT-BECOME-ID",
        }
        row = (
            source_id, "REC-1|ACT-1|1", {"normalized": normalized}, source_values,
            artifact_sha, datetime(2026, 10, 1, tzinfo=timezone.utc),
            datetime(2026, 10, 2, tzinfo=timezone.utc),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = _write_source([row], root, scope="approved-release-membership",
                                   source_urls={source_id: "https://source.example/"})
            graph_root = root / source_id / artifact_sha / "graph-candidates"
            manifest = json.loads((graph_root / "manifest.json").read_text(encoding="utf-8"))
            candidate = json.loads((graph_root / "graph-candidates.jsonl").read_text(encoding="utf-8"))
        self.assertEqual(result["total_candidates"], 1)
        self.assertEqual(manifest["checksum_sha256"], artifact_sha)
        self.assertEqual(manifest["source_artifact_sha256"], artifact_sha)
        self.assertEqual(manifest["retrieved_at_utc"], "2026-10-01T00:00:00+00:00")
        self.assertEqual(manifest["country_code"], "IT")
        self.assertEqual(candidate["organizations"][0]["source_identifier"], {
            "identifier_type": "italian_vat", "id_namespace": "it.tax-authority.vat",
            "value": "IT00000000001", "identity_scope": "source_scoped",
        })
        self.assertEqual(candidate["name_assertions"], [{
            "value": "Synthetic Ragione Sociale", "source_field": "ragione_sociale", "role": "legal",
        }])
        self.assertEqual(candidate["relationships"][0]["relationship_type"], "operator")
        self.assertEqual(candidate["relationships"][0]["observed_at"], "2026-10-02T00:00:00+00:00")
        self.assertEqual(candidate["normalized_values"], normalized)
        self.assertNotIn("PERSONAL-FISCAL-CODE-MUST-NOT-BECOME-ID", json.dumps(candidate["organizations"]))


if __name__ == "__main__":
    unittest.main()
