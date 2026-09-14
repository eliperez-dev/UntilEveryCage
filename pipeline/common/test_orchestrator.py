import json
import tempfile
import unittest
from pathlib import Path

from .adapter_registry import load
from .orchestrator import register_input, run_registered_input
from pipeline.sources.uk.fss_approved.adapter import FssApprovedEstablishmentsAdapter


class SharedPipelineTests(unittest.TestCase):
    def test_registry_and_suppression_are_shared(self):
        root = Path(__file__).parents[1]
        registry = load(root / "adapter-capabilities.json")
        self.assertEqual(registry["adapters"][0]["source_id"], "fss_approved_establishments")
        adapter = FssApprovedEstablishmentsAdapter()
        with tempfile.TemporaryDirectory() as directory:
            staging = Path(directory) / "staging"
            raw = (root / "sources/uk/fss_approved/fixtures/valid.csv").read_bytes()
            artifact, metadata = register_input(raw, staging, {"source_id": adapter.source_id})
            self.assertEqual(artifact.read_bytes(), raw)
            status = run_registered_input(artifact, Path(directory) / "runs", metadata, adapter.run,
                                          suppressed_ids={adapter.source_id})
            self.assertEqual(status["status"], "candidate-ready")
            self.assertEqual(status["suppressed_count"], 2)
            self.assertEqual((status["manifest"]["release_state"]), "not-created")
            self.assertEqual((status["prior_eligible_release"]), None)


if __name__ == "__main__":
    unittest.main()
