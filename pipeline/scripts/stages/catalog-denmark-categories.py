#!/usr/bin/env python3
"""Build a complete category catalog from normalized Denmark staging data."""

import argparse
import collections
import json
from pathlib import Path


def build_catalog(input_path: Path, output_path: Path) -> None:
    categories = collections.defaultdict(lambda: {"count": 0, "examples": []})
    with input_path.open(encoding="utf-8") as source:
        for line in source:
            if not line.strip():
                continue
            record = json.loads(line)
            activity = record["activity"]
            key = (
                activity.get("code"),
                activity.get("label"),
                activity.get("category"),
            )
            item = categories[key]
            item["count"] += 1
            if len(item["examples"]) < 3:
                item["examples"].append({
                    "source_record_key": record.get("source_record_key"),
                    "name": record.get("name"),
                    "source_url": record.get("source_url"),
                })

    rows = [
        {"industry_code": key[0], "industry_label": key[1], "category_label": key[2], **value}
        for key, value in categories.items()
    ]
    rows.sort(key=lambda row: (-row["count"], row["industry_code"] or "", row["category_label"] or ""))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps({"status": "success", "categories": rows}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Catalogued {len(rows)} distinct category combinations from {sum(row['count'] for row in rows)} records")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    build_catalog(args.input, args.output)
