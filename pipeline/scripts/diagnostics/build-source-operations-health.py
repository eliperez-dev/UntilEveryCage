"""Build the private-alpha source operations health index."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pipeline.common.source_operations import SourceOperationsError, build_source_health_index


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--operations-root", type=Path, required=True, help="private root containing history/")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--as-of-utc", required=True, help="timezone-aware ISO-8601 timestamp")
    parser.add_argument("--schedules", type=Path)
    parser.add_argument("--registry", type=Path)
    args = parser.parse_args()
    try:
        index = build_source_health_index(
            args.operations_root, schedules_path=args.schedules, registry_path=args.registry,
            as_of_utc=args.as_of_utc,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(index, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    except (OSError, SourceOperationsError) as error:
        print(f"source-operations-health: {error}", file=sys.stderr)
        return 2
    print(f"source-operations-health: wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
