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
    completed_edge_materialization,
    import_graph_candidates,
)
from pipeline.common.real_private_graph import GRAPH_MATERIALIZATION_FINGERPRINT, _MatcherStage


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--handoff", type=Path, required=True)
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
            result = backfill_approved_graph_identifier_bindings(
                database_url, args.handoff,
                private_target=(database_name, purpose),
            )
        except Exception as error:
            # SQLSTATE is a bounded diagnostic useful for role/grant failures;
            # never emit exception text, which may contain private connection data.
            print(json.dumps({"status": "blocked", "error_type": type(error).__name__,
                              "sqlstate": getattr(error, "sqlstate", None)}, sort_keys=True))
            return 2
        print(json.dumps(result, sort_keys=True))
        return 0
    try:
        completed = completed_edge_materialization(
            database_url, args.handoff, private_target=(database_name, purpose),
            fingerprint=GRAPH_MATERIALIZATION_FINGERPRINT,
        )
    except Exception as error:
        print(json.dumps({"status": "blocked", "error_type": type(error).__name__,
                          "sqlstate": getattr(error, "sqlstate", None)}, sort_keys=True))
        return 2
    if completed is not None:
        print(json.dumps({**completed, "materialization_fingerprint": GRAPH_MATERIALIZATION_FINGERPRINT}, sort_keys=True))
        return 0
    matcher = None
    try:
        matcher = _MatcherStage()
        matcher.add_handoff(args.handoff)
        matcher_summary = matcher.build_candidates()
        result = import_graph_candidates(
            database_url, args.handoff, batch_size=args.batch_size,
            private_target=(database_name, purpose),
            edge_builder=matcher.edge_builder,
            materialization_fingerprint=GRAPH_MATERIALIZATION_FINGERPRINT,
            matcher_summary=matcher_summary,
        )
    except Exception as error:
        # Driver exceptions and validation messages can include local paths or
        # connection details. Emit only a safe failure category.
        print(json.dumps({"status": "blocked", "error_type": type(error).__name__,
                          "sqlstate": getattr(error, "sqlstate", None)}, sort_keys=True))
        return 2
    finally:
        if matcher is not None:
            matcher.close()
    result["matcher"] = matcher_summary
    result["edge_counts_by_type"] = result.pop("persisted_edge_counts", None)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
