#!/usr/bin/env python3
"""Inspect the Danish Find Smiley XML without transforming or mutating it."""

import argparse
import collections
import json
import xml.etree.ElementTree as ET
from pathlib import Path


def inspect(path: Path) -> dict:
    row_count = 0
    missing_coordinates = 0
    fields = collections.Counter()
    business_types = collections.Counter()
    industry_codes = collections.Counter()
    categories = collections.Counter()
    ids = collections.Counter()

    for event, element in ET.iterparse(path, events=("end",)):
        if element.tag != "row":
            continue
        row_count += 1
        values = {child.tag: (child.text or "").strip() for child in element}
        fields.update(values)
        business_types[values.get("virksomhedstype", "")] += 1
        industry_codes[values.get("brancheKode", "")] += 1
        categories[values.get("Pixibranche", "")] += 1
        for key in ("navnelbnr", "cvrnr", "pnr"):
            value = values.get(key, "")
            if value:
                ids[key] += 1
        if not values.get("Geo_Lat") or not values.get("Geo_Lng"):
            missing_coordinates += 1
        element.clear()

    return {
        "path": path.as_posix(),
        "rows": row_count,
        "missing_coordinates": missing_coordinates,
        "fields": sorted(fields),
        "identifier_presence": dict(ids),
        "business_types": business_types.most_common(),
        "industry_codes": industry_codes.most_common(20),
        "categories": categories.most_common(20),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    print(json.dumps(inspect(args.path), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
