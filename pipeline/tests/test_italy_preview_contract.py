"""Fixture-only reconciliation for Italy's generic source-to-preview handoff."""

import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from pipeline.sources.first_wave import FirstWaveRefreshAdapter, descriptor_for

ROOT = Path(__file__).resolve().parents[2]
IMPORTER_PATH = ROOT / "pipeline" / "scripts" / "maintenance" / "import-real-preview.py"
SPEC = importlib.util.spec_from_file_location("import_real_preview_italy_contract", IMPORTER_PATH)
IMPORTER = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(IMPORTER)


class ItalyPreviewContractTests(unittest.TestCase):
    def test_enabled_policy_lifecycle_handoff_and_map_counts_reconcile(self):
        policy = json.loads((ROOT / "pipeline" / "preview-enabled-sources.json").read_text(encoding="utf-8"))
        italy = policy["sources"]["it.853-2004"]
        terms = json.loads((ROOT / italy["terms_review"]).read_text(encoding="utf-8"))
        self.assertTrue(italy["enabled"])
        self.assertEqual(italy["terms_decision"], "approved")
        self.assertEqual(terms["decision"], "approved")
        self.assertEqual(italy["display_policy"]["precision"], "source-precision-unknown")
        self.assertNotIn("it.853-2004", IMPORTER.LEGACY_ALLOWED)

        descriptor = descriptor_for("it.853-2004")
        adapter = FirstWaveRefreshAdapter(descriptor)
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            run_root = Path(temporary)
            result = adapter.refresh(mode="local-artifact", run_dir=run_root,
                                     artifact=descriptor.fixture_paths[0], options={})
            self.assertTrue(result["candidate_handoff"])
            handoff = run_root / "candidate-handoff"
            handoff_manifest = json.loads((handoff / "manifest.json").read_text(encoding="utf-8"))
            records_path = handoff / "normalized" / "records.jsonl"
            raw = records_path.read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), handoff_manifest["normalized_sha256"])
            records = [json.loads(line) for line in raw.decode("utf-8").splitlines()]
            self.assertEqual(result["candidate_observation_rows"], len(records))
            self.assertEqual(result["candidate_handoff_sha256"], handoff_manifest["normalized_sha256"])
            self.assertEqual(result["input_rows"], result["normalized_rows"] + result["quarantined_rows"])
            self.assertEqual(len(records), result["normalized_rows"])

            parsed = [IMPORTER.parse_row("it.853-2004", record) for record in records]
            map_visible = sum(row[1] == "numeric_source_coordinate" for row in parsed)
            source_unknown = sum(row[7] == "source-precision-unknown" for row in parsed if row[1] == "numeric_source_coordinate")
            self.assertEqual(map_visible, source_unknown)
            self.assertRegex(result["schema_fingerprint"], r"^[a-f0-9]{64}$")


if __name__ == "__main__":
    unittest.main()
