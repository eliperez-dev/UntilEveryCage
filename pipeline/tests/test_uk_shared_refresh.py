"""Regression coverage for UK shared-refresh acquisition identity binding."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts import real_preview


ROOT = Path(__file__).parents[2]
SOURCE_ID = "fsa_approved_establishments"


class UkSharedRefreshTests(unittest.TestCase):
    def test_fresh_import_uses_runner_id_and_validates_original_acquisition(self):
        runner_run_id = "refresh-uk-source-20261026"
        retrieved_at = "2026-10-26T12:00:00Z"
        artifact_bytes = b"synthetic private FSA artifact bytes"
        artifact_sha256 = hashlib.sha256(artifact_bytes).hexdigest()

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "pipeline").mkdir()
            (root / "pipeline" / "preview-enabled-sources.json").write_bytes(
                (ROOT / "pipeline" / "preview-enabled-sources.json").read_bytes())
            output_root = root / "runs"
            output_root.mkdir()
            acquisition_dir = (output_root / runner_run_id / "sources" / SOURCE_ID
                               / "acquisition" / SOURCE_ID / runner_run_id)
            artifact_path = acquisition_dir / "source.csv"
            acquisition_path = acquisition_dir / "acquisition-metadata.json"
            acquisition_dir.mkdir(parents=True)
            artifact_path.write_bytes(artifact_bytes)
            acquisition_path.write_text(json.dumps({
                "source_id": SOURCE_ID,
                "run_id": runner_run_id,
                "artifact": "source.csv",
                "artifact_path": str(artifact_path),
                "sha256": artifact_sha256,
                "byte_size": len(artifact_bytes),
                "requested_url": "https://example.invalid/fsa.csv",
                "final_url": "https://example.invalid/fsa.csv",
                "retrieved_at_utc": retrieved_at,
                "adapter_version": "fsa-uk-v2-3",
                "config_version": "fsa-uk-approved-v1",
                "terms_review": {"decision": "approved"},
            }), encoding="utf-8")
            runner_manifest_path = output_root / runner_run_id / "manifest.json"
            runner_manifest_path.parent.mkdir(parents=True, exist_ok=True)
            runner_manifest_path.write_text(json.dumps({
                "run_id": runner_run_id,
                "completed_at_utc": retrieved_at,
                "results": [{
                    "source_id": SOURCE_ID,
                    "status": "succeeded",
                    "acquisition_classification": "live",
                    "summary": {
                        "candidate_handoff_sha256": "a" * 64,
                        "schema_fingerprint": "b" * 64,
                        "quarantine_reasons": {},
                        "input_rows": 1,
                        "candidate_observation_rows": 1,
                        "quarantined_rows": 0,
                    },
                }],
            }), encoding="utf-8")

            calls: list[list[str]] = []

            def fake_run(command, **kwargs):
                calls.append(list(command))
                if "pipeline.refresh_private" in command:
                    return subprocess.CompletedProcess(command, 0, json.dumps({
                        "exit_status": "ok",
                        "run_id": runner_run_id,
                        "completed_at_utc": retrieved_at,
                        "results": [{
                            "source_id": SOURCE_ID,
                            "status": "succeeded",
                            "acquisition_classification": "live",
                            "summary": {
                                "candidate_handoff_sha256": "a" * 64,
                                "schema_fingerprint": "b" * 64,
                                "quarantine_reasons": {},
                                "input_rows": 1,
                                "candidate_observation_rows": 1,
                                "quarantined_rows": 0,
                            },
                        }],
                    }), "")

                self.assertIn("import-real-preview.py", command[1])
                self.assertEqual(command[command.index("--run-id") + 1], runner_run_id)
                self.assertEqual(command[command.index("--run-manifest") + 1],
                                 str(runner_manifest_path))
                metadata = json.loads(acquisition_path.read_text(encoding="utf-8"))
                self.assertEqual(metadata["source_id"], SOURCE_ID)
                self.assertEqual(metadata["run_id"], command[command.index("--run-id") + 1])
                self.assertEqual(metadata["artifact_path"], str(artifact_path))
                self.assertEqual(hashlib.sha256(artifact_path.read_bytes()).hexdigest(), metadata["sha256"])
                self.assertEqual(metadata["sha256"], artifact_sha256)
                return subprocess.CompletedProcess(command, 0, json.dumps({
                    "status": "imported",
                    "map_visible_count": 0,
                    "observation_count": 1,
                    "facility_candidate_count": 1,
                    "numeric_coordinate_count": 0,
                    "city_postal_count": 0,
                    "unmapped_facility_count": 1,
                    "public_release_count": 3,
                    "public_projection_count": 2,
                    "baseline_public_state_preserved": True,
                    "prior_public_release_count": 3,
                    "prior_public_projection_count": 2,
                    "normalized_sha256": "c" * 64,
                }), "")

            with patch.object(real_preview, "ROOT", root), \
                 patch.dict(real_preview.os.environ,
                            {"UEC_REAL_PREVIEW_RUNS_ROOT": str(output_root)}, clear=False), \
                 patch.object(real_preview, "_local_database_url", return_value="postgresql://localhost/test"), \
                 patch.object(real_preview.subprocess, "run", side_effect=fake_run):
                result = real_preview._refresh_source_locked(SOURCE_ID)

            self.assertEqual(result["status"], "imported")
            self.assertEqual(result["run_id"], runner_run_id)
            self.assertEqual(len(calls), 2)
            self.assertIn("--run-id", calls[1])
            self.assertEqual(calls[1][calls[1].index("--run-id") + 1], runner_run_id)
            ledger = json.loads(Path(result["ledger"]).read_text(encoding="utf-8"))
            self.assertEqual(ledger["public_rows"], 0)
            self.assertTrue(ledger["baseline_public_state_preserved"])
            self.assertEqual(ledger["prior_public_release_count"], 3)
            self.assertEqual(ledger["prior_public_projection_count"], 2)
            self.assertEqual(ledger["prior_public_rows"], 5)


if __name__ == "__main__":
    unittest.main()
