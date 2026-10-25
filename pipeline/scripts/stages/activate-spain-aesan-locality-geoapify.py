#!/usr/bin/env python3
"""Consume retained AESAN locality events into the standard private queue; never call Geoapify."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from pipeline.sources.spain_rgseaa.map_activation import MAX_ACTIVATION_EVENTS, activate


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("events", help="private append-only AESAN locality event JSONL")
    parser.add_argument("--database-url", default=os.environ.get("UEC_DATABASE_URL"))
    parser.add_argument("--limit", type=int, default=MAX_ACTIVATION_EVENTS)
    args = parser.parse_args()
    if not args.database_url:
        parser.error("--database-url or UEC_DATABASE_URL is required")
    try:
        counts = activate(args.database_url, args.events, limit=args.limit)
    except Exception as error:
        print(f"activation_failed: {type(error).__name__}")
        return 1
    print("source=es.locations provider=geoapify " + " ".join(
        f"{key}={value}" for key, value in counts.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
