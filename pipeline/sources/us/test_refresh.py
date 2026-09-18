import json
import tempfile
import unittest
from pathlib import Path

from .refresh import diagnose, run_us_refresh


ROOT = Path(__file__).parent


class UsOperatorRefreshTests(unittest.TestCase):
    def _plan(self, *, directory: Path, demographics: Path, aphis: Path, previous_manifest: Path | None = None) -> dict:
        fsis = {
            "source": "fsis",
            "directory": str(directory),
            "demographics": str(demographics),
            "retrieved_at_utc": "2026-09-18T00:00:00Z",
            "effective_date": "2026-09-14",
        }
        if previous_manifest is not None:
            fsis["previous_manifest"] = str(previous_manifest)
        return {
            "schema_version": "us-operator-plan-v1",
            "retry": {"max_attempts": 2, "retry_delay_seconds": 0, "max_retry_delay_seconds": 0},
            "sources": [
                fsis,
                {
                    "source": "aphis",
                    "profile": "annual_reports",
                    "raw": str(aphis),
                    "retrieved_at_utc": "2026-09-15T00:00:00Z",
                    "query_context": {"selected_year": "2025", "amended_reports_included": True},
                },
            ],
        }

    def test_one_command_report_is_row_free_and_keeps_public_gate_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = run_us_refresh(
                self._plan(
                    directory=ROOT / "fsis/fixtures/valid.csv",
                    demographics=ROOT / "fsis/fixtures/demographics.csv",
                    aphis=ROOT / "aphis/fixtures/annual_reports.csv",
                ),
                plan_base=root,
                run_root=root / "run",
                as_of_utc="2026-09-18T12:00:00Z",
            )
            self.assertEqual(report["overall_state"], "private-review-ready")
            self.assertFalse(report["release"]["release_promoted"])
            self.assertFalse(report["release"]["public_exposure"])
            self.assertEqual(report["source_count"], 2)
            self.assertEqual(report["sources"][0]["counts"]["input_rows"], 2)
            self.assertEqual(report["sources"][0]["row_reconciliation"]["matched_demographic_rows"], 2)
            self.assertEqual(report["sources"][1]["private_import"]["publication_eligible_rows"], 0)
            serialized = json.dumps(report, sort_keys=True)
            self.assertNotIn("Synthetic", serialized)
            self.assertNotIn("Account Name", serialized)

            diagnostics = diagnose(root / "run", as_of_utc="2026-09-18T12:00:00Z")
            self.assertEqual(diagnostics["release"]["publication_gate"], "blocked")
            self.assertTrue(all(item["run_status_present"] for item in diagnostics["checks"]))

    def test_failed_lane_reports_action_and_preserves_previous_valid_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = run_us_refresh(
                self._plan(
                    directory=ROOT / "fsis/fixtures/valid.csv",
                    demographics=ROOT / "fsis/fixtures/demographics.csv",
                    aphis=ROOT / "aphis/fixtures/annual_reports.csv",
                ),
                plan_base=root,
                run_root=root / "first",
            )
            previous = root / "first/fsis/lifecycle/manifest.json"
            malformed = root / "malformed.csv"
            malformed.write_text("not,a,valid,fsis\n", encoding="utf-8")
            plan = self._plan(
                directory=malformed,
                demographics=ROOT / "fsis/fixtures/demographics.csv",
                aphis=ROOT / "aphis/fixtures/annual_reports.csv",
                previous_manifest=previous,
            )
            report = run_us_refresh(plan, plan_base=root, run_root=root / "second")
            fsis = report["sources"][0]
            self.assertEqual(report["overall_state"], "attention-required")
            self.assertEqual(fsis["status"], "failed")
            self.assertTrue(fsis["release_preserved"])
            self.assertTrue(fsis["previous_valid"]["available"])
            self.assertEqual(fsis["failure"]["failure_class"], "validation-or-runtime")
            self.assertTrue((root / "second/fsis/failure-report.json").exists())


if __name__ == "__main__":
    unittest.main()
