from __future__ import annotations

import shutil
import unittest
from pathlib import Path

from .first_wave import FIRST_WAVE, descriptor_for, readiness_report, run_fixture


class FirstWaveDescriptorTests(unittest.TestCase):
    def test_expected_sources_are_registered(self):
        self.assertEqual(
            {item.source_id for item in FIRST_WAVE},
            {"dk.smiley", "be.locations", "ca.ontario.meat-plants", "ca.cfia.federal-meat", "fr.dgal.section-i", "fr.dgal.section-ii", "it.853-2004", "au.npi.facilities"},
        )

    def test_descriptors_are_fixture_and_local_artifact_ready(self):
        for item in FIRST_WAVE:
            self.assertTrue(item.fixture_paths)
            self.assertTrue(all(path.is_file() for path in item.fixture_paths), item.source_id)
            self.assertTrue(item.readiness()["fixture_ready"])
            self.assertTrue(item.readiness()["local_artifact_ready"])
            self.assertTrue(item.readiness()["review_required"])
            self.assertEqual(item.readiness()["publication"], "human_gate_required")

    def test_fixture_runs_emit_private_aggregate_and_candidate_handoff(self):
        # The hosted Windows runner may deny ACL changes under temporary
        # directories. Use a fixed disposable workspace directory instead.
        directory = Path(__file__).resolve().parents[4] / ".d2-adapter-test"
        directory.mkdir(exist_ok=True)
        try:
            try:
                for item in FIRST_WAVE:
                    result = run_fixture(item.source_id, Path(directory) / item.source_id.replace(".", "_"))
                    self.assertEqual(result["status"], "candidate-ready", item.source_id)
                    self.assertEqual(result["publication_state"], "human-gate-required", item.source_id)
                    self.assertFalse(result["release_promoted"], item.source_id)
                    self.assertTrue(result["candidate_handoff"], item.source_id)
                    self.assertTrue(result["health_written"], item.source_id)
                    self.assertIsInstance(result["input_rows"], int)
                    self.assertNotIn("source_values", result)
            except PermissionError as error:
                self.skipTest(f"Windows temporary-file ACL blocks atomic private-run test: {error}")
        finally:
            shutil.rmtree(directory, ignore_errors=True)

    def test_descriptor_lookup_fails_closed(self):
        with self.assertRaises(KeyError):
            descriptor_for("uk.fsa.approved-establishments")

    def test_readiness_report_keeps_live_state_separate(self):
        report = readiness_report()
        self.assertEqual(len(report), 8)
        self.assertTrue(all(item["private_pipeline"] == "fixture_contract_ready" for item in report))
        self.assertTrue(all(item["publication"] == "human_gate_required" for item in report))
        self.assertIn("assisted_only", {item["live_acquisition"] for item in report})


if __name__ == "__main__":
    unittest.main()
