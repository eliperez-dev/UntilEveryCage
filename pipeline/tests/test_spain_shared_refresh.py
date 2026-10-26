"""Regression coverage for Spain's fresh shared-refresh acquisition identity."""

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
SOURCE_ID = "es.locations"


class SpainSharedRefreshTests(unittest.TestCase):
    def test_fresh_import_uses_runner_id_and_validates_original_acquisition(self):
        runner_run_id = "canonical-refresh-plan-20261025"
        retrieved_at = "2026-10-25T12:00:00Z"
        artifact_bytes = b"synthetic AESAN workbook bytes"
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
            artifact_path = acquisition_dir / "rgseaa.xlsx"
            acquisition_path = acquisition_dir / "acquisition-metadata.json"
            acquisition_dir.mkdir(parents=True)
            artifact_path.write_bytes(artifact_bytes)
            acquisition_path.write_text(json.dumps({
                "source_id": SOURCE_ID,
                "run_id": runner_run_id,
                "artifact": "rgseaa.xlsx",
                "artifact_path": str(artifact_path),
                "sha256": artifact_sha256,
                "byte_size": len(artifact_bytes),
                "requested_url": "https://example.invalid/aesan.xlsx",
                "final_url": "https://example.invalid/aesan.xlsx",
                "retrieved_at_utc": retrieved_at,
                "adapter_version": "es-aesan-rgseaa-v2",
                "config_version": "es-aesan-rgseaa-v1",
                "terms_review": {"decision": "approved"},
            }), encoding="utf-8")
            runner_manifest_path = output_root / runner_run_id / "manifest.json"
            runner_manifest_path.parent.mkdir(parents=True, exist_ok=True)
            runner_manifest_path.write_text(json.dumps({
                "run_id": runner_run_id,
                "completed_at_utc": retrieved_at,
                "results": [{"source_id": SOURCE_ID, "status": "succeeded",
                             "acquisition_classification": "live"}],
            }), encoding="utf-8")

            calls: list[list[str]] = []

            def fake_run(command, **kwargs):
                calls.append(list(command))
                if "pipeline.refresh_private" in command:
                    return subprocess.CompletedProcess(command, 0, json.dumps({
                        "exit_status": "ok",
                        "run_id": runner_run_id,
                        "completed_at_utc": retrieved_at,
                        "results": [{"source_id": SOURCE_ID, "status": "succeeded",
                                     "acquisition_classification": "live"}],
                    }), "")

                # Model the importer accepting the same acquisition sidecar
                # produced by the refresh run, rather than one keyed by the
                # preview function's separately generated local UUID.
                self.assertIn("import-real-preview.py", command[1])
                self.assertEqual(command[command.index("--run-id") + 1], runner_run_id)
                self.assertEqual(command[command.index("--run-manifest") + 1],
                                 str(runner_manifest_path))
                metadata = json.loads(acquisition_path.read_text(encoding="utf-8"))
                self.assertEqual(metadata["source_id"], SOURCE_ID)
                self.assertEqual(metadata["run_id"], command[command.index("--run-id") + 1])
                self.assertEqual(metadata["artifact_path"], str(artifact_path))
                self.assertEqual(hashlib.sha256(artifact_path.read_bytes()).hexdigest(),
                                 metadata["sha256"])
                self.assertEqual(metadata["sha256"], artifact_sha256)
                return subprocess.CompletedProcess(command, 0, json.dumps({
                    "status": "imported", "map_visible_count": 0,
                    "observation_count": 1, "facility_candidate_count": 1,
                    "public_release_count": 0, "public_projection_count": 0,
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


if __name__ == "__main__":
    unittest.main()
