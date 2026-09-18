import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from .refresh import refresh


ROOT = Path(__file__).parent


class FsisRefreshTests(unittest.TestCase):
    def test_bundle_refresh_writes_private_handoff_and_provenance_per_file(self):
        with tempfile.TemporaryDirectory() as directory:
            result = refresh(
                run_dir=Path(directory) / "run",
                directory_path=ROOT / "fixtures/valid.csv",
                demographics_path=ROOT / "fixtures/demographics.csv",
                retrieved_at_utc="2026-09-18T00:00:00Z",
                effective_date="2026-09-14",
                mode="handoff",
            )
            manifest = result["manifest"]
            self.assertTrue(result["candidate_created"])
            self.assertEqual(manifest["release_state"], "not-created")
            self.assertEqual(manifest["publication_state"], "private-candidate")
            self.assertEqual(manifest["source_artifacts"]["demographics"]["byte_size"], len((ROOT / "fixtures/demographics.csv").read_bytes()))
            self.assertEqual(manifest["row_reconciliation"]["matched_demographic_rows"], 2)
            handoff_path = Path(directory) / "run/lifecycle/handoff/manifest.json"
            self.assertTrue(handoff_path.exists())
            handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
            self.assertEqual(handoff["handoff_artifact_role"], "directory")
            self.assertEqual(handoff["source_artifacts"]["demographics"]["sha256"], manifest["source_artifacts"]["demographics"]["sha256"])
            self.assertEqual(handoff["bundle_artifact"]["sha256"], manifest["sha256"])

    def test_schema_drift_blocks_handoff_after_previous_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = refresh(run_dir=root / "first", directory_path=ROOT / "fixtures/valid.csv", mode="dry-run")
            previous = root / "first/lifecycle/manifest.json"
            changed = root / "changed.csv"
            original = (ROOT / "fixtures/valid.csv").read_text(encoding="utf-8").splitlines()
            changed.write_text("\n".join([original[0] + ",new_column"] + [line + ",new" for line in original[1:]]) + "\n", encoding="utf-8")
            # A changed but parseable header is detected against the prior
            # manifest and blocks handoff.
            with self.assertRaises(ValueError):
                refresh(run_dir=root / "second", directory_path=changed, previous_manifest=previous, mode="handoff")
            self.assertFalse((root / "second/lifecycle/handoff/manifest.json").exists())


if __name__ == "__main__":
    unittest.main()
