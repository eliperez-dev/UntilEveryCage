"""Unit contracts for the bounded local API load rehearsal."""

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "benchmarks" / "run_api_load_rehearsal.py"
SPEC = importlib.util.spec_from_file_location("run_api_load_rehearsal", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class ApiLoadRehearsalTests(unittest.TestCase):
    def test_requested_scale_is_supported_without_unbounded_seeding(self):
        self.assertEqual(MODULE.MAX_SEED, 25_000)
        self.assertEqual(MODULE.validate_observations(25_000), 25_000)
        with self.assertRaises(ValueError):
            MODULE.validate_observations(25_001)

    def test_levels_and_targets_are_bounded(self):
        self.assertEqual(MODULE.validate_levels([1, 4, 8, 16]), (1, 4, 8, 16))
        for levels in ([], [0], [17], [1, 1]):
            with self.subTest(levels=levels), self.assertRaises(ValueError):
                MODULE.validate_levels(levels)
        self.assertEqual(MODULE.validate_loopback_url("http://127.0.0.1:8000").hostname, "127.0.0.1")
        self.assertEqual(MODULE.validate_loopback_url("http://localhost:8000/").hostname, "localhost")
        for target in ("https://127.0.0.1:8000", "http://203.0.113.5:8000", "http://127.0.0.1:8000/api", "http://user:pass@127.0.0.1:8000"):
            with self.subTest(target=target), self.assertRaises(ValueError):
                MODULE.validate_loopback_url(target)

    def test_summary_is_aggregate_only_and_preserves_error_signals(self):
        samples = [
            MODULE.Sample("list", 10.0, 200, False, None, 40),
            MODULE.Sample("radius", 20.0, 503, False, None, 0),
            MODULE.Sample("detail", 30.0, 0, True, "timeout", 0),
        ]
        sampler = type("Sampler", (), {"max_active": 4, "max_waiting": 1, "max_connections": 20})()
        report = MODULE.summarize(samples, 1.0, sampler)
        self.assertEqual(report["requests"], 3)
        self.assertEqual(report["successes"], 1)
        self.assertEqual(report["server_errors"], 1)
        self.assertEqual(report["timeouts"], 1)
        self.assertEqual(report["pool_pressure_signals"]["http_503_or_higher"], 1)
        self.assertEqual(report["database_signals"]["max_waiting_sessions"], 1)
        self.assertNotIn("/api/", str(report))
        self.assertNotIn("latitude", str(report))
        self.assertNotIn("facility", str(report).lower())

    def test_deterministic_fixture_identifiers_are_stable(self):
        self.assertEqual(MODULE.deterministic_uuid("load-facility", 1), MODULE.deterministic_uuid("load-facility", 1))
        self.assertNotEqual(MODULE.deterministic_uuid("load-facility", 1), MODULE.deterministic_uuid("load-facility", 2))

    def test_recommendations_fail_safe_when_every_level_has_pressure(self):
        results = [
            {"concurrency": 1, "timeouts": 1, "server_errors": 0, "connection_errors": 0},
            {"concurrency": 4, "timeouts": 0, "server_errors": 0, "connection_errors": 1},
        ]
        recommendations = MODULE.build_recommendations(results, 2000)
        self.assertIsNone(recommendations["initial_api_pool_per_process"])
        self.assertEqual(recommendations["clean_tested_concurrency_levels"], [])
        self.assertIn("blocked", recommendations["basis"])

    def test_recommendations_choose_only_clean_levels(self):
        results = [
            {"concurrency": 1, "timeouts": 0, "server_errors": 0, "connection_errors": 0},
            {"concurrency": 4, "timeouts": 1, "server_errors": 0, "connection_errors": 0},
        ]
        recommendations = MODULE.build_recommendations(results, 2000)
        self.assertEqual(recommendations["initial_api_pool_per_process"], 1)
        self.assertEqual(recommendations["clean_tested_concurrency_levels"], [1])


if __name__ == "__main__":
    unittest.main()
