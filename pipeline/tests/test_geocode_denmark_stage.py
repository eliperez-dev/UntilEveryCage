import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "stages" / "geocode-denmark-dawa.py"
spec = importlib.util.spec_from_file_location("geocode_stage", SCRIPT)
MODULE = importlib.util.module_from_spec(spec)
spec.loader.exec_module(MODULE)


class DenmarkGeocodeStageTests(unittest.TestCase):
    def test_limit_is_bounded_and_provider_approval_is_required(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "provider.json"
            config.write_text(json.dumps({"provider_id": "test", "base_url": "https://example.invalid", "status": "pending", "terms_reviewed": False, "rate_limit_requests_per_second": 1}), encoding="utf-8")
            with self.assertRaises(ValueError):
                MODULE.run(Path(directory) / "missing.jsonl", Path(directory) / "out.jsonl", 0, 0, 1, config, None, None, True)
            with self.assertRaises(ValueError):
                MODULE.run(Path(directory) / "missing.jsonl", Path(directory) / "out.jsonl", MODULE.MAX_BATCH + 1, 0, 1, config, None, None, False)

    def test_network_is_explicit_and_requires_a_per_run_terms_review(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "provider.json"
            queue = root / "queue.jsonl"
            config.write_text(json.dumps({"provider_id": "test", "base_url": "https://example.invalid", "mode": "development_only", "status": "approved_for_development", "rate_limit_requests_per_second": 1}), encoding="utf-8")
            queue.write_text("", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "explicitly enabled"):
                MODULE.run(queue, root / "out.jsonl", 1, 0, 1, config, None, None, False)
            with self.assertRaisesRegex(ValueError, "terms review"):
                MODULE.run(queue, root / "out.jsonl", 1, 0, 1, config, None, None, True)

    def test_suppression_keys_are_payload_free_and_strict(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "suppression.jsonl"
            path.write_text('{"source_id":"dk.smiley","source_record_key":"123"}\n', encoding="utf-8")
            self.assertEqual(MODULE.load_suppression_keys(path), {("dk.smiley", "123")})
            path.write_text('{"source_id":"","source_record_key":"123"}\n', encoding="utf-8")
            with self.assertRaises(ValueError):
                MODULE.load_suppression_keys(path)

    def test_provider_acceptance_requires_review_for_single_point(self):
        self.assertEqual(MODULE.acceptance([{"x": 10, "y": 55}]), "accepted_single_point")
        self.assertEqual(MODULE.acceptance([{"x": 10, "y": 55}, {"x": 11, "y": 56}]), "review_multiple_points")
        self.assertEqual(MODULE.acceptance([]), "unresolved")

    def test_suppressed_records_are_not_requested_and_report_is_aggregate_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "provider.json"
            terms = root / "terms.json"
            queue = root / "queue.jsonl"
            suppressions = root / "suppression.jsonl"
            output = root / "results.jsonl"
            config.write_text(json.dumps({"provider_id": "test", "base_url": "https://example.invalid", "mode": "development_only", "status": "approved_for_development", "rate_limit_requests_per_second": 1}), encoding="utf-8")
            terms.write_text(json.dumps({"reviewer": "synthetic", "reference": "https://example.invalid/terms", "reviewed_at": "2026-01-01T00:00:00Z", "decision": "approved", "notes": "synthetic test"}), encoding="utf-8")
            queue.write_text("\n".join(json.dumps(item) for item in [
                {"queue_key": "dk.smiley:blocked", "source_id": "dk.smiley", "source_record_key": "blocked", "original_address": {"street": "Secret Street 1", "postal_code": "1000", "city": "Testby"}},
                {"queue_key": "dk.smiley:allowed", "source_id": "dk.smiley", "source_record_key": "allowed", "original_address": {"street": "Safe Street 2", "postal_code": "1000", "city": "Testby"}},
            ]) + "\n", encoding="utf-8")
            suppressions.write_text('{"source_id":"dk.smiley","source_record_key":"blocked"}\n', encoding="utf-8")
            original_fetch = MODULE.fetch
            calls = []
            try:
                MODULE.fetch = lambda params, base_url: (calls.append((params, base_url)) or (200, [{"x": 12.5, "y": 55.6}]))
                MODULE.run(queue, output, 2, 0, 1, config, suppressions, terms, True)
            finally:
                MODULE.fetch = original_fetch
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0][1], "https://example.invalid")
            self.assertEqual(len(output.read_text(encoding="utf-8").splitlines()), 1)
            report = (root / "geocode-review-report.json").read_text(encoding="utf-8")
            self.assertIn('"suppressed": 1', report)
            self.assertNotIn("Secret Street", report)
            self.assertNotIn("blocked", report)


if __name__ == "__main__":
    unittest.main()
