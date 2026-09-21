"""Import one private graph handoff into a loopback disposable database.

This command never promotes a release or writes public projections.  Facility
and evidence handoffs must be selected explicitly because they use separate
database sinks.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from pipeline.common.graph_persistence import import_evidence_events, import_graph_candidates


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=("facility", "evidence"), required=True)
    parser.add_argument("--handoff", type=Path, required=True)
    parser.add_argument("--database-url", default=os.environ.get("UEC_DATABASE_URL", ""))
    parser.add_argument("--disposable-db", action="store_true", required=True)
    parser.add_argument("--batch-size", type=int, default=250)
    args = parser.parse_args()
    importer = import_graph_candidates if args.kind == "facility" else import_evidence_events
    result = importer(args.database_url, args.handoff, disposable_db=args.disposable_db, batch_size=args.batch_size)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
