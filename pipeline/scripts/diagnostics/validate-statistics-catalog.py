#!/usr/bin/env python3
"""Validate a versioned aggregate-statistics catalog without publishing it."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[3]))

from pipeline.statistics.catalog import StatisticsCatalogError, load_catalog, validate_catalog


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalog", type=Path)
    args = parser.parse_args()
    try:
        catalog = load_catalog(args.catalog)
        report = validate_catalog(catalog)
    except StatisticsCatalogError as error:
        print(json.dumps({"status": "blocked", "error": str(error)}, indent=2))
        return 1
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
