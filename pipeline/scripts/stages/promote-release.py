#!/usr/bin/env python3
"""Promote a validated release to the active public release state."""

import argparse
import json
import os
import sys
from pathlib import Path

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
            unsafe = connection.execute("""
                SELECT
                  count(*) FILTER (WHERE m.default_visible AND (g.status IS DISTINCT FROM 'accepted' OR g.result IS NULL)),
                  count(*) FILTER (WHERE o.classification_review_status <> 'approved' AND m.default_visible),
                  count(*) FILTER (WHERE r.publication_eligible IS DISTINCT FROM true OR r.privacy_screening_status <> 'passed' OR r.maintainer_approval <> 'approved'),
                  count(*) FILTER (WHERE s.source_record_id IS NOT NULL)
                FROM uec.release_members m
                JOIN uec.observations o ON o.observation_id = m.observation_id
                LEFT JOIN LATERAL (SELECT status, result FROM uec.geocode_results WHERE source_record_id=o.source_record_id ORDER BY queried_at DESC, geocode_result_id DESC LIMIT 1) g ON true
                LEFT JOIN uec.publication_review_current r ON r.source_record_id=o.source_record_id
                LEFT JOIN uec.public_access_restricted s ON s.source_record_id=o.source_record_id
                WHERE m.release_id=%s
            """, (release_id,)).fetchone()
            if any(unsafe):
                raise ValueError(f"release safety gates failed: coordinate_not_ready={unsafe[0]}, review_required={unsafe[1]}, publication_not_approved={unsafe[2]}, active_suppression={unsafe[3]}")
            previous = connection.execute("SELECT release_id FROM uec.releases WHERE status = 'promoted' AND profile = %s AND release_id <> %s", (target[1], release_id)).fetchall()
            connection.execute("UPDATE uec.releases SET status = 'validated' WHERE status = 'promoted' AND profile = %s AND release_id <> %s", (target[1], release_id))
            connection.execute("UPDATE uec.releases SET status = 'promoted' WHERE release_id = %s", (release_id,))
            return {"release_id": release_id, "status": "promoted", "previously_promoted": [row[0] for row in previous]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("release_id")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--database-url", default=os.environ.get("UEC_DATABASE_URL", "postgresql://uec:uec-local-development-only@localhost:5433/uec"))
    args = parser.parse_args()
    try:
        result = promote(args.database_url, args.release_id)
        serialized = json.dumps(result, indent=2) + "\n"
        print(serialized, end="")
        if args.manifest:
            args.manifest.write_text(serialized, encoding="utf-8")
    except Exception as error:
        print(json.dumps({"status": "blocked", "error": str(error)}, indent=2), file=sys.stderr)
        sys.exit(1)
