#!/usr/bin/env python3
"""Print privacy-safe aggregate geocoding queue, usage, retry, and ETA status."""

import argparse
import json
import os
from datetime import datetime, timezone

import psycopg


def status(database_url: str, provider: str | None = None) -> dict:
    parameters = (provider,) if provider else ()
    job_filter = "WHERE current.provider_id = %s" if provider else ""
    result_filter = "WHERE result.provider_id = %s" if provider else ""

    with psycopg.connect(database_url) as database:
        states = database.execute(
            f"""
            SELECT COALESCE(current.event_type, 'unknown'), current.provider_id, count(*)
            FROM uec.geocode_job_current AS current
            {job_filter}
            GROUP BY 1, 2
            ORDER BY 1, 2
            """,
            parameters,
        ).fetchall()
        countries = database.execute(
            f"""
            SELECT record.country_code, count(*)
            FROM uec.geocode_job_current AS current
            JOIN uec.source_records AS record USING (source_record_id)
            {job_filter}
            GROUP BY 1
            ORDER BY 1
            """,
            parameters,
        ).fetchall()
        daily_usage = database.execute(
            f"""
            SELECT date_trunc('day', result.queried_at)::date,
                   result.provider_id,
                   count(*)
            FROM uec.geocode_results AS result
            {result_filter}
            GROUP BY 1, 2
            ORDER BY 1 DESC, 2
            """,
            parameters,
        ).fetchall()
        pending = database.execute(
            f"""
            SELECT count(*)
            FROM uec.geocode_job_current AS current
            WHERE current.event_type IN ('queued', 'started')
            {('AND current.provider_id = %s' if provider else '')}
            """,
            parameters,
        ).fetchone()[0]
        completed = database.execute(
            f"""
            SELECT count(*)
            FROM uec.geocode_results AS result
            WHERE result.queried_at >= now() - interval '7 days'
            {('AND result.provider_id = %s' if provider else '')}
            """,
            parameters,
        ).fetchone()[0]

    daily_rate = completed / 7
    return {
        "schema_version": "geocode-operator-status-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "privacy_boundary": "aggregate only; no addresses, queries, payloads, identifiers, or keys",
        "states": [
            {"state": state, "provider": provider_id, "count": count}
            for state, provider_id, count in states
        ],
        "countries": [
            {"country_code": country_code, "count": count}
            for country_code, count in countries
        ],
        "daily_usage": [
            {"day": str(day), "provider": provider_id, "count": count}
            for day, provider_id, count in daily_usage
        ],
        "retry_state": "retryable failures are included in state counts; details are intentionally omitted",
        "pending": pending,
        "completed_last_7_days": completed,
        "eta_days": round(pending / daily_rate, 1) if daily_rate else None,
        "eta_basis": "7-day completed geocode result average; null means insufficient usage",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=os.environ.get(
            "UEC_DATABASE_URL",
            "postgresql://uec:uec-local-development-only@localhost:5433/uec",
        ),
    )
    parser.add_argument("--provider")
    parser.add_argument("--pretty", action="store_true")
    arguments = parser.parse_args()
    print(
        json.dumps(
            status(arguments.database_url, arguments.provider),
            indent=2 if arguments.pretty else None,
            default=str,
        )
    )
