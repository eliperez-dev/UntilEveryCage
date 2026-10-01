#!/usr/bin/env python3
"""Reproject retained observation JSONL through the versioned taxonomy.

Default is a dry run. --apply writes to an explicit output path and updates
only the derived top-level ``taxonomy`` object; original source evidence and
normalized fields are copied unchanged.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from pipeline.taxonomy_crosswalk import reproject
from pipeline.taxonomy_crosswalk import crosswalk_document, persistence_assignments
from pipeline.taxonomy.persistence import persist_preview_candidate_assignment_set, persist_uec_assignment_set


def read_jsonl(path: Path) -> list[dict]:
    records = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                raise ValueError(f"blank JSONL row at line {line_number}")
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(f"JSONL row is not an object at line {line_number}")
            records.append(row)
    return records


def atomic_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            for record in records:
                stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True, default=list) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="retained observation JSONL")
    parser.add_argument("--apply", action="store_true", help="write projected rows to --output")
    parser.add_argument("--output", type=Path, help="required with --apply; must not be the input path")
    parser.add_argument("--report", type=Path, help="write the aggregate report; defaults to stdout")
    parser.add_argument("--database-url", help="optional database target; requires --apply and lineage IDs on every row")
    args = parser.parse_args()
    if args.apply and (args.output is None or args.output.resolve() == args.input.resolve()):
        parser.error("--apply requires --output distinct from input")
    if not args.apply and args.output is not None:
        parser.error("--output requires --apply")
    if args.report and args.report.resolve() == args.input.resolve():
        parser.error("--report must not overwrite input")
    if args.apply and args.report and args.output.resolve() == args.report.resolve():
        parser.error("--report and --output must be distinct paths")
    if args.database_url and not args.apply:
        parser.error("--database-url requires --apply; dry runs are non-mutating")
    rows = read_jsonl(args.input)
    projected, report = reproject(rows)
    if args.apply:
        if args.database_url:
            import psycopg
            with psycopg.connect(args.database_url) as connection:
                for row in projected:
                    source_id = str(row.get("source_id") or "")
                    document = crosswalk_document(source_id)
                    assignment_rows = persistence_assignments(row["taxonomy"])
                    preview = row.get("preview_lineage") if isinstance(row.get("preview_lineage"), dict) else row
                    if all(preview.get(key) for key in ("candidate_id", "representative_observation_id", "snapshot_sha256")):
                        persist_preview_candidate_assignment_set(
                            connection,
                            candidate_id=str(preview["candidate_id"]),
                            representative_observation_id=str(preview["representative_observation_id"]),
                            snapshot_sha256=str(preview["snapshot_sha256"]),
                            source_id=source_id,
                            document=document,
                            assignment_rows=assignment_rows,
                        )
                    elif all(row.get(key) for key in ("observation_id", "source_record_id", "artifact_id")):
                        persist_uec_assignment_set(
                            connection,
                            observation_id=str(row["observation_id"]),
                            source_record_id=str(row["source_record_id"]),
                            artifact_id=str(row["artifact_id"]),
                            document=document,
                            assignment_rows=assignment_rows,
                        )
                    else:
                        raise ValueError("database reprojection row lacks genuine UEC or real_preview lineage")
        atomic_jsonl(args.output, projected)
        report["applied"] = True
        report["output"] = str(args.output)
    else:
        report["applied"] = False
    payload = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(payload, encoding="utf-8")
    else:
        sys.stdout.write(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
