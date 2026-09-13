#!/usr/bin/env python3
"""Promote a validated release to the active public release state."""

import argparse
import json
import os
import sys

import psycopg


def can_promote(status: str) -> bool:
    return status == "validated"


def promote(database_url: str, release_id: str) -> dict:
    with psycopg.connect(database_url) as connection:
        with connection.transaction():
            target = connection.execute("SELECT status, profile FROM uec.releases WHERE release_id = %s FOR UPDATE", (release_id,)).fetchone()
            if not target:
                raise ValueError(f"release not found: {release_id}")
            if not can_promote(target[0]):
                raise ValueError(f"release must be validated before promotion; current status is {target[0]}")
            previous = connection.execute("SELECT release_id FROM uec.releases WHERE status = 'promoted' AND profile = %s AND release_id <> %s", (target[1], release_id)).fetchall()
            connection.execute("UPDATE uec.releases SET status = 'validated' WHERE status = 'promoted' AND profile = %s AND release_id <> %s", (target[1], release_id))
            connection.execute("UPDATE uec.releases SET status = 'promoted' WHERE release_id = %s", (release_id,))
            return {"release_id": release_id, "status": "promoted", "previously_promoted": [row[0] for row in previous]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("release_id")
    parser.add_argument("--database-url", default=os.environ.get("UEC_DATABASE_URL", "postgresql://uec:uec-local-development-only@localhost:5433/uec"))
    args = parser.parse_args()
    try:
        print(json.dumps(promote(args.database_url, args.release_id), indent=2))
    except Exception as error:
        print(json.dumps({"status": "blocked", "error": str(error)}, indent=2), file=sys.stderr)
        sys.exit(1)
