from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path

from pipeline.common.real_private_graph import _MatcherStage, build_report, discover_manifests, run_rehearsal, write_report
from pipeline.common.graph_candidate import write_graph_candidates
from pipeline.common.graph_persistence import build_candidate_connection_edges, load_graph_candidate_handoff


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

    def test_fsis_alias_matcher_stage_produces_supported_inferred_edge(self):
        handoff = self.root / "fsis" / "graph-candidates"
        write_graph_candidates(handoff, [
            {"source_id": "us.fsis", "source_row": 1, "source_record_key": "fsis-a",
             "normalized": {"establishment_id": "FS-001", "dba_names": ["Synthetic Business Name"]}},
            {"source_id": "us.fsis", "source_row": 2, "source_record_key": "fsis-b",
             "normalized": {"establishment_id": "FS-002", "alternate_names": ["synthetic business name"]}},
        ], artifact_sha256="a" * 64, observed_at="2026-01-01T00:00:00Z")
        stage = _MatcherStage()
        try:
            stage.add_handoff(handoff)
            stats = stage.build_candidates()
            first = next(row for row in load_graph_candidate_handoff(handoff)[1]
                         if row["source_record_key"] == "fsis-a")
            manifest = {"source_id": "us.fsis", "retrieved_at_utc": "2026-01-02T00:00:00Z"}
            edges = build_candidate_connection_edges(first, manifest, edge_builder=stage.edge_builder)
            self.assertEqual(stats["shared_business_name_pairs_emitted"], 1)
            self.assertEqual(len(edges), 1)
            self.assertEqual(edges[0]["relationship_type"], "shared_business_name")
            self.assertEqual(edges[0]["connection_type"], "inferred")
            self.assertEqual({ref["source_record_key"] for ref in edges[0]["supporting_source_refs"]}, {"fsis-a", "fsis-b"})
        finally:
            stage.close()


if __name__ == "__main__":
    unittest.main()
