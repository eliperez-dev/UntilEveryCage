#!/usr/bin/env python3
"""Validate a candidate release before it can become a publishable release."""

import argparse
import html
import json
import os
import sys
from pathlib import Path

import psycopg


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
        metrics = connection.execute("""
            SELECT
                count(*)::int AS release_records,
                count(DISTINCT release_member.observation_id)::int AS distinct_observations,
                (count(*) - count(DISTINCT release_member.observation_id))::int AS duplicate_observations,
                count(*) FILTER (WHERE observation.classification_review_status <> 'approved' AND release_member.default_visible)::int AS review_visible,
                count(*) FILTER (WHERE release_member.default_visible AND latest.status = 'accepted' AND latest.result IS NOT NULL)::int AS exact_display_ready,
                count(*) FILTER (WHERE release_member.default_visible AND latest.status = 'review_required' AND city.reference_location IS NOT NULL)::int AS city_display_ready,
                count(*) FILTER (WHERE release_member.default_visible AND (latest.status IS NULL OR (latest.status <> 'accepted' AND city.reference_location IS NULL)))::int AS unmapped_display,
                count(*) FILTER (WHERE release_member.default_visible AND (latest.status <> 'accepted' OR latest.result IS NULL))::int AS coordinate_not_ready,
                count(*) FILTER (WHERE review.release_id IS NULL OR review.publication_eligible IS DISTINCT FROM true OR review.privacy_screening_status IS DISTINCT FROM 'passed' OR review.maintainer_approval IS DISTINCT FROM 'approved')::int AS publication_not_approved,
                count(*) FILTER (WHERE restricted.source_record_id IS NOT NULL)::int AS active_suppression,
                count(*) FILTER (WHERE release_member.default_visible AND (release.summary->'demonstration' IS NOT NULL AND release.summary->'demonstration'->>'rights_status' IS DISTINCT FROM 'cleared'))::int AS rights_not_cleared,
                (SELECT count(*)::int FROM uec.validation_findings finding WHERE finding.severity = 'error' AND (finding.source_record_id IS NULL OR finding.source_record_id IN (SELECT source_record_id FROM uec.observations WHERE observation_id IN (SELECT observation_id FROM uec.release_members WHERE release_id = %s)))) AS validation_errors
            FROM uec.release_members AS release_member
            JOIN uec.releases AS release ON release.release_id = release_member.release_id
            JOIN uec.observations AS observation ON observation.observation_id = release_member.observation_id
            JOIN uec.facilities AS facility ON facility.facility_id = release_member.facility_id
            LEFT JOIN LATERAL (SELECT status, result FROM uec.geocode_results WHERE source_record_id = observation.source_record_id ORDER BY queried_at DESC, geocode_result_id DESC LIMIT 1) AS latest ON true
            LEFT JOIN LATERAL (SELECT reference_location FROM uec.city_reference_points WHERE country_code = facility.country_code AND lower(city_name) = lower(facility.city) AND (postal_code IS NULL OR postal_code = facility.postal_code) LIMIT 1) AS city ON true
            LEFT JOIN uec.publication_review_release_current review
              ON review.source_record_id = observation.source_record_id
             AND review.release_id = release_member.release_id
            LEFT JOIN uec.public_access_restricted restricted ON restricted.source_record_id = observation.source_record_id
            WHERE release_member.release_id = %s
        """, (release_id, release_id)).fetchone()
        names = ["release_records", "distinct_observations", "duplicate_observations", "review_visible", "exact_display_ready", "city_display_ready", "unmapped_display", "coordinate_not_ready", "publication_not_approved", "active_suppression", "rights_not_cleared", "validation_errors"]
        metrics_dict = dict(zip(names, metrics)); metrics_dict["test_only"] = bool(release[1])
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
