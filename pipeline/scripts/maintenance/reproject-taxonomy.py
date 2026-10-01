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
    args = parser.parse_args()
    if args.apply and (args.output is None or args.output.resolve() == args.input.resolve()):
        parser.error("--apply requires --output distinct from input")
    if not args.apply and args.output is not None:
        parser.error("--output requires --apply")
    if args.report and args.report.resolve() == args.input.resolve():
        parser.error("--report must not overwrite input")
    if args.apply and args.report and args.output.resolve() == args.report.resolve():
        parser.error("--report and --output must be distinct paths")
    rows = read_jsonl(args.input)
    projected, report = reproject(rows)
    if args.apply:
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
