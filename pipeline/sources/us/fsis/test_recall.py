import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from .recall import build_recall_candidate, parse_bytes, write_private_run

ROOT = Path(__file__).parent


class RecallAdapterTests(unittest.TestCase):
    def test_explicit_identifier_is_accepted_and_name_only_is_quarantined(self):
        raw = (ROOT / "fixtures/recalls.json").read_bytes()
        result = parse_bytes(raw, retrieved_at="2026-09-18T00:00:00Z")
        self.assertEqual(len(result["accepted"]), 1)
        self.assertIn("unresolved_establishment_identifier", result["quarantined"][0]["reasons"])

    def test_candidate_is_private_and_claim_retains_dates_and_support(self):
        raw = (ROOT / "fixtures/recalls.json").read_bytes()
        parsed = parse_bytes(raw, retrieved_at="2026-09-18T00:00:00Z")
        candidate = build_recall_candidate(parsed["accepted"][0], artifact_sha256=hashlib.sha256(raw).hexdigest(), observed_at="2026-09-18T00:00:00Z")
        claim = candidate["claims"][-1]
        self.assertEqual(claim["value"]["recall_date"], "2026-09-01")
        self.assertEqual(candidate["publication"]["publication_status"], "not_eligible")
        self.assertEqual(candidate["review_state"], "review_required")

    def test_run_is_deterministic_and_row_free_manifest(self):
        raw = (ROOT / "fixtures/recalls.json").read_bytes()
        with tempfile.TemporaryDirectory() as left, tempfile.TemporaryDirectory() as right:
            a = write_private_run(raw, left, retrieved_at="2026-09-18T00:00:00Z")
            b = write_private_run(raw, right, retrieved_at="2026-09-18T00:00:00Z")
            self.assertEqual(a, b)
            self.assertEqual(json.loads((Path(left) / "aggregate-manifest.json").read_text())["quarantined_rows"], 1)
            self.assertFalse("records" in json.dumps(a))

    def test_digits_in_free_text_do_not_create_establishment_join(self):
        parsed = parse_bytes(json.dumps({"results": [{
            "recall_number": "FSIS-2026-003",
            "firm": "Foods 123 LLC",
            "reason": "Product code 456",
        }]}).encode("utf-8"))
        self.assertEqual(len(parsed["accepted"]), 0)
        self.assertIn("unresolved_establishment_identifier", parsed["quarantined"][0]["reasons"])


if __name__ == "__main__":
    unittest.main()
