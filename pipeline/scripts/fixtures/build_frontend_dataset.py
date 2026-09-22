#!/usr/bin/env python3
"""Build or validate the E1 frontend development dataset boundary."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
# Running a script by path puts this file's directory on sys.path rather than
# the repository root. Keep the CLI usable from the launchpad and PowerShell.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from pipeline.common.frontend_dataset import SEED, build, validate

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__); sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build"); b.add_argument("--mode", choices=("representative", "performance", "private"), required=True); b.add_argument("--output-dir", type=Path, required=True); b.add_argument("--seed", type=int, default=SEED); b.add_argument("--performance-count", type=int, default=100_000); b.add_argument("--edge-count", type=int, default=150_000); b.add_argument("--private-manifest", type=Path)
    v = sub.add_parser("validate"); v.add_argument("--output-dir", type=Path, required=True); v.add_argument("--require-performance", action="store_true")
    args = parser.parse_args(); result = build(args.output_dir, mode=args.mode, seed=args.seed, performance_count=args.performance_count, edge_count=args.edge_count, private_manifest=args.private_manifest) if args.command == "build" else validate(args.output_dir, require_performance=args.require_performance)
    print(json.dumps(result, sort_keys=True, indent=2)); return 0 if result.get("ok", True) else 1

if __name__ == "__main__": raise SystemExit(main())
