import json
from pathlib import Path

from pipeline.scripts.diagnostics.real_corpus_report import build_report


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
