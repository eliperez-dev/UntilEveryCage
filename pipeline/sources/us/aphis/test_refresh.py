import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline import refresh_private
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

    def test_shared_cli_wires_evidence_sink_only_for_explicit_disposable_import(self):
        observed = {}

        class RecordingRunner:
            def __init__(self, _catalog, **kwargs):
                observed.update(kwargs)

            def run(self, _request):
                return {"exit_status": "ok"}

        def evidence_sink(url, handoff, *, disposable_db):
            observed["sink_call"] = (url, handoff, disposable_db)
            return {"status": "completed"}

        arguments = [
            "--source", "us.aphis.annual-reports",
            "--mode", "fixture",
            "--import-candidates",
            "--disposable-db",
            "--database-url", "postgresql://127.0.0.1:55433/uec_v0_api_repair",
        ]
        with patch.object(refresh_private, "RefreshRunner", RecordingRunner), patch.object(
            refresh_private, "import_evidence_events", evidence_sink
        ):
            self.assertEqual(refresh_private.main(arguments), 0)
            importer = observed.get("evidence_importer")
            self.assertTrue(callable(importer))
            handoff = Path("private-evidence-handoff")
            url = "postgresql://127.0.0.1:55433/uec_v0_api_repair"
            importer(handoff, url)
            self.assertEqual(observed["sink_call"], (url, handoff, True))

        observed.clear()
        with patch.object(refresh_private, "RefreshRunner", RecordingRunner):
            self.assertEqual(refresh_private.main([
                "--source", "us.aphis.annual-reports", "--mode", "fixture"
            ]), 0)
        self.assertIsNone(observed.get("evidence_importer"))


if __name__ == "__main__":
    unittest.main()
