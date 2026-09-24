import json
import tempfile
import unittest
from pathlib import Path

from pipeline.common.refresh_runner import RefreshCatalog
from pipeline.sources.us.fsis.adapter import CONFIG
from pipeline.sources.us.fsis.runner_adapter import FsisRefreshAdapter


class FsisRunnerAdapterTests(unittest.TestCase):
    def test_registered_as_a_live_source_scoped_adapter(self):
        catalog = RefreshCatalog()
        registered = catalog.adapters["us.fsis"]
        self.assertTrue(registered.capabilities.live_callable)
        self.assertEqual(registered.adapter.source_id, "us.fsis")

    def test_fixture_path_runs_existing_two_file_reconciliation_without_public_release(self):
        with tempfile.TemporaryDirectory() as directory:
            result = FsisRefreshAdapter().refresh(
                mode="fixture", run_dir=Path(directory), artifact=None, options={})
            handoff_path = Path(directory) / "candidate-handoff" / "manifest.json"
            handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
            self.assertEqual(result["candidate_handoff"], True)
            self.assertEqual(result["acquisition_classification"], "assisted")
            self.assertEqual(handoff["source_id"], "us.fsis")
            self.assertEqual(handoff["code_version"], CONFIG["adapter_version"])
            self.assertEqual(handoff["config_version"], CONFIG["contract_version"])
            self.assertEqual(handoff["publication_state"], "private-candidate")
            self.assertGreater(result["candidate_observation_rows"], 0)


if __name__ == "__main__":
    unittest.main()
