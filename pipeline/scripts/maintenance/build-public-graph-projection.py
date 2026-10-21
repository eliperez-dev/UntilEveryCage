#!/usr/bin/env python3
"""Build the indexed graph read model for one already-eligible release.

Requires the normal private graph target environment. This command creates no
release, approval, rights, review, or privacy decisions.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.common.graph_projection import build_release_projection  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--batch-size", type=int, default=500)
    args = parser.parse_args(argv)
    database_url = os.environ.get("UEC_GRAPH_DATABASE_URL", "")
    database_name = os.environ.get("UEC_GRAPH_DATABASE_NAME", "")
    purpose = os.environ.get("UEC_GRAPH_DATABASE_PURPOSE", "")
    try:
        result = build_release_projection(
            database_url, args.release_id,
            private_target=(database_name, purpose), batch_size=args.batch_size,
        )
    except Exception as error:
        print(json.dumps({"status": "blocked", "error_type": type(error).__name__,
                          "sqlstate": getattr(error, "sqlstate", None)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
