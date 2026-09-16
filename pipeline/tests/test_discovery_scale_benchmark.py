"""Unit contracts for the synthetic scale benchmark."""

import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "benchmarks" / "run_discovery_scale.py"
SPEC = importlib.util.spec_from_file_location("run_discovery_scale", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class DiscoveryScaleBenchmarkTests(unittest.TestCase):
    def test_default_scales_and_query_catalog_are_bounded(self):
        self.assertEqual(MODULE._validate_scales(list(MODULE.DEFAULT_SCALES)), (100_000, 1_000_000))
        self.assertEqual(len(MODULE.QUERY_SPECS), 8)
        self.assertEqual(
            {spec["name"] for spec in MODULE.QUERY_SPECS},
            {"list", "pagination", "filters", "text_filter", "bbox", "radius", "detail", "graph_ready"},
        )
        for spec in MODULE.QUERY_SPECS:
            self.assertNotIn("uec.", spec["sql"].lower())
            if spec["name"] != "detail":
                self.assertIn("limit 50", spec["sql"].lower())

    def test_scale_validation_rejects_unsafe_or_ambiguous_inputs(self):
        for scales in ([], [0], [-1], [MODULE.MAX_SCALE + 1], [100_000, 100_000]):
            with self.subTest(scales=scales), self.assertRaises(ValueError):
                MODULE._validate_scales(scales)

    def test_plan_summary_is_row_free_and_aggregated(self):
        payload = [{
            "Planning Time": 0.12,
            "Execution Time": 1.23,
            "Plan": {
                "Node Type": "Limit",
                "Actual Rows": 50,
                "Shared Hit Blocks": 3,
                "Plans": [{
                    "Node Type": "Index Scan",
                    "Index Name": "synthetic_index",
                    "Actual Rows": 50,
                    "Shared Read Blocks": 2,
                }],
            },
        }]
        report = MODULE.summarize_plan(json.dumps(payload))
        self.assertEqual(report["actual_rows"], 50)
        self.assertEqual(report["index_names"], ["synthetic_index"])
        self.assertEqual(report["shared_hit_blocks"], 3)
        self.assertEqual(report["shared_read_blocks"], 2)
        self.assertNotIn("Plan", report)
        self.assertNotIn("canonical_name", json.dumps(report).lower())
        self.assertNotIn("source_record", json.dumps(report).lower())


if __name__ == "__main__":
    unittest.main()
