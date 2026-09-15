"""Write a row-free V1/V2 crosswalk report for a private review run."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pipeline.reconciliation.crosswalk import compare_v1_v2


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("v1_path", type=Path)
    parser.add_argument("v2_path", type=Path)
    parser.add_argument("--v1-key", required=True)
    parser.add_argument("--v2-key", required=True)
    parser.add_argument("--country", required=True)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = compare_v1_v2(args.v1_path, args.v2_path, v1_key=args.v1_key, v2_key=args.v2_key,
                           v1_country=args.country, v2_source_id=args.source_id)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
