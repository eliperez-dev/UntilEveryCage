#!/usr/bin/env python3
"""Record an explicit review-authorized lift for an append-only suppression case."""
import argparse
import os
import uuid

import psycopg

DEFAULT_DB = "postgresql://uec:uec-local-development-only@localhost:5433/uec"


def lift(database_url, case_id, policy_version, maintainer, note=None):
    with psycopg.connect(database_url) as connection:
        with connection.transaction():
            case = connection.execute(
                "SELECT reason_category FROM uec.suppression_cases WHERE case_id=%s",
                (case_id,),
            ).fetchone()
            if not case:
                raise ValueError("suppression case not found")
            # Do not persist operator notes: they can contain private evidence.
            connection.execute("""
                INSERT INTO uec.suppression_case_events
                (case_id, event_type, reason_category, policy_version, actor, decision)
                VALUES (%s, 'lifted', %s, %s, %s, 'lift')
            """, (case_id, case[0], policy_version, maintainer))
            connection.execute("""
                INSERT INTO uec.record_access_events
                (access_event_id, source_record_id, action, reason_category, policy_version, maintainer)
                SELECT gen_random_uuid(), source_record_id, 'public_access_restored',
                       %s, %s, %s
                FROM uec.source_records record
                JOIN uec.suppression_references ref
                  ON ref.case_id=%s
                 AND ((ref.source_id=record.source_id AND ref.source_record_key=record.source_record_key)
                      OR EXISTS (SELECT 1 FROM uec.observations observation
                                 WHERE observation.facility_id=ref.facility_id
                                   AND observation.source_record_id=record.source_record_id))
            """, (case[0], policy_version, maintainer, case_id))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_id", type=uuid.UUID)
    parser.add_argument("--policy-version", required=True)
    parser.add_argument("--maintainer", required=True)
    parser.add_argument("--note", help="accepted for CLI compatibility; sensitive intake notes are not stored")
    parser.add_argument("--database-url", default=os.environ.get("UEC_DATABASE_URL", DEFAULT_DB))
    args = parser.parse_args()
    lift(args.database_url, args.case_id, args.policy_version, args.maintainer, args.note)
    print("Recorded explicit suppression lift; evidence was not modified.")
