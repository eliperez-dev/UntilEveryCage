"""D3 mixed-plan and fail-closed live-access contract tests."""
from __future__ import annotations

import shutil
import unittest
from pathlib import Path

from pipeline.common.d3_live_operations import (
    D3_FACILITY_SOURCE_IDS,
    D3_EVIDENCE_SOURCE_IDS,
    D3_EXPECTED_SOURCE_IDS,
    D3_REHEARSAL_SOURCE_IDS,
    build_mixed_rehearsal,
)


class D3LiveOperationsTests(unittest.TestCase):
    root = Path(__file__).with_name(".d3-live-operations-tests")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root, ignore_errors=True)

    def test_mixed_fixture_plan_is_deterministic_and_includes_expected_d3_sources(self):
        first = build_mixed_rehearsal(run_root=self.root / "fixture", mode="fixture")
        second = build_mixed_rehearsal(run_root=self.root / "fixture-second", mode="fixture")
        self.assertEqual(first["selected_sources"], list(D3_REHEARSAL_SOURCE_IDS))
        self.assertEqual(first["d3"]["mixed_scope"]["expected_d3_sources"], list(D3_EXPECTED_SOURCE_IDS))
        self.assertEqual(first["d3"]["mixed_scope"]["facility_sources"], list(D3_FACILITY_SOURCE_IDS))
        self.assertEqual(first["d3"]["mixed_scope"]["evidence_sources"], list(D3_EVIDENCE_SOURCE_IDS))
        self.assertEqual(first["d3"]["live_access"]["network_requests"], 0)
        self.assertEqual(first["plan_hash"], second["plan_hash"])
        self.assertEqual(first["d3"]["fixture_availability"]["us.fsis"]["fixture_available"], True)
        self.assertFalse(first["publication"]["promoted"])
        self.assertFalse(first["publication"]["published"])
        self.assertEqual(first["d3"]["readiness"]["public_release_allowed"], False)

    def test_live_mode_is_fail_closed_without_network_access(self):
        result = build_mixed_rehearsal(run_root=self.root / "live", mode="live-acquisition")
        self.assertEqual(result["d3"]["live_access"]["performed"], False)
        self.assertEqual(result["d3"]["live_access"]["network_requests"], 0)
        self.assertEqual(result["exit_status"], "failed")
        self.assertEqual(result["counts"]["selected"], len(D3_REHEARSAL_SOURCE_IDS))
        self.assertEqual(result["counts"]["failed"], len(D3_REHEARSAL_SOURCE_IDS))
        self.assertEqual(result["counts"]["unsupported"], 0)
        self.assertEqual(result["publication"], {"release_created": False, "promoted": False, "published": False})
        for source in result["results"]:
            self.assertFalse(source["operational"]["previous_valid_state"]["verified"])
            self.assertFalse(any(source.get("publication", {}).values()))

        def keys(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    yield key
                    yield from keys(child)
            elif isinstance(value, list):
                for child in value:
                    yield from keys(child)

        self.assertNotIn("artifact_path", set(keys(result)))
        self.assertNotIn("private_path", set(keys(result)))

    def test_local_artifact_mode_runs_all_thirteen_sources(self):
        result = build_mixed_rehearsal(run_root=self.root / "local-artifact", mode="local-artifact")
        self.assertEqual(result["selected_sources"], list(D3_REHEARSAL_SOURCE_IDS))
        self.assertEqual(result["counts"]["succeeded"], len(D3_REHEARSAL_SOURCE_IDS))
        self.assertEqual(result["counts"]["failed"], 0)


if __name__ == "__main__":
    unittest.main()
