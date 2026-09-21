"""Run the D5 real private-corpus graph rehearsal.

Example (operator-only, private roots are supplied explicitly)::

    python pipeline/scripts/diagnostics/rehearse-real-private-graph.py \
      --private-root C:\\path\\to\\retained-evidence \
      --output D:\\UntilEveryCage-private\\d5-rehearsal\\report.json

The output is aggregate-only.  Use ``--database-url`` only with a loopback
disposable database that has the D4 marker and pass ``--disposable-db``.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.common.real_private_graph import run_rehearsal, write_report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-root", action="append", type=Path, required=True, help="authorized private manifest/artifact root; repeatable")
    parser.add_argument("--source", action="append", default=[], help="restrict to a source id; repeatable")
    parser.add_argument("--output", type=Path, required=True, help="row-free output report")
    parser.add_argument("--database-url", default=os.environ.get("UEC_DATABASE_URL", ""))
    parser.add_argument("--disposable-db", action="store_true", help="acknowledge a loopback non-default-port D4 disposable database")
    args = parser.parse_args()
    report = run_rehearsal(args.private_root, selected_sources=args.source, database_url=args.database_url, disposable_db=args.disposable_db)
    digest = write_report(report, args.output)
    print(json.dumps({"output_sha256": digest, "source_count": report["source_count"], "handoffs": report["handoffs"], "database": report["database"]}, sort_keys=True))
    return 0 if report["database"]["blocked"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
