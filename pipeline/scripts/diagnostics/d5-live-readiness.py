"""Produce the D5 no-network acquisition readiness report."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from pipeline.common.d5_live_readiness import REPORT_AS_OF, build_readiness_report, write_readiness_report  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=Path("pipeline/source_registry.json"))
    parser.add_argument("--schedules", type=Path, default=Path("pipeline/source_operations.json"))
    parser.add_argument("--as-of-utc", default=REPORT_AS_OF)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = build_readiness_report(registry_path=args.registry, schedules_path=args.schedules, as_of_utc=args.as_of_utc)
        write_readiness_report(args.output, report)
    except (OSError, ValueError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, sort_keys=True))
        return 2
    print(json.dumps({
        "status": "ok",
        "report": str(args.output),
        "source_count": report["scope"]["source_count"],
        "classification_counts": report["classification_counts"],
        "network_requests": 0,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
