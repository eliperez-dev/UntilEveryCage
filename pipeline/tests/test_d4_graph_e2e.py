"""D4 synthetic private graph/evidence contract rehearsal."""
from __future__ import annotations

import json
import os
import unittest
from pathlib import Path

from pipeline.common.d4_graph_e2e import (
    D4_FACILITY_SOURCE_IDS,
    D4_SOURCE_IDS,
    D4_SOURCE_KINDS,
    SyntheticPrivateGraph,
    GraphRehearsalError,
    run_scale_rehearsal,
)


ROOT = Path(__file__).parents[1]
MANIFEST = ROOT.parent / "data" / "manifests" / "d4-private-graph-e2e.json"


class D4GraphE2ETests(unittest.TestCase):
    def test_manifest_is_row_free_and_covers_thirteen_sources(self):
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(manifest["schema_version"], "d4-private-graph-e2e-manifest-v1")
        self.assertEqual(manifest["source_ids"], list(D4_SOURCE_IDS))
        self.assertEqual(len(manifest["source_ids"]), 13)
        self.assertEqual(len(D4_FACILITY_SOURCE_IDS), 11)
        self.assertEqual(len(manifest["source_kinds"]), 13)
        self.assertEqual(manifest["execution"]["facility_sources"], 11)
        self.assertEqual(manifest["execution"]["evidence_sources"], 2)
        def keys(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    yield key
                    yield from keys(child)
            elif isinstance(value, list):
                for child in value:
                    yield from keys(child)
        self.assertNotIn("records", set(keys(manifest)))
        self.assertNotIn("payload", set(keys(manifest)))
        self.assertNotIn("raw_rows", set(keys(manifest)))
        self.assertNotIn("private_path", set(keys(manifest)))

    def test_one_facility_eleven_facilities_and_two_evidence_sources_are_sequential(self):
        graph = SyntheticPrivateGraph()
        receipts = [graph.import_batch(source, D4_SOURCE_KINDS[source], (f"fixture-{index}",)) for index, source in enumerate(D4_SOURCE_IDS)]
        self.assertEqual(len(receipts), 13)
        self.assertTrue(all(receipt.status == "completed" for receipt in receipts))
        self.assertEqual(graph.private_query("d4-private-token"), {"entities": 11, "evidence": 2, "review_required": 0})
        report = graph.report()
        self.assertEqual(report["scope"]["execution"], "sequential")
        self.assertEqual(report["public"]["entities"], 0)

    def test_rerun_is_idempotent_and_interrupted_batch_resumes(self):
        graph = SyntheticPrivateGraph()
        first = graph.import_batch("us.fsis", "facility_master", ("a", "b"))
        duplicate = graph.import_batch("us.fsis", "facility_master", ("b", "a"))
        self.assertEqual(first.status, "completed")
        self.assertEqual(duplicate.status, "already_present")
        interrupted = graph.import_batch("us.aphis", "evidence_event", ("e1", "e2"), interrupted_after=1)
        self.assertEqual(interrupted.status, "interrupted")
        resumed = graph.import_batch("us.aphis", "evidence_event", ("e1", "e2"))
        self.assertEqual(resumed.status, "completed")
        self.assertEqual(graph.private_query("d4-private-token")["evidence"], 2)

    def test_corruption_isolated_and_source_kind_mismatch_rejected(self):
        graph = SyntheticPrivateGraph()
        graph.import_batch("us.fsis", "facility_master", ("good",))
        with self.assertRaisesRegex(GraphRehearsalError, "corrupted"):
            graph.import_batch("us.aphis", "evidence_event", ("bad",), corrupted=True)
        with self.assertRaisesRegex(GraphRehearsalError, "source-kind mismatch"):
            graph.import_batch("us.aphis", "facility_master", ("wrong-kind",))
        graph.import_batch("us.inspections", "evidence_event", ("still-good",))
        self.assertEqual(graph.private_query("d4-private-token"), {"entities": 1, "evidence": 1, "review_required": 0})

    def test_review_lineage_suppression_and_public_private_boundaries(self):
        graph = SyntheticPrivateGraph()
        candidate = graph.review_exact_id("us.fsis", "FSIS-SYNTHETIC-ID")
        self.assertTrue(candidate.startswith("candidate:us.fsis:"))
        with self.assertRaisesRegex(GraphRehearsalError, "US FSIS"):
            graph.review_exact_id("us.aphis", "APHIS-SYNTHETIC-ID")
        graph.queue_match_candidate("deterministic", "same-source-key")
        graph.queue_match_candidate("probabilistic", "similarity-only")
        graph.record_lineage("merge", subject="source-scoped-a", target="reviewed-b")
        graph.record_lineage("split", subject="reviewed-b", target="source-scoped-c")
        graph.record_lineage("reversal", subject="reviewed-b", target="source-scoped-a")
        graph.suppress(candidate)
        self.assertFalse(graph.report()["review"]["auto_merge"])
        self.assertEqual(graph.report()["review"]["deterministic_candidates"], 1)
        self.assertEqual(graph.report()["review"]["probabilistic_candidates"], 1)
        self.assertEqual(graph.report()["lineage"]["events"], 3)
        self.assertEqual(graph.report()["suppression"]["active"], 1)
        self.assertEqual(graph.public_query(), {"entities": 0, "evidence": 0, "relationships": 0, "release_created": False})
        with self.assertRaises(PermissionError):
            graph.private_query("wrong-token")

    def test_scale_rehearsal_is_bounded_and_aggregate_only(self):
        result = run_scale_rehearsal(count=10_000, batch_size=500)
        self.assertEqual(result["count"], 10_000)
        self.assertEqual(result["batches"], 20)
        self.assertTrue(result["bounded"])
        self.assertEqual(result["public_rows"], 0)
        self.assertNotIn("records", result)

    @unittest.skipUnless(os.environ.get("UEC_D4_RUN_100K") == "1", "optional 100k benchmark is opt-in")
    def test_optional_100k_scale_rehearsal(self):
        result = run_scale_rehearsal(count=100_000, batch_size=1_000)
        self.assertEqual(result["count"], 100_000)
        self.assertEqual(result["batches"], 100)
        self.assertEqual(result["public_rows"], 0)


if __name__ == "__main__":
    unittest.main()
