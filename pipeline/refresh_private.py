"""Run one or more registered source adapters through the private runner.

The framework intentionally ships without implicit source imports.  Source
packages can register hooks in a later onboarding change; until then a source
is reported as unsupported rather than guessed or silently executed.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from pipeline.common.refresh_runner import RefreshCatalog, RefreshRunner, RefreshRunnerError
from pipeline.contracts.refresh import RefreshRequest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--source", action="append", dest="sources", help="source ID; repeat for selected runs")
    group.add_argument("--all-eligible", action="store_true", help="select all implemented/partial registry entries")
    parser.add_argument("--mode", choices=("fixture", "local-artifact", "live-acquisition"), default="fixture")
    parser.add_argument("--artifact", action="append", default=[], metavar="SOURCE=PATH", help="artifact mapping for fixture/local-artifact mode")
    parser.add_argument("--output-root", type=Path, default=Path("data/staging/private-refresh"))
    parser.add_argument("--retries", type=int, default=0)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--import-candidates", action="store_true", help="explicitly request candidate import into a loopback disposable DB")
    parser.add_argument("--database-url")
    return parser


def _artifacts(values: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in values:
        source, separator, path = item.partition("=")
        if not separator or not source or not path:
            raise ValueError("--artifact must be SOURCE=PATH")
        if source in result:
            raise ValueError(f"duplicate artifact mapping: {source}")
        result[source] = path
    return result


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        request = RefreshRequest(source_ids=tuple(args.sources or ()), all_eligible=args.all_eligible,
                                 mode=args.mode, artifact_paths=_artifacts(args.artifact), output_root=args.output_root,
                                 retries=args.retries, resume=args.resume, import_candidates=args.import_candidates,
                                 database_url=args.database_url)
        result = RefreshRunner(RefreshCatalog()).run(request)
    except (OSError, ValueError, RefreshRunnerError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, sort_keys=True))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["exit_status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())

