#!/usr/bin/env python3
"""Apply an explicit, visibility-aware Denmark classification ruleset."""

import argparse
import collections
import json
import logging
from pathlib import Path

LOGGER = logging.getLogger("uec.denmark.classify")


def load_rules(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def classify_record(record: dict, ruleset: dict) -> dict:
    code = record.get("activity", {}).get("code")
    decision = ruleset["fallback"]
    for rule in ruleset["rules"]:
        if code in rule["codes"]:
            decision = rule
            break
    result = dict(record)
    result["classification"] = {
        "ruleset_id": ruleset["ruleset_id"],
        "rule_id": decision["rule_id"],
        "category": decision["classification"],
        "review_status": decision["review_status"],
        "default_visible": decision["default_visible"],
        "optional_filter": decision.get("optional_filter"),
    }
    return result


def classify_file(input_path: Path, rules_path: Path, output_dir: Path, progress_every: int = 10000) -> Path:
    ruleset = load_rules(rules_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "classified-records.jsonl"
    report_path = output_dir / "classification-report.json"
    counts = collections.Counter()
    LOGGER.info("stage=classify status=started input=%s ruleset=%s", input_path, ruleset["ruleset_id"])
    with input_path.open(encoding="utf-8") as source, output_path.open("w", encoding="utf-8", newline="\n") as output:
        for count, line in enumerate(source, start=1):
            if not line.strip():
                continue
            record = classify_record(json.loads(line), ruleset)
            classification = record["classification"]
            counts.update([classification["category"], classification["review_status"]])
            output.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            if count % progress_every == 0:
                LOGGER.info("stage=classify records=%d", count)
    report = {
        "status": "success",
        "ruleset_id": ruleset["ruleset_id"],
        "input_path": input_path.as_posix(),
        "output_path": output_path.as_posix(),
        "records_classified": sum(counts[key] for key in set(counts) if key in {r["classification"] for r in ruleset["rules"]} | {ruleset["fallback"]["classification"]}),
        "counts_by_classification": {key: value for key, value in counts.items() if key not in {"approved", "review_required"}},
        "counts_by_review_status": {key: value for key, value in counts.items() if key in {"approved", "review_required"}},
        "ruleset_path": rules_path.as_posix(),
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    LOGGER.info("stage=classify status=success records=%d report=%s", report["records_classified"], report_path)
    return output_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--rules", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%dT%H:%M:%SZ")
    classify_file(args.input, args.rules, args.output_dir)
