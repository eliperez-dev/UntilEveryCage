#!/usr/bin/env python3
"""Append official city reference points to PostGIS."""
import argparse, json, os
from pathlib import Path
import psycopg

DEFAULT_DB = "postgresql://uec:uec-local-development-only@localhost:5433/uec"

def load(path: Path, database_url: str) -> int:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    with psycopg.connect(database_url) as connection:
        with connection.transaction():
            inserted = 0
            for row in rows:
                result = connection.execute("""
                    INSERT INTO uec.city_reference_points
                    (country_code, city_name, postal_code, reference_location,
                     reference_source, source_retrieved_at, source_reference_id)
                    VALUES (%s, %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
                            %s, %s, %s)
                    ON CONFLICT DO NOTHING
                """, (row["country_code"], row["city_name"], row.get("postal_code"),
                      row["reference_longitude"], row["reference_latitude"],
                      row["reference_source"], row["source_retrieved_at"], row["source_reference_id"]))
                inserted += result.rowcount
    return inserted

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("staging", type=Path)
    parser.add_argument("--database-url", default=os.environ.get("UEC_DATABASE_URL", DEFAULT_DB))
    args = parser.parse_args()
    print(f"Inserted {load(args.staging, args.database_url)} city reference points")
