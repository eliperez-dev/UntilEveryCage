import json
import tempfile
import unittest
from pathlib import Path

from .refresh import refresh


class FranceRefreshTests(unittest.TestCase):
    def test_assisted_refresh_emits_candidate_handoff_and_review_packet(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); result = refresh(section="I", raw_path=Path(__file__).parent / "fixtures/section_i.csv", run_dir=root / "refresh", retrieved_at_utc="2026-09-15T00:00:00Z")
            self.assertEqual(result["report"]["lifecycle_status"], "candidate-ready")
            run = Path(result["report"]["run_dir"]); self.assertTrue((run / "candidate-handoff/manifest.json").exists()); self.assertTrue((run / "operator-review-packet.json").exists())
            packet = json.loads((run / "operator-review-packet.json").read_text()); self.assertFalse(packet["row_payloads_included"])

    def test_prior_run_is_linked_to_standard_delta_and_graph_handoff(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); source = Path(__file__).parent / "fixtures/section_i.csv"
            first = refresh(section="I", raw_path=source, run_dir=root / "first", retrieved_at_utc="2026-09-15T00:00:00Z")
            prior = Path(first["report"]["run_dir"]) / "normalized" / "records.jsonl"
            second = refresh(section="I", raw_path=source, run_dir=root / "second", retrieved_at_utc="2026-09-16T00:00:00Z", previous_normalized=prior)
            run = Path(second["report"]["run_dir"])
            packet = json.loads((run / "review-packet.json").read_text(encoding="utf-8"))
            self.assertEqual(packet["release_diff"]["status"], "delta-ready")
            self.assertEqual(packet["release_diff"]["counts"]["not_observed"], 0)
            graph = json.loads((run / "candidate-handoff/graph-candidates/manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(graph["candidate_rows"], 2)
            self.assertFalse(graph["publication_status"] == "eligible")


if __name__ == "__main__": unittest.main()
