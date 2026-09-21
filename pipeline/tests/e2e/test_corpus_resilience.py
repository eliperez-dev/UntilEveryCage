import os
import unittest
from pathlib import Path

from pipeline.scripts.benchmarks import run_corpus_resilience


class CorpusResilienceE2ETests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.environ.get("UEC_RUN_E2E") != "1" or os.environ.get("UEC_RUN_CORPUS_RESILIENCE") != "1":
            raise unittest.SkipTest(
                "set UEC_RUN_E2E=1 and UEC_RUN_CORPUS_RESILIENCE=1 to run the Docker-backed corpus rehearsal"
            )
        cls.report = run_corpus_resilience.run_rehearsal(
            root=Path(__file__).parents[3],
            max_records=int(os.environ.get("UEC_RESILIENCE_RECORDS", "50000")),
        )

    def test_interruption_resumes_and_duplicate_import_is_idempotent(self):
        self.assertEqual(self.report["status"], "pass")
        self.assertTrue(self.report["import"]["interruption_triggered"])
        self.assertEqual(self.report["import"]["expected_rows"], self.report["database"]["row_counts"]["source_records"])
        self.assertEqual(self.report["duplicate_import"]["new_rows"], 0)
        self.assertTrue(self.report["duplicate_import"]["counts_unchanged"])

    def test_backup_restore_replays_current_suppression_before_service(self):
        backup = self.report["backup_restore"]
        self.assertTrue(backup["stale_pre_service_gate_rejected"])
        self.assertEqual(backup["restored_suppressed_rows_before_replay"], 0)
        self.assertEqual(backup["suppressed_rows_after_replay"], 1)
        self.assertGreater(backup["custom_dump_bytes"], 0)

    def test_report_contains_runtime_size_and_bounded_memory_observations(self):
        self.assertEqual(self.report["migrations"]["applied"], 34)
        self.assertGreaterEqual(self.report["runtime_seconds"], 0)
        self.assertGreater(self.report["database"]["final_size_bytes"], 0)
        self.assertGreater(self.report["memory_observation"]["load_import_peak_bytes"], 0)


if __name__ == "__main__":
    unittest.main()
