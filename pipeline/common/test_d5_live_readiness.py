from __future__ import annotations

import json
import unittest
from pathlib import Path

from pipeline.common.d2_e2e_readiness import D2_SOURCE_IDS
from pipeline.common.d3_live_operations import D3_EXPECTED_SOURCE_IDS
from pipeline.common.d5_live_readiness import EXPECTED_SOURCE_IDS, REPORT_SCHEMA_VERSION, SOURCE_PROFILES, build_readiness_report


ROOT = Path(__file__).parents[2] / "pipeline"


class D5LiveReadinessTests(unittest.TestCase):
    def test_scope_is_exactly_the_thirteen_d2_d3_sources(self):
        self.assertEqual(tuple(EXPECTED_SOURCE_IDS), tuple(D2_SOURCE_IDS) + tuple(D3_EXPECTED_SOURCE_IDS))
        self.assertEqual(len(EXPECTED_SOURCE_IDS), 13)
        self.assertEqual(set(EXPECTED_SOURCE_IDS), set(SOURCE_PROFILES))

    def test_report_is_row_free_and_fail_closed(self):
        report = build_readiness_report(
            registry_path=ROOT / "source_registry.json",
            schedules_path=ROOT / "source_operations.json",
            as_of_utc="2026-09-21T00:00:00Z",
        )
        self.assertEqual(report["schema_version"], REPORT_SCHEMA_VERSION)
        self.assertEqual(report["scope"]["source_count"], 13)
        self.assertEqual(report["scope"]["execution"], "static-audit-no-network")
        self.assertEqual(sum(report["classification_counts"].values()), 13)
        self.assertEqual(report["classification_counts"].get("unattended_live-ready", 0), 0)
        self.assertEqual(report["classification_counts"].get("authenticated_live-ready", 0), 0)
        self.assertFalse(report["operational_controls"]["persistent_scheduler"])
        self.assertFalse(report["operational_controls"]["automatic_publication"])
        for source in report["sources"]:
            self.assertEqual(source["checks"]["network_requests_in_audit"], 0)
            self.assertFalse(source["checks"]["shared_runner_live_mode"])
            self.assertEqual(source["publication"], "blocked")
            self.assertNotIn("rows", source)
            self.assertNotIn("records", source)

    def test_report_serialization_is_deterministic_and_contains_only_aggregate_data(self):
        report = build_readiness_report(
            registry_path=ROOT / "source_registry.json",
            schedules_path=ROOT / "source_operations.json",
            as_of_utc="2026-09-21T00:00:00Z",
        )
        serialized = json.dumps(report, ensure_ascii=False, sort_keys=True)
        loaded = json.loads(serialized)
        self.assertEqual(loaded, report)
        self.assertNotIn("C:\\", serialized)
        self.assertNotIn("/Users/", serialized)

    def test_every_source_has_control_checks_and_operator_boundary(self):
        report = build_readiness_report(
            registry_path=ROOT / "source_registry.json",
            schedules_path=ROOT / "source_operations.json",
        )
        controls = ("timeout", "retry", "provenance", "checksum", "freshness", "no_change", "previous_valid_state")
        for source in report["sources"]:
            for control in controls:
                self.assertTrue(source["checks"][control], source["source_id"])
            self.assertIn(source["operational_classification"], {"terms-blocked", "browser-assisted", "preserved-artifact-only", "technically-broken", "unattended_live-ready", "authenticated_live-ready"})
            self.assertTrue(source["operator_command"])
            self.assertTrue(source["authorization_boundary"])


if __name__ == "__main__":
    unittest.main()
