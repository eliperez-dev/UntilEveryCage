"""Run the D3 mixed private acquisition/readiness rehearsal."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from pipeline.common.d3_live_operations import build_mixed_rehearsal  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--mode", choices=("fixture", "local-artifact", "live-acquisition"), default="fixture")
    parser.add_argument("--as-of-utc", default="2026-01-01T00:00:00Z")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = build_mixed_rehearsal(run_root=args.run_root, mode=args.mode,
                                       as_of_utc=args.as_of_utc, resume=args.resume)
    except (OSError, ValueError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, sort_keys=True))
        return 2
    print(json.dumps({
        "status": result["exit_status"],
        "selected": result["selected_sources"],
        "counts": result["counts"],
        "report": str(args.run_root / "d3-live-operations-report.json"),
    }, sort_keys=True))
    return 0 if result["exit_status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
