"""Materialize a validated private graph handoff into a configured private DB.

Requires UEC_GRAPH_DATABASE_URL, UEC_GRAPH_DATABASE_NAME, and
UEC_GRAPH_DATABASE_PURPOSE=private-graph-materialization-v1. It never imports
evidence events, changes release membership, or changes privacy/approval state.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from pipeline.common.graph_persistence import (
    backfill_approved_graph_identifier_bindings,
)
from pipeline.common.real_private_graph import materialize_graph_corpus


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--handoff", type=Path, action="append", required=True,
                        help="private candidate handoff; repeat to stage all source handoffs together")
    parser.add_argument("--batch-size", type=int, default=250)
    parser.add_argument(
        "--backfill-approved-bindings-only", action="store_true",
        help="append exact native-ID/activity bindings and repair eligible inferred endpoint keys for a completed Italy import; do not rerun base writes or edge matching",
    )
    args = parser.parse_args()
    database_url = os.environ.get("UEC_GRAPH_DATABASE_URL", "")
    database_name = os.environ.get("UEC_GRAPH_DATABASE_NAME", "")
    purpose = os.environ.get("UEC_GRAPH_DATABASE_PURPOSE", "")
    if args.backfill_approved_bindings_only:
        try:
            results = [backfill_approved_graph_identifier_bindings(
                database_url, handoff, private_target=(database_name, purpose),
            ) for handoff in args.handoff]
        except Exception as error:
            # SQLSTATE is a bounded diagnostic useful for role/grant failures;
            # never emit exception text, which may contain private connection data.
            print(json.dumps({"status": "blocked", "error_type": type(error).__name__,
                              "sqlstate": getattr(error, "sqlstate", None)}, sort_keys=True))
            return 2
        print(json.dumps(results[0] if len(results) == 1 else {"status": "completed", "results": results}, sort_keys=True))
        return 0
    try:
        result = materialize_graph_corpus(
            database_url, args.handoff, private_target=(database_name, purpose),
            batch_size=args.batch_size,
        )
    except Exception as error:
        # Driver exceptions and validation messages can include local paths or
        # connection details. Emit only a safe failure category.
        print(json.dumps({"status": "blocked", "error_type": type(error).__name__,
                          "sqlstate": getattr(error, "sqlstate", None)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
