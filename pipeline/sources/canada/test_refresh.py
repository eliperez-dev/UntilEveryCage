import json
import tempfile
import unittest
from pathlib import Path

from .refresh import refresh


class CanadaRefreshTests(unittest.TestCase):
    def test_assisted_refresh_emits_separate_private_candidates(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); results = []
            for source, fixture in (("ontario", "ontario.csv"), ("cfia", "cfia.csv")):
                result = refresh(source=source, raw_path=Path(__file__).parent / "fixtures" / fixture, run_dir=root / source, retrieved_at_utc="2026-09-15T00:00:00Z"); results.append(result)
                self.assertEqual(result["report"]["lifecycle_status"], "candidate-ready")
                run = Path(result["report"]["run_dir"]); self.assertTrue((run / "candidate-handoff/manifest.json").exists()); self.assertTrue((run / "operator-review-packet.json").exists())
            self.assertEqual({item["report"]["source_id"] for item in results}, {"ca.ontario.meat-plants", "ca.cfia.federal-meat"})
            self.assertFalse(json.loads((Path(results[0]["report"]["run_dir"]) / "operator-review-packet.json").read_text())["row_payloads_included"])


if __name__ == "__main__": unittest.main()
