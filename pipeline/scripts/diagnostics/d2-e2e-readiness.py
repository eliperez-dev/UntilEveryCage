"""Run the private, row-free D2 disposable E2E readiness contract."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from pipeline.common.d2_e2e_readiness import (  # noqa: E402
    D2ReadinessError,
    D2_SOURCE_IDS,
    build_report,
    write_report,
)
from pipeline.common.d2_postgres_sink import make_disposable_postgis_sink  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sources", help="comma-separated source IDs; defaults to all eligible")
    parser.add_argument("--all-eligible", action="store_true", help="run all seven eligible sources")
    parser.add_argument("--resume", type=Path, help="row-free report from an earlier run")
    parser.add_argument("--fail-source", choices=D2_SOURCE_IDS, help="inject a fixture failure for contract testing")
    parser.add_argument("--database-url", help="explicit disposable Postgres/PostGIS URL; never points at a public DB")
    args = parser.parse_args(argv)
    if args.sources and args.all_eligible:
        parser.error("use either --sources or --all-eligible, not both")
    selected = None if args.all_eligible or not args.sources else [item.strip() for item in args.sources.split(",") if item.strip()]
    try:
        resume = json.loads(args.resume.read_text(encoding="utf-8")) if args.resume else None
        sink = make_disposable_postgis_sink(args.database_url) if args.database_url else None
        report = build_report(selected_sources=selected, fail_source=args.fail_source, resume_report=resume, database_sink=sink)
        write_report(args.output, report)
    except (D2ReadinessError, OSError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"d2-e2e-readiness: {exc}", file=sys.stderr)
        return 2
    aggregate = report["aggregate"]
    print(f"d2-e2e-readiness: {aggregate['passed_sources']} passed, {aggregate['failed_sources']} failed; wrote {args.output}")
    return int(aggregate["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
