"""Append IGN-derived coarse municipality points for verified AESAN localities."""
from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from pathlib import Path
from typing import Any

import psycopg

from .location_enrichment import SOURCE_ID, registration_key_sha256
from .map_activation import verified_event
from .municipality_reference import (
    REFERENCE_SOURCE, load_ign_reference_index,
    exact_municipality_reference_index, resolve_municipality_reference,
)

DATABASE = "uec_launch_sources_test_20261025"
MAX_EVENTS = 20000
MAX_EVENT_FILE_BYTES = 32 * 1024 * 1024


def load_locality_events(path: str | Path, *, limit: int = MAX_EVENTS) -> list[dict[str, Any]]:
    """Read and validate a full bounded event cohort without the old 24-call cap."""
    source = Path(path)
    if (not 1 <= limit <= MAX_EVENTS or not source.is_file() or source.is_symlink()
            or source.stat().st_size > MAX_EVENT_FILE_BYTES):
        raise ValueError("spain_event_file_invalid_or_over_limit")
    events: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    with source.open("r", encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                raise ValueError("spain_event_json_invalid") from None
            if not isinstance(raw, dict):
                raise ValueError("spain_event_schema_invalid")
            clean = verified_event(raw)
            if clean is None:
                continue
            identity = (clean["source_record_key"], clean["lookup_hash"])
            if identity in seen:
                continue
            seen.add(identity)
            clean["_event"] = raw
            events.append(clean)
            if len(events) > limit:
                raise ValueError("spain_event_cohort_exceeds_limit")
    return events


def _candidate_index(connection: Any, expected_snapshot_sha256: str
                     ) -> dict[tuple[str, str], list[dict[str, Any]]]:
    rows = connection.execute("""
        SELECT candidate.candidate_id,candidate.snapshot_sha256,candidate.source_group_key,
               observation.source_identifier,candidate.country_code,candidate.location_class,
               candidate.default_map_scope,location.location_evidence->>'country_code',
               NOT EXISTS (
                   SELECT 1 FROM real_preview.geocode_targets target
                   JOIN uec.geocode_jobs job USING(job_id)
                   JOIN uec.public_access_restricted restricted USING(source_record_id)
                   WHERE target.candidate_id=candidate.candidate_id
               ) AS restriction_clear
          FROM real_preview.candidates candidate
          JOIN real_preview.observations observation
            ON observation.preview_id=candidate.representative_observation_id
           AND observation.snapshot_sha256=candidate.snapshot_sha256
           AND observation.source_id=candidate.source_id
          JOIN real_preview.candidate_private_location_evidence location
            ON location.candidate_id=candidate.candidate_id
         WHERE candidate.snapshot_sha256=%s AND candidate.source_id=%s AND candidate.country_code='ES'
    """, (expected_snapshot_sha256, SOURCE_ID)).fetchall()
    index: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        if str(row[1]).strip() != expected_snapshot_sha256:
            continue
        registration_hash = registration_key_sha256(str(row[2]))
        record_key_hash = str(row[3]).strip()
        if registration_hash is None or len(record_key_hash) != 64:
            continue
        index.setdefault((registration_hash, record_key_hash), []).append({
            "candidate_id": row[0], "snapshot_sha256": str(row[1]).strip(),
            "source_group_key": row[2], "country_code": row[4],
            "location_class": row[5], "default_map_scope": row[6],
            "evidence_country_code": row[7], "restriction_clear": row[8],
        })
    return index


def _candidate_rejection(candidate: dict[str, Any]) -> str | None:
    """Apply existing private-source and restriction gates before local display."""
    if not candidate["restriction_clear"]:
        return "events_restricted"
    if (candidate["country_code"] != "ES" or candidate["evidence_country_code"] != "ES"
            or candidate["location_class"] != "unmapped_private_observation"
            or candidate["default_map_scope"] is not True):
        return "events_ineligible"
    return None


def activate(database_url: str, events_path: str | Path, reference_path: str | Path, *,
             limit: int = MAX_EVENTS, connect: Any = None) -> dict[str, int]:
    """Idempotently append coarse IGN reference evidence; never geocode or publish."""
    if connect is None:
        connect = psycopg.connect
    events = load_locality_events(events_path, limit=limit)
    reference = load_ign_reference_index(reference_path)
    reference_index = exact_municipality_reference_index(reference["municipalities"])
    counts: Counter[str] = Counter()
    counts["events_accepted"] = len(events)
    with connect(database_url) as connection, connection.transaction():
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        if connection.execute("SELECT current_database()").fetchone()[0] != DATABASE:
            raise RuntimeError("database_identity_invalid")
        latest = connection.execute("""
            SELECT snapshot_sha256 FROM real_preview.source_preview_runs
             WHERE source_id=%s ORDER BY created_at DESC,run_id DESC LIMIT 1
        """, (SOURCE_ID,)).fetchone()
        if latest is None:
            raise RuntimeError("spain_preview_snapshot_missing")
        snapshot_sha256 = str(latest[0]).strip()
        if len(snapshot_sha256) != 64:
            raise RuntimeError("spain_preview_snapshot_invalid")
        candidates = _candidate_index(connection, snapshot_sha256)
        for event in events:
            rows = candidates.get((event["lookup_hash"], event["source_record_key"]), [])
            if len(rows) != 1:
                counts["events_ambiguous" if len(rows) > 1 else "events_ineligible"] += 1
                continue
            candidate = rows[0]
            rejection = _candidate_rejection(candidate)
            if rejection is not None:
                counts[rejection] += 1
                continue
            locality = resolve_municipality_reference(
                event["municipality"], event["province"], reference_index,
                source_metadata=reference)
            if locality["outcome"] != "matched":
                counts[f"reference_{locality['outcome']}"] += 1
                continue
            reference_id = locality["reference_source_id"]
            existing = connection.execute("""
                SELECT snapshot_sha256,source_id,reference_latitude,reference_longitude,
                       display_precision,display_geometry_source,reference_source_id,reference_source
                  FROM real_preview.local_reference_display_evidence
                 WHERE candidate_id=%s AND reference_source_id=%s
            """, (candidate["candidate_id"], reference_id)).fetchone()
            geometry_source = "IGN NGMEP 2026 municipality reference; " + locality["coordinate_origin"]
            evidence_source = (
                f"{REFERENCE_SOURCE}; {reference['attribution']}; dataset_sha256="
                f"{reference['source_sha256']}; AESAN lookup event="
                f"{event['_event'].get('retrieved_at')}"
            )
            if existing is not None:
                expected = (candidate["snapshot_sha256"], SOURCE_ID, locality["latitude"],
                            locality["longitude"], "locality_reference_coarse", geometry_source,
                            reference_id, evidence_source)
                if tuple(existing) != expected:
                    counts["existing_reference_conflict"] += 1
                else:
                    counts["already_present"] += 1
                continue
            inserted = connection.execute("""
                INSERT INTO real_preview.local_reference_display_evidence
                    (candidate_id,snapshot_sha256,source_id,reference_latitude,reference_longitude,
                     display_precision,display_geometry_source,reference_source_id,reference_source)
                VALUES (%s,%s,%s,%s,%s,'locality_reference_coarse',%s,%s,%s)
                ON CONFLICT (candidate_id,reference_source_id) DO NOTHING
                RETURNING evidence_id
            """, (candidate["candidate_id"], candidate["snapshot_sha256"], SOURCE_ID,
                  locality["latitude"], locality["longitude"], geometry_source,
                  reference_id, evidence_source)).fetchone()
            counts["evidence_appended" if inserted else "concurrent_existing"] += 1
    counts["provider_calls"] = 0
    counts["publications"] = 0
    return dict(sorted(counts.items()))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("events", type=Path)
    parser.add_argument("reference", type=Path)
    parser.add_argument("--database-url", default=os.environ.get("UEC_DATABASE_URL"))
    parser.add_argument("--limit", type=int, default=MAX_EVENTS)
    args = parser.parse_args()
    if not args.database_url:
        parser.error("--database-url or UEC_DATABASE_URL is required")
    try:
        counts = activate(args.database_url, args.events, args.reference, limit=args.limit)
    except Exception as error:
        print(f"activation_failed: {type(error).__name__}")
        return 1
    print("source=es.locations " + " ".join(f"{key}={value}" for key, value in counts.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
