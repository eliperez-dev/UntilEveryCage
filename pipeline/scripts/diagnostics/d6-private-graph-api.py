"""Run the D6 private graph API contract against authorized local handoffs.

Only compact observations are retained in memory and the output is aggregate
only.  The private root and handoff paths never appear in the report.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.common.d5_connection_analysis import load_private_rows
from pipeline.common.real_private_graph import _handoffs
from pipeline.common.d6_private_graph import rehearse
from pipeline.common.d4_graph_e2e import D4_SOURCE_IDS


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-root", action="append", type=Path, required=True, help="authorized private handoff root; repeatable")
    parser.add_argument("--output", type=Path, required=True, help="aggregate-only output report")
    parser.add_argument("--expected-positive", type=int, default=1)
    args = parser.parse_args(argv)
    handoffs = _handoffs(args.private_root, set(D4_SOURCE_IDS))
    row_paths: dict[str, Path] = {}
    for source_id, kind, root in handoffs:
        candidate = root / ("records.jsonl" if kind == "evidence" else "graph-candidates" / "records.jsonl")
        if candidate.is_file():
            row_paths[source_id] = candidate
    observations = load_private_rows(row_paths) if row_paths else []
    report = rehearse(observations, positive_controls=args.expected_positive)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"source_count": len(row_paths), "private_rows_consumed": len(observations), "exact_edges": report["connections"]["exact"], "inferred_edges": report["connections"]["inferred"], "public_rows": 0}, sort_keys=True))
    return 0 if report["status"] == "verified" else 2


if __name__ == "__main__":
    raise SystemExit(main())
