"""Emit a row-free aggregate inventory for every V1 locations.csv snapshot."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from pipeline.reconciliation.v1_inventory import DEFAULT_COUNTRIES, inventory_v1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--static-data", type=Path, default=Path("static_data"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    countries = []
    for code in DEFAULT_COUNTRIES:
        path = args.static_data / code / "locations.csv"
        item = {"country_code": code}
        if path.exists():
            item.update(inventory_v1(path))
        else:
            item.update({"comparison_status": "blocked_missing_v1_snapshot", "counts": None})
        countries.append(item)
    report = {"report_version": "v1-country-inventory-1", "countries": countries, "raw_rows_in_report": False}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
