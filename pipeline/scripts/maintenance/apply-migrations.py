#!/usr/bin/env python3
"""Apply ordered V2 migrations with an auditable checksum ledger."""

import argparse
import hashlib
import os
import time
from pathlib import Path

import psycopg


def migration_files(directory: Path) -> list[Path]:
    files = sorted(directory.glob("*.sql"))
    if not files:
        raise ValueError(f"no SQL migrations found in {directory}")
    return files


def apply(database_url: str, directory: Path) -> list[str]:
    files = migration_files(directory)
    applied: list[str] = []
    connection = None
    for attempt in range(10):
        try:
            connection = psycopg.connect(database_url)
            break
        except psycopg.OperationalError:
            if attempt == 9:
                raise
            time.sleep(1)
    assert connection is not None
    # Keep setup and each migration in separate transactions.  A later
    # migration failure must leave already-applied versions recorded so a
    # retry can resume, while the failing migration and its ledger row roll
    # back together.
    with connection:
        with connection.transaction():
            connection.execute("CREATE SCHEMA IF NOT EXISTS uec")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS uec.schema_migrations (
                    version TEXT PRIMARY KEY,
                    sha256 CHAR(64) NOT NULL,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
        for path in files:
            version = path.stem
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            with connection.transaction():
                row = connection.execute(
                    "SELECT sha256 FROM uec.schema_migrations WHERE version = %s",
                    (version,),
                ).fetchone()
                if row:
                    if row[0] != digest:
                        raise ValueError(f"migration checksum changed after application: {version}")
                    continue
                sql = path.read_text(encoding="utf-8")
                connection.execute(sql)
                connection.execute(
                    "INSERT INTO uec.schema_migrations (version, sha256) VALUES (%s, %s)",
                    (version, digest),
                )
                applied.append(version)
    return applied


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.environ.get("UEC_DATABASE_URL", "postgresql://uec:uec-local-development-only@localhost:5433/uec?sslmode=disable"))
    parser.add_argument("--directory", type=Path, default=Path(__file__).parents[2] / "migrations")
    args = parser.parse_args()
    for version in apply(args.database_url, args.directory):
        print(f"applied {version}")
