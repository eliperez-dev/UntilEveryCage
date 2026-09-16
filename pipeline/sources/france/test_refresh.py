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


if __name__ == "__main__": unittest.main()
