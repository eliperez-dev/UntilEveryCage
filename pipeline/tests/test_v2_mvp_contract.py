"""Prevent the V2 MVP claim matrix and API freeze from drifting."""

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[2]
MATRIX_JSON = ROOT / "docs" / "governance" / "v2-mvp-claim-evidence.json"
MATRIX_MD = ROOT / "docs" / "governance" / "v2-mvp-claim-evidence.md"
FREEZE_JSON = ROOT / "docs" / "api" / "v2-mvp-contract.json"
SOURCE_CONTRACT = ROOT / "docs" / "api" / "v2-contract.json"
LOCATION_SCHEMA = ROOT / "docs" / "api" / "v2-location.schema.json"


class V2MvpContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.matrix = json.loads(MATRIX_JSON.read_text(encoding="utf-8"))
        cls.freeze = json.loads(FREEZE_JSON.read_text(encoding="utf-8"))
        cls.source_contract = json.loads(SOURCE_CONTRACT.read_text(encoding="utf-8"))
        cls.location_schema = json.loads(LOCATION_SCHEMA.read_text(encoding="utf-8"))

    def test_matrix_has_required_domains_and_evidence(self):
        allowed = set(self.matrix["status_definitions"])
        claims = self.matrix["claims"]
        self.assertEqual(len({claim["id"] for claim in claims}), len(claims))
        self.assertTrue({"ethics", "safety", "provenance", "publication", "privacy", "lifecycle", "graph", "scale", "geospatial", "operational"} <= {claim["area"] for claim in claims})
        for claim in claims:
            self.assertIn(claim["status"], allowed, claim["id"])
            self.assertTrue(claim["claim"].strip(), claim["id"])
            self.assertTrue(claim["limit"].strip(), claim["id"])
            self.assertGreater(len(claim["evidence"]), 0, claim["id"])
            for evidence in claim["evidence"]:
                path = ROOT / evidence["path"]
                self.assertTrue(path.is_file(), f"{claim['id']}: missing {evidence['path']}")
                self.assertGreaterEqual(evidence.get("line", 1), 1)

    def test_matrix_ids_are_present_in_human_document(self):
        document = MATRIX_MD.read_text(encoding="utf-8")
        for claim in self.matrix["claims"]:
            self.assertIn(f"`{claim['id']}`", document)

    def test_matrix_markdown_links_resolve(self):
        document = MATRIX_MD.read_text(encoding="utf-8")
        for target in re.findall(r"\]\(([^)]+)\)", document):
            if target.startswith(("http://", "https://", "#")):
                continue
            path = target.split("#", 1)[0]
            self.assertTrue((MATRIX_MD.parent / path).is_file(), target)

    def test_freeze_endpoint_inventory_matches_source_contract(self):
        frozen = set(self.freeze["public_endpoints"] + self.freeze["development_only_endpoints"] + self.freeze["operator_surfaces"])
        self.assertEqual(frozen, set(self.source_contract["endpoints"]))
        self.assertEqual(self.freeze["api_version"], self.source_contract["version"])
        self.assertEqual(self.freeze["location_schema"], "docs/api/v2-location.schema.json")

    def test_location_schema_is_closed_and_self_consistent(self):
        properties = set(self.location_schema["properties"])
        required = set(self.location_schema["required"])
        self.assertTrue(self.location_schema["additionalProperties"] is False)
        self.assertEqual(properties, required)
        self.assertEqual(self.freeze["schema_version"], "uec-location-projection-v1")

    def test_freeze_declares_non_goals_and_change_policy(self):
        self.assertGreaterEqual(len(self.freeze["non_goals"]), 5)
        self.assertIn("Breaking", self.freeze["change_policy"])


if __name__ == "__main__":
    unittest.main()
