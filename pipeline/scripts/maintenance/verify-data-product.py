#!/usr/bin/env python3
"""Verify a packaged UEC public snapshot and its optional trusted digest."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from pipeline.common.data_product import DataProductError, verify_package


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package_dir", type=Path)
    parser.add_argument("--manifest-sha256", help="Trusted digest obtained from a project-controlled channel")
    args = parser.parse_args()
    try:
        result = verify_package(args.package_dir, args.manifest_sha256)
    except (DataProductError, OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "blocked", "error": str(error)}), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
