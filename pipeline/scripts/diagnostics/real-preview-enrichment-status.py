#!/usr/bin/env python3
"""Print aggregate-only real-preview geospatial enrichment status."""

import argparse
import json
import os

import psycopg


def report(database_url: str, source_id: str | None = None) -> dict:
    with psycopg.connect(database_url) as connection:
        rows = connection.execute("""
            SELECT state_code, reason_code, count(*)::bigint
            FROM real_preview.candidate_enrichment_reconciliation
            WHERE (%s::text IS NULL OR source_id=%s)
            GROUP BY state_code,reason_code ORDER BY state_code,reason_code
        """, (source_id, source_id)).fetchall()
    return {
        "status": "ok",
        "scope": "all_sources" if source_id is None else "one_source",
        "source_id": source_id,
        "candidate_count": sum(int(row[2]) for row in rows),
        "states": [{"state": row[0], "reason": row[1], "count": int(row[2])} for row in rows],
        "privacy": "aggregate_only",
        "publication": "none",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source")
    parser.add_argument("--database-url", default=os.environ.get("UEC_DATABASE_URL", "postgresql://uec:uec-local-development-only@localhost:5433/uec"))
    args = parser.parse_args()
    print(json.dumps(report(args.database_url, args.source), sort_keys=True))
