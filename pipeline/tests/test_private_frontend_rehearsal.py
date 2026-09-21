import json
import tempfile
import unittest
from pathlib import Path

from pipeline.scripts.maintenance.rehearse_candidate_private_frontend import rehearse_candidate


class PrivateFrontendRehearsalTests(unittest.TestCase):
    def test_missing_private_handoff_is_not_counted_as_zero_and_report_is_row_free(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / "candidate.json"
            manifest.write_text(json.dumps({
                "publication": {"release_created": False, "release_promoted": False, "project_approval": "not-approved"},
                "sources": [{"source_id": "dk.smiley", "candidate_handoff_manifest": "private/missing.json", "normalized_rows": 12, "status": "candidate-ready; private only"}],
            }), encoding="utf-8")
            report = rehearse_candidate(manifest, root=root)
            self.assertEqual(report["status"], "passed")
            self.assertEqual(report["sources"][0]["handoff_state"], "unavailable-private-handoff")
            self.assertFalse(report["private_payloads_included"])
            self.assertNotIn("source_values", json.dumps(report))

    def test_private_preview_probe_requires_test_only_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / "candidate.json"
            manifest.write_text(json.dumps({
                "publication": {"release_created": False, "release_promoted": False, "project_approval": "not-approved"},
                "sources": [{"source_id": "dk.smiley", "status": "private only"}],
            }), encoding="utf-8")

            def response(_base_url, _token):
                return 200, {"meta": {"test_only": False, "private_preview": True}}

            with self.assertRaises(ValueError):
                rehearse_candidate(manifest, root=root, base_url="http://127.0.0.1", token="test", request=response)


if __name__ == "__main__":
    unittest.main()
