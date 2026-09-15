import json
import tempfile
import unittest
from pathlib import Path

from .refresh import refresh_scotland


FIXTURE = Path(__file__).parent / "fixtures" / "valid.csv"


class FssRefreshTests(unittest.TestCase):
    def test_shared_lifecycle_emits_health_and_not_observed_semantics(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = root / "previous.jsonl"
            previous.write_text(json.dumps({"normalized": {"approval_number": "001234"}}) + "\n" + json.dumps({"normalized": {"approval_number": "missing"}}) + "\n", encoding="utf-8")
            result = refresh_scotland(
                raw_path=FIXTURE, run_dir=root / "run", retrieved_at_utc="2026-09-14T00:00:00Z",
                effective_date="2026-09-01", mode="handoff", previous_normalized=previous,
            )
            report = result["report"]
            self.assertEqual(report["coverage_counts"], {"Scotland": 2})
            self.assertEqual(report["disappeared_not_observed_count"], 1)
            self.assertIn("not-observed", report["disappearance_semantics"])
            health_path = Path(report["health_path"])
            health = json.loads(health_path.read_text(encoding="utf-8"))
            self.assertEqual(health["health_state"], "private-validated")
            self.assertFalse(health["public_exposure"])
            self.assertEqual(result["handoff"]["release_state"], "not-created")

    def test_handoff_keeps_quarantine_and_source_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = refresh_scotland(raw_path=Path(__file__).parent / "fixtures" / "quarantine.csv", run_dir=root / "run", retrieved_at_utc="2026-09-14T00:00:00Z", mode="handoff")
            self.assertEqual(result["report"]["normalized_rows"], 0)
            self.assertEqual(result["report"]["quarantined_rows"], 4)
            self.assertEqual(result["handoff"]["normalized_rows"], 0)


if __name__ == "__main__":
    unittest.main()
