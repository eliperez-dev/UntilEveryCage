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
