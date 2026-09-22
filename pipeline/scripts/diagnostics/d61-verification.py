"""Emit the aggregate D6.1 verification report.

The private roots are operator-supplied and are read only in memory.  This
diagnostic never records a root, URL, source row, or raw field.  It is useful
for checking candidate yield before integration, but it cannot claim D6.1 is
verified until a disposable Docker/Postgres rehearsal supplies a report with
at least one genuine inferred connection.

Invoke this diagnostic with operator-supplied ``--private-root`` and
``--output`` values.  Use ``--real-rehearsal-report`` to combine the offline candidate report with
the aggregate result emitted by the mandatory Docker/Postgres rehearsal.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.common.d5_connection_analysis import _probabilistic_candidates, load_private_rows
from pipeline.common.d61_verification import build_report, validate_report
from pipeline.common.d4_graph_e2e import D4_SOURCE_IDS
from pipeline.common.real_private_graph import _handoffs


def _real_counts(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("real rehearsal report is unreadable") from exc
    validate_report(payload)
    rehearsal = payload["real_rehearsal"]
    return {
        "executed": bool(rehearsal["executed"]),
        "genuine_inferred_connections": int(rehearsal["genuine_inferred_connections"]),
        "persisted_exact": int(payload["persisted"]["exact"]),
        "persisted_inferred": int(payload["persisted"]["inferred"]),
        "skipped": int(payload["skipped"]["ambiguous_blocks"]),
        "skip_reasons": dict(payload["skipped"]["reasons"]),
        "idempotent": payload["persisted"].get("idempotent"),
    }


def build_diagnostic(private_roots: list[Path], *, real_rehearsal_report: Path | None = None) -> dict[str, Any]:
    handoffs = _handoffs(private_roots, set(D4_SOURCE_IDS))
    row_paths: dict[str, Path] = {}
    for source_id, kind, root in handoffs:
        candidate = root / ("records.jsonl" if kind == "evidence" else Path("graph-candidates") / "records.jsonl")
        if candidate.is_file():
            row_paths[source_id] = candidate
    observations = load_private_rows(row_paths) if row_paths else []
    candidates, capped = _probabilistic_candidates(observations)
    exact_candidates = sum(bool(row.facility_ids and row.organization_ids) for row in observations)
    real = _real_counts(real_rehearsal_report) if real_rehearsal_report else {
        "executed": False,
        "genuine_inferred_connections": 0,
        "persisted_exact": 0,
        "persisted_inferred": 0,
        "skipped": 0,
        "skip_reasons": {},
        "idempotent": None,
    }
    reasons = dict(real["skip_reasons"])
    if capped:
        reasons["candidate_generation_cap"] = reasons.get("candidate_generation_cap", 0) + 1
    report = build_report(
        execution="authorized_private_root_offline",
        authorized_handoffs=len(row_paths),
        private_rows_consumed=len(observations),
        candidate_count=exact_candidates + len(candidates),
        candidate_exact_count=exact_candidates,
        candidate_inferred_count=len(candidates),
        persisted_exact_count=real["persisted_exact"] if "persisted_exact" in real else 0,
        persisted_inferred_count=real["persisted_inferred"],
        skipped_ambiguous_count=real["skipped"] + (1 if capped else 0),
        skipped_reasons=reasons,
        negative_controls=0,
        conflicting_controls=0,
        genuine_inferred_connections=real["genuine_inferred_connections"],
        real_rehearsal_executed=real["executed"],
        idempotent=real["idempotent"],
        api_pages={"candidate_inferred": min(len(candidates), 100)},
        public_rows=0,
        public_edges=0,
    )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-root", action="append", type=Path, required=True, help="authorized private handoff root; repeatable")
    parser.add_argument("--real-rehearsal-report", type=Path, help="aggregate report emitted by the Docker/Postgres rehearsal")
    parser.add_argument("--output", type=Path, required=True, help="aggregate-only output report")
    args = parser.parse_args(argv)
    report = build_diagnostic(args.private_root, real_rehearsal_report=args.real_rehearsal_report)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "candidate_count": report["candidates"]["total"],
        "persisted_inferred": report["persisted"]["inferred"],
        "public_rows": report["publication"]["public_rows"],
    }, sort_keys=True))
    return 0 if report["status"] == "verified" else 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
