#!/usr/bin/env python3
"""Apply an explicit, visibility-aware Denmark classification ruleset."""

import argparse
import collections
import json
import logging
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from pipeline.sources.denmark.location import classify_location, load_local_references

LOGGER = logging.getLogger("uec.denmark.classify")


def load_rules(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def classify_record(record: dict, ruleset: dict, location_references: list[dict] | None = None) -> dict:
    source_activity = record.get("activity", {})
    code = source_activity.get("codes") or source_activity.get("code")
    codes = code if isinstance(code, (list, tuple)) else [code]
    codes = [str(value).strip() for value in codes if value is not None and str(value).strip()]
    decisions = []
    for source_code in codes:
        decision = next((rule for rule in ruleset["rules"] if source_code in rule["codes"]), ruleset["fallback"])
        if decision is not ruleset["fallback"]:
            decisions.append(decision)
    # Keep all recognized activities in source-code order. The singular display
    # category is selected by the documented ruleset order, independent of XML
    # field order; unsupported values remain visible in source_classification_*.
    unique_decisions = {decision["classification"]: decision for decision in decisions}
    primary = next((rule for rule in ruleset["rules"] if rule["classification"] in unique_decisions), None)
    decision = primary or ruleset["fallback"]
    categories = [rule["classification"] for rule in ruleset["rules"]
                  if rule["classification"] in unique_decisions]
    geocode_categories = set((ruleset.get("private_geocode_scope") or {}).get("activity_categories", ()))
    source_scope_eligible = bool(geocode_categories.intersection(categories))
    mapping_status = "unmapped" if not categories else (
        "partial" if len(decisions) != len(codes) else "mapped")
    result = dict(record)
    result["classification"] = {
        "ruleset_id": ruleset["ruleset_id"],
        "rule_id": decision["rule_id"],
        "category": decision["classification"] if categories else None,
        "activity_categories": categories,
        "mapping_status": mapping_status,
        "review_status": decision["review_status"],
        "default_visible": decision["default_visible"],
        "optional_filter": decision.get("optional_filter"),
        "private_geocode_scope": "animal_product_production_and_processing" if source_scope_eligible else "out_of_scope",
        "private_geocode_scope_policy_id": (ruleset.get("private_geocode_scope") or {}).get("policy_id"),
    }
    result["source_classification"] = {
        "codes": codes,
        "labels": list(source_activity.get("labels") or ([source_activity.get("label")] if source_activity.get("label") else [])),
        "category_label": source_activity.get("category"),
        "category_labels": list(source_activity.get("category_labels") or ([source_activity.get("category")] if source_activity.get("category") else [])),
    }
    result["location"] = classify_location(
        result,
        location_references,
        privacy_status="eligible" if source_scope_eligible else "pending",
        source_scope_eligible=source_scope_eligible,
    )
    return result


def classify_file(input_path: Path, rules_path: Path, output_dir: Path, progress_every: int = 10000,
                  location_references_path: Path | None = None) -> Path:
    ruleset = load_rules(rules_path)
    location_references = load_local_references(location_references_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "classified-records.jsonl"
    report_path = output_dir / "classification-report.json"
    counts = collections.Counter()
    LOGGER.info("stage=classify status=started input=%s ruleset=%s", input_path, ruleset["ruleset_id"])
    with input_path.open(encoding="utf-8") as source, output_path.open("w", encoding="utf-8", newline="\n") as output:
        for count, line in enumerate(source, start=1):
            if not line.strip():
                continue
            record = classify_record(json.loads(line), ruleset, location_references)
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
    parser.add_argument("--location-references", type=Path,
                        help="Previously acquired local Denmark locality/postal reference JSONL; never fetched here.")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%dT%H:%M:%SZ")
    classify_file(args.input, args.rules, args.output_dir, location_references_path=args.location_references)
