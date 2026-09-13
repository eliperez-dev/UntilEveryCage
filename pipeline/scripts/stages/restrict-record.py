#!/usr/bin/env python3
"""Record an append-only public-access safety restriction."""
import argparse, os, uuid
import psycopg

DEFAULT_DB = "postgresql://uec:uec-local-development-only@localhost:5433/uec"

def restrict(database_url, source_record_id, reason_category, policy_version, maintainer, note=None):
    if reason_category not in {"privacy", "safety", "legal", "other"}:
        raise ValueError("reason category must be privacy, safety, legal, or other")
    with psycopg.connect(database_url) as connection:
        with connection.transaction():
            connection.execute("""
                INSERT INTO uec.record_access_events
                (access_event_id, source_record_id, action, reason_category, policy_version, maintainer, note)
                VALUES (%s, %s, 'public_access_revoked', %s, %s, %s, %s)
            """, (uuid.uuid4(), source_record_id, reason_category, policy_version, maintainer, note))

if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("source_record_id", type=uuid.UUID)
    p.add_argument("--reason", required=True, choices=["privacy", "safety", "legal", "other"])
    p.add_argument("--policy-version", required=True)
    p.add_argument("--maintainer", required=True)
    p.add_argument("--note")
    p.add_argument("--database-url", default=os.environ.get("UEC_DATABASE_URL", DEFAULT_DB))
    a = p.parse_args()
    restrict(a.database_url, a.source_record_id, a.reason, a.policy_version, a.maintainer, a.note)
    print("Recorded public-access revocation; evidence was not modified.")
