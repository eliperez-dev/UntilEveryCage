import json
import shutil
import tempfile
import unittest
from pathlib import Path

from pipeline.common.refresh_runner import RefreshCatalog, RefreshRunner
from pipeline.contracts.refresh import RefreshRequest
from pipeline.sources.australia.test_npi import FIXTURE


class NpiRunnerTests(unittest.TestCase):
    def test_source_is_registered_and_fixture_runs_through_shared_runner(self):
        catalog = RefreshCatalog()
        self.assertIn("au.npi.facilities", catalog.adapters)
        directory = Path(tempfile.mkdtemp(prefix="uec-e2-npi-runner-fixture-"))
        try:
            result = RefreshRunner(catalog).run(RefreshRequest(
                source_ids=("au.npi.facilities",),
                mode="fixture",
                output_root=Path(directory),
            ))
            self.assertEqual(result["exit_status"], "ok")
            item = result["results"][0]
            self.assertEqual(item["source_id"], "au.npi.facilities")
            self.assertEqual(item["acquisition_classification"], "assisted")
            self.assertEqual(item["summary"]["normalized_rows"], 3)
            self.assertFalse(item["publication"]["published"])
            manifest_path = Path(directory) / result["run_id"] / "sources" / "au.npi.facilities" / "manifest.json"
            self.assertTrue(manifest_path.exists())
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["source_id"], "au.npi.facilities")
        finally:
            shutil.rmtree(directory, ignore_errors=True)

    def test_live_mode_is_blocked_before_any_network(self):
        catalog = RefreshCatalog()
        directory = Path(tempfile.mkdtemp(prefix="uec-e2-npi-runner-live-"))
        try:
            result = RefreshRunner(catalog).run(RefreshRequest(
                source_ids=("au.npi.facilities",),
                mode="live-acquisition",
                output_root=Path(directory),
            ))
            item = result["results"][0]
            self.assertEqual(item["acquisition_classification"], "assisted")
            self.assertIn("operator-assisted", item["operational"]["failure_reason"])
        finally:
            shutil.rmtree(directory, ignore_errors=True)

    def test_local_artifact_mode_preserves_private_candidate_boundary(self):
        directory = Path(tempfile.mkdtemp(prefix="uec-e2-npi-local-artifact-"))
        try:
            result = RefreshRunner(RefreshCatalog()).run(RefreshRequest(
                source_ids=("au.npi.facilities",),
                mode="local-artifact",
                artifact_paths={"au.npi.facilities": str(FIXTURE)},
                output_root=directory,
            ))
            self.assertEqual(result["exit_status"], "ok")
            item = result["results"][0]
            self.assertEqual(item["status"], "succeeded")
            self.assertEqual(item["summary"]["normalized_rows"], 3)
            self.assertFalse(item["publication"]["published"])
            self.assertFalse(item.get("public_exposure", False))
        finally:
            shutil.rmtree(directory, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
