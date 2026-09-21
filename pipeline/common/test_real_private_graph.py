from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path

from pipeline.common.real_private_graph import build_report, discover_manifests, run_rehearsal, write_report


class RealPrivateGraphTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(".tmp") / "d5-real-private-graph-tests"
        shutil.rmtree(self.root, ignore_errors=True)
        self.root.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_manifest_discovery_is_row_free_and_deduplicated(self):
        root = self.root
        payload = {
                "source_id": "test.real",
                "normalized_rows": 4,
                "quarantined_rows": 1,
                "graph_candidate_summary": {
                    "candidate_count": 4,
                    "facility_identifier_candidates": 3,
                    "organization_identifier_candidates": 2,
                    "operator_relationship_candidates": 2,
                },
                "review_metrics": {"geospatial": {"coordinate_state_counts": {"exact": 3, "unmapped": 1}}},
                "release_state": "not-created",
                "publication_state": "private-candidate",
            }
        (root / "manifest.json").write_text(json.dumps(payload), encoding="utf-8")
        (root / "copy.json").write_text(json.dumps(payload), encoding="utf-8")
        records = discover_manifests([root])
        self.assertEqual(len(records), 1)
        report = build_report([root])
        self.assertEqual(report["source_count"], 1)
        self.assertEqual(report["totals"]["normalized_rows"], 4)
        self.assertEqual(report["sources"][0]["coordinate_state_counts"], {"exact": 3, "unmapped": 1})
        self.assertEqual(report["sources"][0]["integrity_status"], "missing-provenance")
        self.assertNotIn("records", json.dumps(report))

    def test_source_list_expands_without_payload(self):
        root = self.root
        (root / "aggregate-report.json").write_text(json.dumps({"sources": [{"source_id": "a.real", "normalized_rows": 2}, {"source_id": "b.real", "normalized_rows": 3}]}), encoding="utf-8")
        report = build_report([root])
        self.assertEqual(report["source_count"], 2)
        self.assertEqual(report["totals"]["normalized_rows"], 5)

    def test_selection_prefers_detailed_quarantine_counts(self):
        root = self.root
        (root / "run-a-manifest.json").write_text(json.dumps({"source_id": "a.real", "normalized_rows": 10, "quarantined_rows": 0}), encoding="utf-8")
        (root / "run-b-manifest.json").write_text(json.dumps({"source_id": "a.real", "normalized_rows": 10, "quarantined_rows": 2}), encoding="utf-8")
        report = build_report([root])
        self.assertEqual(report["sources"][0]["quarantined_rows"], 2)

    def test_real_handoff_discovery_and_private_report(self):
        root = self.root
        handoff = root / "source" / "graph-candidates"
        handoff.mkdir(parents=True)
        (handoff / "manifest.json").write_text(json.dumps({"source_id": "a.real", "release_state": "not-created", "publication_state": "private-candidate", "records_sha256": ""}), encoding="utf-8")
        (handoff / "records.jsonl").write_text("", encoding="utf-8")
        report = run_rehearsal([root])
        self.assertEqual(report["handoffs"]["facility"], 1)
        self.assertFalse(report["publication"]["approval_inferred"])
        digest = write_report(report, root / "report.json")
        self.assertEqual(len(digest), 64)


if __name__ == "__main__":
    unittest.main()
