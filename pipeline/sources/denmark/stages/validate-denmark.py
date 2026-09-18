#!/usr/bin/env python3
"""Validate classified Denmark records without deleting invalid rows."""

import argparse
import collections
import json
import logging
from datetime import datetime
from pathlib import Path

LOGGER = logging.getLogger("uec.denmark.validate")


def validate_file(input_path: Path, output_dir: Path, expected_rows: int | None = None, progress_every: int = 10000) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "validation-report.json"
    quarantine_path = output_dir / "validation-findings.jsonl"
    counts = collections.Counter()
    seen_keys = set()
    findings = []
    total = 0
    LOGGER.info("stage=validate status=started input=%s", input_path)
    with input_path.open(encoding="utf-8") as source, quarantine_path.open("w", encoding="utf-8", newline="\n") as rejected:
        for line in source:
            if not line.strip():
                continue
            total += 1
            record = json.loads(line)
            key = record.get("source_record_key")
            row_findings = []
            if not key:
                row_findings.append(("error", "missing_source_record_key"))
            elif key in seen_keys:
                row_findings.append(("error", "duplicate_source_record_key"))
            else:
                seen_keys.add(key)
            address = record.get("address", {})
            if not record.get("name"):
                row_findings.append(("warning", "missing_name"))
            if not address.get("street") and not address.get("city") and not address.get("postal_code"):
                row_findings.append(("error", "missing_address"))
            if address.get("country_code") != "DK":
                row_findings.append(("error", "unexpected_country"))
            date_value = record.get("latest_inspection_date")
            if date_value:
                try:
                    datetime.strptime(date_value, "%Y-%m-%d")
                except ValueError:
                    row_findings.append(("error", "invalid_normalized_date"))
            classification = record.get("classification", {})
            if not classification.get("rule_id"):
                row_findings.append(("error", "missing_classification_rule"))
            if classification.get("review_status") == "review_required":
                row_findings.append(("review", "classification_requires_review"))
            coordinate_status = record.get("coordinates", {}).get("review_status")
            counts["coordinates_" + str(coordinate_status)] += 1
            if row_findings:
                finding = {"source_row": record.get("source_row"), "source_record_key": key, "findings": [{"severity": s, "code": c} for s, c in row_findings]}
                rejected.write(json.dumps({"record": record, "findings": finding["findings"]}, ensure_ascii=False, sort_keys=True) + "\n")
                findings.append(finding)
                for _, code in row_findings:
                    counts[code] += 1
            if total % progress_every == 0:
                LOGGER.info("stage=validate records=%d findings=%d", total, len(findings))
    if expected_rows is not None and total != expected_rows:
        counts["unexpected_row_count"] += 1
    report = {
        "status": "success",
        "input_path": input_path.as_posix(),
        "records_checked": total,
        "unique_source_record_keys": len(seen_keys),
        "finding_records": len(findings),
        "expected_rows": expected_rows,
        "counts": dict(counts),
        "findings_path": quarantine_path.as_posix(),
        "policy": "findings are reported and preserved; no records are deleted",
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    LOGGER.info("stage=validate status=success records=%d finding_records=%d report=%s", total, len(findings), report_path)
    return report_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--expected-rows", type=int)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%dT%H:%M:%SZ")
    validate_file(args.input, args.output_dir, args.expected_rows)
