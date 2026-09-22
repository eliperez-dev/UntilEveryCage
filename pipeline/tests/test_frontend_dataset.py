from __future__ import annotations
import unittest
from pathlib import Path
from pipeline.common.frontend_dataset import SEED, build, validate

class FrontendDatasetTests(unittest.TestCase):
    def setUp(self) -> None:
        # Keep generated rows under the repository's ignored report area. This
        # also works on managed Windows hosts that deny user-temp ACLs.
        self._tmp_root = Path("data") / "reports" / "e1-dataset-tests"
        self._tmp_root.mkdir(parents=True, exist_ok=True)

    def test_representative_corpus_is_deterministic_and_complete(self) -> None:
        first, second = self._tmp_root / "first", self._tmp_root / "second"
        one, two = build(first, mode="representative", seed=SEED), build(second, mode="representative", seed=SEED)
        self.assertEqual(one["files"]["locations"]["sha256"], two["files"]["locations"]["sha256"]); self.assertEqual(one["files"]["graph_edges"]["sha256"], two["files"]["graph_edges"]["sha256"]); self.assertTrue(validate(first)["ok"]); self.assertEqual(one["public_projection"]["facility_rows"], 0); self.assertEqual(one["public_projection"]["graph_edges"], 0)

    def test_private_mode_is_aggregate_only_and_allowlisted(self) -> None:
        root = self._tmp_root / "private"; root.mkdir(parents=True, exist_ok=True)
        manifest = Path(root) / "private.json"; manifest.write_text('{"sources":[{"source_id":"it.853-2004","input_rows":5,"normalized_rows":4,"quarantined_rows":1,"status":"candidate-ready; private only","raw_artifact":"must-not-leak"},{"source_id":"ca.ontario.meat-plants","normalized_rows":99}]}', encoding="utf-8"); output = Path(root) / "out"; result = build(output, mode="private", private_manifest=manifest)
        self.assertEqual(result["source_inventory"][0]["source_id"], "it.853-2004"); self.assertNotIn("raw_artifact", (output / "manifest.json").read_text(encoding="utf-8")); self.assertTrue(validate(output)["ok"]); self.assertEqual((output / "locations.jsonl").read_text(encoding="utf-8"), "")

    def test_small_performance_request_fails_closed(self) -> None:
        with self.assertRaises(ValueError): build(self._tmp_root / "small-performance", mode="performance", performance_count=999, edge_count=999)
