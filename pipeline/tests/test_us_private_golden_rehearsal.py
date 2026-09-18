"""Regression checks for the aggregate-only US private golden rehearsal."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pipeline.scripts.maintenance.rehearse_us_private_golden import FORBIDDEN_KEYS, run


ROOT = Path(__file__).resolve().parents[2]


def _keys(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from _keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _keys(child)


class UsPrivateGoldenRehearsalTests(unittest.TestCase):
    def test_complete_rehearsal_is_private_row_free_and_honest(self):
        with tempfile.TemporaryDirectory() as directory:
            report = run(repository_root=ROOT, output=Path(directory) / "report.json")

        self.assertEqual(report["mechanical_contract_state"], "passed")
        self.assertEqual(report["outcome"]["release_state"], "not-created")
        self.assertFalse(report["outcome"]["public_exposure"])
        self.assertFalse(report["outcome"]["legacy_substitution"])
        self.assertEqual({item["source_id"] for item in report["source_profiles"]}, {"us.fsis", "us.aphis"})
        self.assertEqual(len(report["source_profiles"]), 4)
        self.assertEqual(report["current_evidence_boundary"]["fsis"]["direct_csv_status"], "blocked")
        self.assertEqual(report["current_evidence_boundary"]["aphis"]["failed_capture_count"], 3)
        self.assertEqual(report["validation_quarantine_probe"]["quarantine_count"], 2)
        self.assertFalse(report["validation_quarantine_probe"]["candidate_included_in_release"])
        self.assertEqual(report["geospatial_readiness"]["candidate_count"], 5)
        self.assertEqual(report["geospatial_readiness"]["coordinate_review_count"], 5)
        self.assertEqual(report["accountability_graph"]["cross_source_identity_joins_attempted"], 0)
        self.assertFalse(report["accountability_graph"]["auto_merge"])
        self.assertEqual(report["private_api_frontend"]["preview_probe"], "passed")
        self.assertEqual(report["suppression"]["suppressed_count"], 1)
        fsis_rerun = report["rerun_idempotency"]["fsis"]
        self.assertTrue(all(fsis_rerun[key] for key in ("same_artifact_sha256", "same_normalized_sha256", "same_counts", "same_handoff_sha256")))
        self.assertTrue(report["rerun_idempotency"]["aphis_private_import"]["same_handoff_sha256"])
        self.assertEqual(report["operator_review_packet"]["review_packets_present"], 4)
        self.assertNotIn("Example Meat Plant", json.dumps(report))
        self.assertFalse(FORBIDDEN_KEYS.intersection(set(_keys(report))))

    def test_rehearsal_report_is_deterministic(self):
        with tempfile.TemporaryDirectory() as directory:
            first = run(repository_root=ROOT, output=Path(directory) / "first.json")
            second = run(repository_root=ROOT, output=Path(directory) / "second.json")
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
