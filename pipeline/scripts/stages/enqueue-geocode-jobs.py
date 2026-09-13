#!/usr/bin/env python3
"""Create append-only database geocoding jobs from imported source records."""

import argparse
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import psycopg


def enqueue(records_path: Path, database_url: str, provider_id: str, limit: int | None = None) -> int:
    count = 0
    with psycopg.connect(database_url) as connection:
        with connection.transaction():
            for line in records_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                record = json.loads(line)
                address = record.get("address", {})
                if not address.get("street") or not address.get("postal_code"):
                    continue
                query = ", ".join(filter(None, [address["street"], address["postal_code"], address.get("city"), "Denmark"]))
                source_record_id = uuid.uuid5(uuid.NAMESPACE_URL, f"urn:uec:source-record:dk.smiley:{record['source_record_key']}:{record['source_artifact_sha256']}")
                job = connection.execute(
                    "INSERT INTO uec.geocode_jobs (source_record_id, provider_id, query) VALUES (%s, %s, %s) ON CONFLICT (source_record_id, provider_id, query) DO NOTHING RETURNING job_id",
                    (source_record_id, provider_id, query),
                ).fetchone()
                if job:
                    connection.execute("INSERT INTO uec.geocode_job_events (job_id, event_type, attempt_number, occurred_at) VALUES (%s, 'queued', 1, %s)", (job[0], datetime.now(timezone.utc)))
                    count += 1
                if limit is not None and count >= limit:
                    break
    return count


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("records", type=Path)
    parser.add_argument("--database-url", default=os.environ.get("UEC_DATABASE_URL", "postgresql://uec:uec-local-development-only@localhost:5433/uec"))
    parser.add_argument("--provider", default="dawa")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    print(f"Queued {enqueue(args.records, args.database_url, args.provider, args.limit)} geocoding jobs")
