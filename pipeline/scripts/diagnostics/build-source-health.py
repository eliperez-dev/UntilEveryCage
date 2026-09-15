"""Build a private, row-free country health snapshot from one run directory."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pipeline.contracts.source_health import HealthEvidenceError, build_health_snapshot, write_health_snapshot


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--as-of-utc", required=True, help="timezone-aware ISO-8601 timestamp for deterministic freshness")
    parser.add_argument("--stale-after-hours", type=int, default=24 * 7)
    parser.add_argument("--import-evidence", type=Path)
    args = parser.parse_args(argv)
    try:
        snapshot = build_health_snapshot(
            args.run_dir,
            as_of_utc=args.as_of_utc,
            stale_after_hours=args.stale_after_hours,
            import_evidence_path=args.import_evidence,
        )
        write_health_snapshot(args.output, snapshot)
    except (HealthEvidenceError, OSError) as exc:
        print(f"source-health: {exc}", file=sys.stderr)
        return 2
    print(f"source-health: wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
