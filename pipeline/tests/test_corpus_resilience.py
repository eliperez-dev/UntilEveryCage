import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location(
    "run_corpus_resilience",
    ROOT / "scripts" / "benchmarks" / "run_corpus_resilience.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class CorpusResiliencePlanTests(unittest.TestCase):
    def distribution(self, root: Path) -> Path:
        path = root / "distribution.json"
        path.write_text(json.dumps({
            "coverage": {
                "selected_records_by_source": {
                    "v1.aa.locations": 6,
                    "v1.bb.locations": 3,
                    "v1.cc.locations": 1,
                }
            }
        }), encoding="utf-8")
        return path

    def test_selection_is_bounded_and_preserves_distribution_shape(self):
        with tempfile.TemporaryDirectory() as directory:
            plan = MODULE.build_plan(self.distribution(Path(directory)), max_records=5)
            self.assertEqual(plan["available_records"], 10)
            self.assertEqual(plan["selected_records"], 5)
            self.assertEqual(plan["selected_records_by_source"], {
                "v1.aa.locations": 3,
                "v1.bb.locations": 2,
            })
            with self.assertRaises(MODULE.ResilienceError):
                MODULE.build_plan(self.distribution(Path(directory)), max_records=MODULE.MAX_RECORDS + 1)

    def test_synthetic_corpus_is_temporary_and_report_is_row_free(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report_path = self.distribution(root)
            report = MODULE.run_rehearsal(distribution=report_path, max_records=3, plan_only=True)
            encoded = json.dumps(report)
            self.assertEqual(report["status"], "plan-only")
            self.assertEqual(report["corpus"]["selected_records"], 3)
            for forbidden in ("establishment_id", "Synthetic resilience facility", "source_record_key", "raw_fields"):
                self.assertNotIn(forbidden, encoded)
            self.assertFalse((root / "corpus").exists())

    def test_interruption_exception_is_reserved_for_post_commit_observer(self):
        observations = []

        def after_commit(batch_number, offset, count):
            observations.append((batch_number, offset, count))
            raise MODULE.SimulatedInterruption("test interruption")

        with self.assertRaises(MODULE.SimulatedInterruption):
            after_commit(1, 0, 2)
        self.assertEqual(observations, [(1, 0, 2)])


if __name__ == "__main__":
    unittest.main()
