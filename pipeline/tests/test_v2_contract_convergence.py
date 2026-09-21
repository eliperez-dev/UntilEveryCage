"""Cross-surface tests for the frozen V2 product/API contract."""

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[2]
API = ROOT / "docs" / "api"


class V2ContractConvergenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = json.loads((API / "v2-contract.json").read_text(encoding="utf-8"))
        cls.freeze = json.loads((API / "v2-mvp-contract.json").read_text(encoding="utf-8"))
        cls.schema = json.loads((API / "v2-location.schema.json").read_text(encoding="utf-8"))
        cls.ledger = json.loads((API / "v2-product-convergence-gap-ledger.json").read_text(encoding="utf-8"))
        cls.rust = (ROOT / "src" / "lib.rs").read_text(encoding="utf-8")
        cls.js = (ROOT / "static" / "modules" / "v2Contract.js").read_text(encoding="utf-8")
        cls.wire = (ROOT / "frontend" / "src" / "api" / "wireSchema.ts").read_text(encoding="utf-8")

    def test_freeze_endpoints_match_machine_contract(self):
        frozen = set(self.freeze["public_endpoints"] + self.freeze["development_only_endpoints"] + self.freeze["operator_surfaces"])
        self.assertEqual(frozen, set(self.contract["endpoints"]))
        routes = set(re.findall(r'\.route\(\s*"([^"]+)"', (ROOT / "src" / "main.rs").read_text(encoding="utf-8")))
        contract_routes = {endpoint[4:].split("?", 1)[0] for endpoint in self.contract["endpoints"] if endpoint.startswith("GET ")}
        self.assertTrue(contract_routes <= routes)

    def test_offset_compatibility_and_cursor_preference_are_explicit(self):
        locations = self.contract["endpoints"]["GET /api/v2/locations"]
        self.assertIn("offset", locations["query"])
        self.assertEqual(locations["pagination"]["mutually_exclusive"], ["cursor", "offset"])
        self.assertIn("preferred", locations["pagination"]["cursor"])
        self.assertIn("bbox or radius", locations["spatial"])
        self.assertIn("min_lon", locations["query"])
        self.assertIn("radius_km", locations["query"])
        self.assertIn("offset", self.rust)
        self.assertIn("cursor and offset cannot be combined", self.rust)

    def test_rust_schema_and_static_validator_have_same_location_fields(self):
        block = re.search(r"pub struct V2Location \{(.*?)\n\}", self.rust, re.S).group(1)
        rust_fields = set(re.findall(r"pub (\w+):", block))
        self.assertEqual(rust_fields, set(self.schema["properties"]))
        self.assertEqual(rust_fields, set(re.findall(r"'([a-z_]+)'", re.search(r"V2_LOCATION_FIELDS = Object\.freeze\(\[(.*?)\]\)", self.js, re.S).group(1))))
        self.assertEqual(set(self.schema["required"]), rust_fields)
        self.assertIn(".strict()", self.wire)
        for field in rust_fields:
            self.assertIn(field, self.wire)

    def test_ledger_names_every_required_deferred_surface(self):
        by_id = {gap["id"]: gap for gap in self.ledger["gaps"]}
        expected = {
            "GAP-EVIDENCE-INTEGRITY": ("evidence_content_hash", "evidence_record_id"),
            "GAP-SOURCE-DATES-AVAILABILITY": ("source_publication_date", "source_effective_date", "source_availability_status"),
            "GAP-GEOCODER-METADATA": ("geocoder_provider", "geocoder_query", "geocoder_precision"),
            "GAP-REVIEW-EVENTS": ("review_event_id", "review_scope", "review_date", "review_outcome"),
            "GAP-APPROVAL-METADATA": ("approval_event_id", "approval_scope", "approval_decided_at"),
            "GAP-FRONTEND-REVOCATION": ("durable_frontend_cache", "cache_invalidation_signal", "revocation_signal"),
        }
        self.assertEqual(set(expected), set(by_id))
        for gap_id, fields in expected.items():
            self.assertTrue(set(fields) <= set(by_id[gap_id]["deferred"]), gap_id)
            self.assertEqual(by_id[gap_id]["status"], "deferred")

    def test_mvp_points_to_gap_ledger_without_promising_deferred_fields(self):
        self.assertEqual(self.freeze["deferred_contract_gaps"], "docs/api/v2-product-convergence-gap-ledger.json")
        self.assertIn("no promised durable cache", " ".join(self.freeze["invariants"]))
        self.assertNotIn("evidence_content_hash", self.schema["properties"])
        self.assertNotIn("geocoder_provider", self.schema["properties"])


if __name__ == "__main__":
    unittest.main()
