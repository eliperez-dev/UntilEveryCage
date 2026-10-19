#!/usr/bin/env python3
"""Write a local serving-package manifest and explicit role-grant SQL.

It writes no database state and never exports source artifacts or private
payloads.  The resulting files are inputs to a separately reviewed restore
rehearsal after schema migrations have been applied.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from pipeline.common.release_serving import grant_sql, package_manifest  # noqa: E402

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-id", action="append", required=True)
    parser.add_argument("--migration-inventory-sha256", required=True)
    parser.add_argument("--manifest-output", type=Path, required=True)
    parser.add_argument("--grants-output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        for path in (args.manifest_output, args.grants_output):
            if path.exists() or path.is_symlink() or not path.parent.is_dir():
                raise ValueError("outputs must be new files in existing directories")
        manifest = package_manifest(release_ids=args.release_id, migration_inventory_sha256=args.migration_inventory_sha256)
        args.manifest_output.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8", newline="\n")
        args.grants_output.write_text(grant_sql(), encoding="utf-8", newline="\n")
        print(json.dumps({"status": "prepared", "package_sha256": manifest["package_sha256"], "release_count": len(manifest["release_ids"])}))
        return 0
    except (OSError, ValueError) as error:
        print(json.dumps({"status": "blocked", "reason": str(error)[:160]}))
        return 2

if __name__ == "__main__": raise SystemExit(main())
