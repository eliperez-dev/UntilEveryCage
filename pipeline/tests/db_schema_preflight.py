"""Fail-fast connection and schema preflight for required database jobs."""

import os
import sys
from pathlib import Path

import psycopg


REQUIRED_TABLES = {
    "schema_migrations",
    "facilities",
    "organizations",
    "organization_relationship_observations",
    "claim_current",
    "source_entity_crosswalks",
    "source_records",
}


def main():
    database_url = os.environ.get("UEC_DATABASE_URL")
    if not database_url:
        print("UEC_DATABASE_URL is required for the database/schema preflight", file=sys.stderr)
        return 2
    try:
        with psycopg.connect(database_url) as connection:
            rows = connection.execute(
                "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE n.nspname='uec' AND c.relkind IN ('r','p','v','m','f')"
            ).fetchall()
            tables = {row[0] for row in rows}
            missing = sorted(REQUIRED_TABLES - tables)
            if missing:
                print(f"database schema preflight failed; missing tables: {', '.join(missing)}", file=sys.stderr)
                return 1
            expected = len(list((Path(__file__).parents[1] / "migrations").glob("*.sql")))
            applied = connection.execute("SELECT count(*) FROM uec.schema_migrations").fetchone()[0]
            if applied != expected:
                print(f"database schema preflight failed; applied {applied} migrations, expected {expected}", file=sys.stderr)
                return 1
    except psycopg.Error as error:
        print(f"database/schema preflight failed: {error.__class__.__name__}", file=sys.stderr)
        return 1
    print(f"database/schema preflight passed ({applied} migrations; required graph tables present)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
