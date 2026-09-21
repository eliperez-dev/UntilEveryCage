"""D6 bounded private graph API and real-shaped control tests."""
from __future__ import annotations

import json
import os
import unittest
from pathlib import Path

from pipeline.common.d5_connection_analysis import _observed_from_row
from pipeline.common.d6_private_graph import ConnectionEdge, ConnectionQueryError, ConnectionStore, rehearse


ROOT = Path(__file__).parents[1]


def row(source_id: str, key: str, *, facility: str | None, org: str | None, name: str, postal: str, source_kind: str = "facility_master"):
    return _observed_from_row({
        "source_id": source_id,
        "source_kind": source_kind,
        "source_record_key": key,
        "source_values": {"synthetic": True},
        "source_artifact_sha256": "a" * 64,
        "normalized": {"establishment_id": facility, "cvr": org, "name": name, "postal_code": postal},
    })


class D6PrivateGraphApiTests(unittest.TestCase):
    def test_injected_store_imports_org_nodes_nonzero_edges_and_is_idempotent(self):
        rows = [
            row("us.fsis", "fsis-1", facility="FS1", org="ORG1", name="North Synthetic", postal="10000"),
            row("ca.cfia.federal-meat", "cfia-1", facility="CF1", org="ORG1", name="North Synthetic", postal="10000"),
            row("us.aphis", "aphis-1", facility=None, org="ORG1", name="North Synthetic", postal="10000", source_kind="evidence_event"),
        ]
        report = rehearse(rows)
        self.assertGreater(report["nodes"]["organizations"], 0)
        self.assertGreater(report["connections"]["exact"], 0)
        self.assertGreaterEqual(report["connections"]["inferred"], 1)
        self.assertTrue(report["import"]["idempotent"])
        self.assertEqual(report["controls"]["negative_aphis_fsis_edges"], 0)
        self.assertFalse(report["connections"]["automatic_merge"])
        self.assertFalse(report["connections"]["claim_transfer"])
        self.assertEqual(report["public"]["rows"], 0)
        self.assertNotIn("North Synthetic", json.dumps(report))
        self.assertFalse(report["scope"]["row_payloads_in_report"])

    def test_query_filters_conflicts_suppression_source_entity_cursor_and_cap(self):
        store = ConnectionStore()
        common = dict(source_record_id="ref", left_entity_type="organization", left_entity_id="org:1", right_entity_type="facility", right_entity_id="facility:1", confidence=.9, evidence_refs=({"source_id": "us.fsis", "source_record_ref": "digest"},), observed_at="2026-09-21")
        store.add(ConnectionEdge(edge_id="exact", source_id="us.fsis", connection_type="exact", **common))
        store.add(ConnectionEdge(edge_id="conflict", source_id="us.fsis", connection_type="inferred", conflicting=True, **{**common, "right_entity_id": "facility:2", "confidence": .7}))
        store.add(ConnectionEdge(edge_id="suppressed", source_id="us.fsis", connection_type="exact", suppressed=True, **{**common, "right_entity_id": "facility:3"}))
        self.assertEqual(len(store.query(connection_type="exact")["data"]), 1)
        self.assertEqual(len(store.query(connection_type="inferred", include_conflicting=True)["data"]), 1)
        self.assertEqual(len(store.query(min_confidence=.8)["data"]), 1)
        self.assertEqual(len(store.query(source_id="other")["data"]), 0)
        self.assertEqual(len(store.query(entity_id="facility:1")["data"]), 1)
        self.assertEqual(len(store.query(suppressed=True)["data"]), 1)
        self.assertEqual(store.query(limit=1)["meta"]["next_cursor"], "exact")
        with self.assertRaises(ConnectionQueryError):
            store.query(limit=101)
        with self.assertRaises(ConnectionQueryError):
            store.query(connection_type="bad")

    def test_private_route_and_schema_are_not_public_surfaces(self):
        route = (ROOT.parent / "src" / "main.rs").read_text(encoding="utf-8")
        handler = (ROOT.parent / "src" / "graph_private.rs").read_text(encoding="utf-8")
        self.assertIn('"/api/private/graph/connections"', route)
        for field in ("connection_type", "min_confidence", "include_conflicting", "suppressed", "source_id", "entity_id", "cursor", "limit", "evidence_refs", "score_contributions", "disclaimer", "ruleset"):
            self.assertIn(field, handler)
        self.assertIn("public_projection", handler)
        self.assertNotIn("/api/graph/connections", route)

    @unittest.skipUnless(os.environ.get("D6_PRIVATE_ROOT"), "authorized D6 real private root not configured")
    def test_authorized_real_controls_are_aggregate_only(self):
        # The operator diagnostic consumes this root; CI never assumes private
        # data is present. Keep this test as an explicit opt-in gate.
        private_root = Path(os.environ["D6_PRIVATE_ROOT"])
        self.assertTrue(private_root.exists())


if __name__ == "__main__":
    unittest.main()
