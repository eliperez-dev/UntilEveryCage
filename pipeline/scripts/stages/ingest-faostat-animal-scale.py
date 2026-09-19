#!/usr/bin/env python3
"""Ingest the selected FAOSTAT land-animal rows into a validated private catalog."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[3]))

from pipeline.statistics.faostat import build_entry


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_csv", type=Path)
    parser.add_argument("output_catalog", type=Path)
    parser.add_argument("--artifact-path", required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--byte-size", required=True, type=int)
    parser.add_argument("--retrieved-at-utc", required=True)
    args = parser.parse_args()
    with args.input_csv.open(newline="", encoding="utf-8-sig") as handle:
        entry = build_entry(
            csv.DictReader(handle),
            artifact_path=args.artifact_path,
            sha256=args.sha256,
            byte_size=args.byte_size,
            retrieved_at_utc=args.retrieved_at_utc,
        )
    catalog = {"schema_version": "aggregate-statistics-catalog-v1", "catalog_id": "animal-scale-2024-edition", "catalog_version": "1.0.0", "publication_state": "private-validated", "statistics": [entry]}
    args.output_catalog.parent.mkdir(parents=True, exist_ok=True)
    args.output_catalog.write_text(json.dumps(catalog, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "passed", "statistic_id": entry["statistic_id"], "central": entry["estimate"]["central"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
