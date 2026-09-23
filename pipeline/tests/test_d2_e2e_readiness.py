"""Fast, row-free contract tests for D2's disposable E2E runner."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from pipeline.common.d2_e2e_readiness import (
    D2ReadinessError,
    D2_SOURCE_IDS,
    FIXTURE_VERSION,
    REPORT_SCHEMA_VERSION,
    build_report,
    canonical_bytes,
    write_report,
)


class D2E2EReadinessTests(unittest.TestCase):
    def test_one_source_covers_all_display_and_private_gate_states(self):
        report = build_report(selected_sources=["dk.smiley"])
        source = report["sources"][0]
        self.assertEqual(source["status"], "passed")
        self.assertEqual(source["input_rows"], 5)
        self.assertEqual(source["candidate_rows"], 3)
        self.assertEqual(source["quarantine_rows"], 1)
        self.assertEqual(source["restricted_rows"], 1)
        self.assertEqual(source["display_states"], {"exact": 1, "city": 1, "unmapped": 1, "restricted": 1, "quarantine": 1})
        self.assertTrue(source["review_required"])
        self.assertFalse(source["promoted"])
        self.assertEqual(source["public_surfaces"], {"api": False, "map": False, "csv": False})

    def test_selected_many_and_all_eligible_are_deterministic_and_sequential(self):
        selected = ["it.853-2004", "be.locations", "dk.smiley"]
        report = build_report(selected_sources=selected)
        self.assertEqual(report["scope"]["selected_sources"], selected)
        self.assertEqual(report["scope"]["execution"], "sequential")
        self.assertEqual(report["aggregate"]["selected_sources"], 3)
        all_report = build_report()
        self.assertEqual(all_report["scope"]["eligible_sources"], list(D2_SOURCE_IDS))
        self.assertEqual(all_report["scope"]["selected_sources"], list(D2_SOURCE_IDS))
        self.assertEqual(all_report["aggregate"]["passed_sources"], 9)
        self.assertEqual(all_report["aggregate"]["candidate_rows"], 27)

    def test_failure_is_isolated_and_aggregate_is_nonzero(self):
        report = build_report(fail_source="ca.ontario.meat-plants")
        self.assertEqual(report["aggregate"]["failed_sources"], 1)
        self.assertEqual(report["aggregate"]["passed_sources"], 8)
        self.assertEqual(report["aggregate"]["exit_code"], 1)
        failed = next(item for item in report["sources"] if item["source_id"] == "ca.ontario.meat-plants")
        self.assertEqual(failed["failure_category"], "injected_fixture_failure")
        self.assertEqual(report["readiness"]["state"], "blocked")

    def test_resume_skips_successes_and_reruns_failures(self):
        first = build_report(fail_source="fr.dgal.section-i")
        resumed = build_report(resume_report=first)
        statuses = {item["source_id"]: item["status"] for item in resumed["sources"]}
        self.assertEqual(statuses["fr.dgal.section-i"], "passed")
        self.assertEqual(sum(status == "resumed" for status in statuses.values()), 8)
        self.assertEqual(resumed["aggregate"]["failed_sources"], 0)
        self.assertEqual(resumed["aggregate"]["exit_code"], 0)

    def test_idempotent_rerun_and_row_free_report(self):
        first = build_report()
        second = build_report()
        self.assertEqual(canonical_bytes(first), canonical_bytes(second))
        forbidden = {"source_values", "raw_fields", "address", "street", "latitude", "longitude", "coordinates", "private_path", "private_root"}

        def keys(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    yield key
                    yield from keys(child)
            elif isinstance(value, list):
                for child in value:
                    yield from keys(child)

        self.assertTrue(forbidden.isdisjoint(set(keys(first))))
        self.assertEqual(first["database"]["public_api_rows"], 0)
        # Use a deterministic worktree-local path; the managed Windows runner
        # can deny access to TemporaryDirectory-created ACLs.
        path = Path(__file__).with_name(".d2-readiness-test.json")
        try:
            write_report(path, first)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), first)
        finally:
            path.unlink(missing_ok=True)

    def test_disposable_database_sink_is_aggregate_only_and_repeated(self):
        inserted: set[str] = set()

        def sink(source_id, cases):
            self.assertEqual(len(cases), 5)
            if source_id in inserted:
                return 0
            inserted.add(source_id)
            return 3

        first = build_report(selected_sources=["it.853-2004"], database_sink=sink)
        second = build_report(selected_sources=["it.853-2004"], database_sink=sink)
        self.assertEqual(first["database"]["mode"], "disposable-postgis")
        self.assertEqual(first["aggregate"]["database_candidate_rows"], 3)
        self.assertEqual(second["aggregate"]["database_candidate_rows"], 0)
        self.assertEqual(first["aggregate"]["public_api_rows"], 0)
        self.assertFalse(first["sources"][0]["promoted"])

    def test_selection_and_resume_contract_fail_closed(self):
        with self.assertRaises(D2ReadinessError):
            build_report(selected_sources=["unknown"])
        with self.assertRaises(D2ReadinessError):
            build_report(selected_sources=["dk.smiley", "dk.smiley"])
        report = build_report(selected_sources=["dk.smiley"])
        report["fixture_version"] = "wrong"
        with self.assertRaises(D2ReadinessError):
            build_report(selected_sources=["dk.smiley"], resume_report=report)

    def test_report_has_explicit_private_readiness_contract(self):
        report = build_report()
        self.assertEqual(report["schema_version"], REPORT_SCHEMA_VERSION)
        self.assertEqual(report["fixture_version"], FIXTURE_VERSION)
        self.assertEqual(report["source_run"]["live_acquisition"], "not-run")
        self.assertTrue(report["readiness"]["private_candidate"])
        self.assertFalse(report["readiness"]["public_release_allowed"])
        self.assertEqual(report["readiness"]["owner_review"], "awaiting-owner-review")


if __name__ == "__main__":
    unittest.main()
