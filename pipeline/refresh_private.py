"""Run one or more registered source adapters through the private runner.

The framework intentionally ships without implicit source imports.  Source
packages can register hooks in a later onboarding change; until then a source
is reported as unsupported rather than guessed or silently executed.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Mapping

from pipeline.common.acquisition import default_run_id
from pipeline.common.refresh_runner import RefreshCatalog, RefreshRunner, RefreshRunnerError
from pipeline.contracts.refresh import RefreshRequest
from pipeline.common.graph_persistence import import_graph_candidates


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--source", action="append", dest="sources", help="source ID; repeat for selected runs")
    group.add_argument("--all-eligible", action="store_true", help="select all implemented/partial registry entries")
    parser.add_argument("--mode", choices=("fixture", "local-artifact", "live-acquisition"), default="fixture")
    parser.add_argument("--artifact", action="append", default=[], metavar="SOURCE=PATH", help="artifact mapping for fixture/local-artifact mode")
    parser.add_argument("--output-root", type=Path, default=Path("data/staging/private-refresh"))
    parser.add_argument("--retries", type=int, default=1)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--import-candidates", action="store_true", help="explicitly request candidate import into a loopback disposable DB")
    parser.add_argument("--database-url")
    parser.add_argument("--database-url-env", default="UEC_DATABASE_URL", help="environment variable for a disposable DB URL (default: UEC_DATABASE_URL)")
    parser.add_argument("--disposable-db", action="store_true", help="acknowledge the explicit disposable-database guard")
    parser.add_argument("--authorize-live-source", action="append", default=[], metavar="SOURCE", help="explicitly authorize live acquisition for one source")
    parser.add_argument("--terms-review", action="append", default=[], metavar="SOURCE=PATH", help="approved source-specific terms review JSON")
    parser.add_argument("--timeout-seconds", type=float, default=180)
    parser.add_argument("--max-bytes", type=int, default=128 * 1024 * 1024)
    parser.add_argument("--run-id", help="unique acquisition run ID; generated when omitted")
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


def _source_paths(values: list[str], option: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in values:
        source, separator, path = item.partition("=")
        if not separator or not source or not path:
            raise ValueError(f"{option} must be SOURCE=VALUE")
        if source in result:
            raise ValueError(f"duplicate {option} mapping: {source}")
        result[source] = path
    return result


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        terms_reviews = _source_paths(args.terms_review, "--terms-review")
        database_url = args.database_url
        if args.import_candidates:
            if not args.disposable_db:
                raise ValueError("--import-candidates requires the explicit --disposable-db acknowledgment")
            env_url = os.environ.get(args.database_url_env, "") if args.database_url_env else ""
            if database_url and env_url:
                raise ValueError("use --database-url or --database-url-env, not both")
            database_url = database_url or env_url or None
            if not database_url:
                raise ValueError("candidate import requires --database-url or a populated --database-url-env")
        options = {
            "authorized_live_sources": args.authorize_live_source,
            "terms_review_paths": terms_reviews,
            "timeout_seconds": args.timeout_seconds,
            "max_bytes": args.max_bytes,
            "acquisition_run_id": args.run_id or default_run_id(),
        }
        request = RefreshRequest(source_ids=tuple(args.sources or ()), all_eligible=args.all_eligible,
                                 mode=args.mode, artifact_paths=_artifacts(args.artifact), output_root=args.output_root,
                                 retries=args.retries, resume=args.resume, import_candidates=args.import_candidates,
                                 database_url=database_url, options=options)
        importer = lambda source_dir, url: import_graph_candidates(
            url, source_dir / "candidate-handoff", disposable_db=args.disposable_db)
        runner = RefreshRunner(RefreshCatalog(), candidate_importer=importer if args.import_candidates else None)
        result = runner.run(request)
    except (OSError, ValueError, RefreshRunnerError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, sort_keys=True))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["exit_status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())

