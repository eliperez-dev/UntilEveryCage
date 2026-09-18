import json
import tempfile
import unittest
from pathlib import Path

from .refresh import refresh


ROOT = Path(__file__).parent


class AphisRefreshTests(unittest.TestCase):
    def test_private_handoff_and_import_are_emitted_without_graph_or_release(self):
        with tempfile.TemporaryDirectory() as directory:
            result = refresh(
                run_dir=Path(directory) / "refresh",
                raw_path=ROOT / "fixtures/annual_reports.csv",
                profile="annual_reports",
                retrieved_at_utc="2026-09-15T00:00:00Z",
            )
            self.assertEqual(result["status"], "candidate-ready")
            run = Path(result["run_dir"])
            handoff = json.loads((run / "candidate-handoff/manifest.json").read_text(encoding="utf-8"))
            imported = json.loads((run / "candidate-import/manifest.json").read_text(encoding="utf-8"))
            health = json.loads((run / "source-health.json").read_text(encoding="utf-8"))
            self.assertEqual(handoff["entity_scope"], "aphis_observation")
            self.assertFalse(handoff["graph_candidate_emission"])
            self.assertEqual(imported["imported_rows"], 1)
            self.assertFalse(imported["public_exposure"])
            self.assertEqual(imported["publication_eligible_rows"], 0)
            self.assertEqual(imported["graph_edges_created"], 0)
            self.assertEqual(health["import"]["state"], "completed")
            self.assertEqual(health["import"]["publication_eligible_rows"], 0)
            self.assertFalse((run / "candidate-handoff/graph-candidates").exists())


if __name__ == "__main__":
    unittest.main()
