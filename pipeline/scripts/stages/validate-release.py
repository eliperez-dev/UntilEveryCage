#!/usr/bin/env python3
"""Validate a candidate release before it can become a publishable release."""

import argparse
import html
import json
import os
import sys
from pathlib import Path

import psycopg

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from pipeline.common.source_rights import evaluate as evaluate_source_rights
from pipeline.common.release_geometry import RELEASE_GATE_METRICS_SQL


def evaluate(metrics: dict, expected_records: int | None = None) -> dict:
    findings = []
    if expected_records is not None and metrics["release_records"] != expected_records:
        findings.append({"code": "record_count_mismatch", "expected": expected_records, "actual": metrics["release_records"]})
    if metrics["duplicate_observations"]:
        findings.append({"code": "duplicate_release_observations", "count": metrics["duplicate_observations"]})
    if metrics["validation_errors"]:
        findings.append({"code": "validation_errors", "count": metrics["validation_errors"]})
    if metrics["review_visible"]:
        findings.append({"code": "review_required_visible", "count": metrics["review_visible"]})
    if metrics.get("visible_records", metrics.get("release_records", 0)) == 0:
        findings.append({"code": "no_public_eligible_records", "count": 1})
    if metrics.get("coordinate_not_ready"):
        findings.append({"code": "coordinate_not_ready", "count": metrics["coordinate_not_ready"]})
    if metrics.get("publication_not_approved"):
        findings.append({"code": "publication_not_approved", "count": metrics["publication_not_approved"]})
    if metrics.get("active_suppression"):
        findings.append({"code": "active_suppression", "count": metrics["active_suppression"]})
    if metrics.get("rights_not_cleared"):
        findings.append({"code": "demonstration_rights_not_cleared", "count": metrics["rights_not_cleared"]})
    if metrics.get("test_only"):
        findings.append({"code": "test_only_release", "count": 1})
    return {"status": "passed" if not findings else "blocked", "findings": findings, "metrics": metrics}


def render_html(report: dict) -> str:
    status = html.escape(report["status"].upper())
    metrics = "".join(f"<tr><th>{html.escape(str(key))}</th><td>{html.escape(str(value))}</td></tr>" for key, value in report["metrics"].items())
    findings = "".join(f"<li>{html.escape(json.dumps(finding, ensure_ascii=False))}</li>" for finding in report["findings"]) or "<li>None</li>"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Release review {html.escape(report['release_id'])}</title>
<style>body{{font:16px system-ui;max-width:850px;margin:2rem auto;padding:0 1rem}}.status{{font-weight:700}}table{{border-collapse:collapse}}th,td{{text-align:left;border:1px solid #ccc;padding:.4rem .7rem}}</style></head>
<body><h1>Release review</h1><p>Release: <code>{html.escape(report['release_id'])}</code></p>
<p class="status">Result: {status}</p><h2>Metrics</h2><table>{metrics}</table>
<h2>Findings</h2><ul>{findings}</ul><p>Validation does not promote a release. Promotion remains a separate explicit action.</p></body></html>
"""


def validate(database_url: str, release_id: str, expected_records: int | None, mark_validated: bool) -> dict:
    with psycopg.connect(database_url) as connection:
        release = connection.execute("SELECT status, test_only FROM uec.releases WHERE release_id = %s", (release_id,)).fetchone()
        if not release:
            raise ValueError(f"release not found: {release_id}")
        metrics = connection.execute(RELEASE_GATE_METRICS_SQL,
                                     (release_id, release_id, release_id)).fetchone()
        names = ["release_records", "visible_records", "distinct_observations", "duplicate_observations",
                 "review_visible", "exact_display_ready", "source_reported_display_ready", "coarse_display_ready",
                 "unmapped_display", "coordinate_not_ready", "publication_not_approved", "active_suppression",
                 "demonstration_rights_not_cleared", "validation_errors"]
        metrics_dict = dict(zip(names, metrics))
        rights_gate = evaluate_source_rights(connection, release_id)
        metrics_dict["rights_not_cleared"] = len(rights_gate["blockers"]) + metrics_dict.pop("demonstration_rights_not_cleared")
        metrics_dict["rights_gate"] = rights_gate["status"]
        metrics_dict["rights_requirements"] = len(rights_gate["requirements"])
        metrics_dict["test_only"] = bool(release[1])
        result = evaluate(metrics_dict, expected_records)
        result.update({"release_id": release_id, "release_status_before": release[0], "marked_validated": False})
        if result["status"] == "passed" and mark_validated:
            connection.execute("UPDATE uec.releases SET status = 'validated' WHERE release_id = %s AND status = 'candidate'", (release_id,))
            result["marked_validated"] = True
            result["release_status_after"] = "validated"
        else:
            result["release_status_after"] = release[0]
        return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("release_id")
    parser.add_argument("--expected-records", type=int)
    parser.add_argument("--mark-validated", action="store_true", help="Change a passing candidate release to validated")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--html-output", type=Path)
    parser.add_argument("--database-url", default=os.environ.get("UEC_DATABASE_URL", "postgresql://uec:uec-local-development-only@localhost:5433/uec"))
    args = parser.parse_args()
    try:
        report = validate(args.database_url, args.release_id, args.expected_records, args.mark_validated)
    except Exception as error:
        print(json.dumps({"status": "error", "error": str(error)}, indent=2), file=sys.stderr)
        sys.exit(2)
    serialized = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    print(serialized, end="")
    if args.output:
        args.output.write_text(serialized, encoding="utf-8")
    if args.html_output:
        args.html_output.write_text(render_html(report), encoding="utf-8")
    sys.exit(0 if report["status"] == "passed" else 1)
