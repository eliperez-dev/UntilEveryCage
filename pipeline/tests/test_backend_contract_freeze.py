"""Regression checks for the final V2 backend/frontend contract boundary."""

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[2]


class BackendContractFreezeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = json.loads(
            (ROOT / "docs/api/v2-backend-contract-freeze.json").read_text(encoding="utf-8")
        )
        cls.product = (ROOT / "docs/PRODUCT-READINESS.md").read_text(encoding="utf-8")
        cls.graph = (ROOT / "docs/api/private-graph-contract.md").read_text(encoding="utf-8")
        cls.source_status = json.loads(
            (ROOT / "docs/source-status.json").read_text(encoding="utf-8")
        )

    def test_graph_has_only_exact_and_inferred_without_human_state(self):
        graph = self.contract["private_graph"]
        self.assertEqual(graph["connection_types"], ["exact", "inferred"])
        self.assertFalse(graph["human_confirmed_state"])
        self.assertIsNone(graph["storage_cap"])
        self.assertIn("source_qualified_endpoints", graph["required_metadata"])
        self.assertIn("confidence", graph["required_metadata"])
        self.assertIn("disclaimer", graph["required_metadata"])

    def test_boundaries_are_explicit(self):
        self.assertEqual(self.contract["status"], "frozen-for-frontend-integration")
        self.assertEqual(self.contract["public_location_pagination"]["default_limit"], 100)
        self.assertEqual(self.contract["public_location_pagination"]["max_limit"], 1000)
        self.assertEqual(self.contract["public_location_pagination"]["mutually_exclusive"], ["cursor", "offset"])
        self.assertTrue(any("suppression" in invariant for invariant in self.contract["invariants"]))
        self.assertTrue(any("publication" in invariant for invariant in self.contract["invariants"]))
        self.assertIn("There is no `human_confirmed` connection state.", self.graph)
        self.assertIn("page bound is not a storage cap", self.graph)

    def test_readiness_does_not_regress_to_human_graph_gate_or_old_d6_gate(self):
        self.assertIn("D6.2 integration", self.product)
        self.assertIn("### D6.2 — Backend architecture closure and contract freeze", self.product)
        self.assertNotIn("| Identity and reconciliation | Blocked: human review |", self.product)
        self.assertNotIn("inferred-edge materialization and publication remain open", self.product)
        self.assertIn("historical 5,000 probabilistic-candidate", self.product)
        self.assertIn("not a graph connection state or a prerequisite", self.product)

    def test_source_status_points_to_legacy_metadata_ledger(self):
        legacy = self.source_status["legacy_archive"]
        self.assertEqual(legacy["manifest"], "data/manifests/legacy-files.csv")
        self.assertEqual(legacy["status_ledger"], "data/manifests/legacy-status.json")
        self.assertEqual(legacy["database_migration_status"], "metadata_only_not_migrated")
        self.assertEqual(legacy["public_projection"], "not_eligible")


if __name__ == "__main__":
    unittest.main()
