import json
import unittest
from pathlib import Path

from pipeline.scripts.diagnostics.real_corpus_report import build_report, canonical_bytes


def test_report_is_honest_about_metadata_only_sources(tmp_path: Path):
    (tmp_path / "manifest.json").write_text(json.dumps({"country": "XX", "artifacts": [
        {"source_id": "xx.rows", "rows": 12, "capture_status": "row_artifact"},
        {"source_id": "xx.route", "rows": None, "capture_status": "route_only"},
    ]}))
    report = build_report(tmp_path)
    assert report["known_input_rows"] == 12
    assert report["artifact_entries"] == 2
    assert report["target_assessment"]["met"] is False
    assert report["capture_states"] == {"route_only": 1, "row_artifact": 1}


def test_missing_manifest_root_is_empty_not_success(tmp_path: Path):
    report = build_report(tmp_path / "missing")
    assert report["known_input_rows"] == 0
    assert report["target_assessment"]["met"] is False


class RealCorpusReportTests(unittest.TestCase):
    def test_unknown_counts_are_not_reported_as_zero(self):
        report = build_report(Path(__file__).parents[2] / "data" / "manifests")
        self.assertGreater(report["manifest_files"], 0)
        self.assertGreater(report["capture_states"].get("metadata_only", 0), 0)
        self.assertIn("not available", report["strata"]["category"])
        self.assertFalse(report["target_assessment"]["met"])

    def test_canonical_bytes_are_stable(self):
        report = build_report(Path(__file__).parents[2] / "data" / "manifests")
        self.assertEqual(canonical_bytes(report), canonical_bytes(report))
        self.assertTrue(canonical_bytes(report).endswith(b"\n"))


if __name__ == "__main__":
    unittest.main()
