#!/usr/bin/env python3
"""Urgently suppress a record and create a durable, payload-free case reference."""
import argparse, os, uuid
import psycopg

DEFAULT_DB = "postgresql://uec:uec-local-development-only@localhost:5433/uec"

def restrict(database_url, source_record_id, reason_category, policy_version, maintainer, note=None, scope="whole_record"):
    if reason_category not in {"privacy", "safety", "legal", "other"}:
        raise ValueError("reason category must be privacy, safety, legal, or other")
    if scope not in {"address", "coordinates", "whole_record"}:
        raise ValueError("scope must be address, coordinates, or whole_record")
    with psycopg.connect(database_url) as connection:
        with connection.transaction():
            source = connection.execute("""
                SELECT source_id, source_record_key,
                       (SELECT facility_id FROM uec.observations
                        WHERE source_record_id = record.source_record_id
                        ORDER BY observed_at DESC, observation_id DESC LIMIT 1)
                FROM uec.source_records record
                WHERE source_record_id = %s
            """, (source_record_id,)).fetchone()
            if not source:
                raise ValueError("source record not found")
            source_id, source_record_key, facility_id = source
            case_id = uuid.uuid4()
            # The note is intentionally not retained: operator intake notes
            # may contain private evidence. Keep audit metadata minimal.
            connection.execute("""
                INSERT INTO uec.suppression_cases
                (case_id, reason_category, status, policy_version, actor, decision)
                VALUES (%s, %s, 'active', %s, %s, 'suppress')
            """, (case_id, reason_category, policy_version, maintainer))
            connection.execute("""
                INSERT INTO uec.suppression_references
                (case_id, facility_id, source_id, source_record_key, scope)
                VALUES (%s, %s, %s, %s, %s)
            """, (case_id, facility_id, source_id, source_record_key, scope))
            connection.execute("""
                INSERT INTO uec.record_access_events
                (access_event_id, source_record_id, action, reason_category, policy_version, maintainer, note)
                VALUES (%s, %s, 'public_access_revoked', %s, %s, %s, %s)
            """, (uuid.uuid4(), source_record_id, reason_category, policy_version, maintainer, None))
    return case_id

if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("source_record_id", type=uuid.UUID)
    p.add_argument("--reason", required=True, choices=["privacy", "safety", "legal", "other"])
    p.add_argument("--policy-version", required=True)
    p.add_argument("--maintainer", required=True)
    p.add_argument("--note", help="accepted for CLI compatibility; sensitive intake notes are not stored")
    p.add_argument("--scope", choices=["address", "coordinates", "whole_record"], default="whole_record")
    p.add_argument("--database-url", default=os.environ.get("UEC_DATABASE_URL", DEFAULT_DB))
    a = p.parse_args()
    case_id = restrict(a.database_url, a.source_record_id, a.reason, a.policy_version, a.maintainer, a.note, a.scope)
    print(f"Recorded public-access revocation case {case_id}; evidence was not modified.")
