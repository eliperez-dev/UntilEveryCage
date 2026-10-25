#!/usr/bin/env python3
"""Acquire a bounded AESAN locality-event cohort aligned to the current preview snapshot."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from pipeline.sources.spain_rgseaa.location_enrichment import (
    MAX_LOOKUPS, SOURCE_ID, append_private_events, enrich_records,
    registration_key_sha256,
)

DATABASE = "uec_launch_sources_test_20261025"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _rows(path: Path) -> dict[str, dict]:
    if not path.is_file() or path.is_symlink():
        raise ValueError("normalized_records_file_invalid")
    rows = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            raise ValueError("normalized_records_json_invalid") from None
        if not isinstance(record, dict) or record.get("source_id") != SOURCE_ID:
            raise ValueError("normalized_records_source_mismatch")
        record_key = record.get("source_record_key")
        normalized = record.get("normalized")
        if not isinstance(record_key, str) or not isinstance(normalized, dict):
            raise ValueError("normalized_records_schema_invalid")
        if record_key in rows:
            raise ValueError("normalized_records_key_duplicate")
        rows[record_key] = record
    return rows


def acquire(database_url: str, records_path: Path, output_path: Path, *,
            limit: int = MAX_LOOKUPS, lookup=None, connect=None) -> dict[str, int]:
    if not 1 <= limit <= MAX_LOOKUPS:
        raise ValueError(f"AESAN locality acquisition limit must be 1..{MAX_LOOKUPS}")
    approved_root = os.environ.get("UEC_REAL_PREVIEW_RUNS_ROOT")
    if not approved_root:
        raise ValueError("UEC_REAL_PREVIEW_RUNS_ROOT_required_for_generated_artifacts")
    root = Path(approved_root).resolve()
    output_path = output_path.resolve()
    if not output_path.is_relative_to(root):
        raise ValueError("event_output_must_be_under_UEC_REAL_PREVIEW_RUNS_ROOT")
    if not records_path.is_file() or records_path.is_symlink():
        raise ValueError("normalized_records_file_invalid")
    records_hash = _sha256_file(records_path)

    connection_factory = connect or psycopg.connect
    with connection_factory(database_url, options="-c default_transaction_read_only=on") as connection:
        with connection.transaction():
            connection.execute("SET TRANSACTION READ ONLY")
            if connection.execute("SELECT current_database()").fetchone()[0] != DATABASE:
                raise RuntimeError("database_identity_invalid")
            manifest = connection.execute("""
                WITH latest AS (
                    SELECT snapshot_sha256 FROM real_preview.source_preview_runs
                     WHERE source_id=%s ORDER BY created_at DESC,run_id DESC LIMIT 1
                )
                SELECT manifest.snapshot_sha256,manifest.normalized_sha256
                  FROM real_preview.source_manifests manifest
                  JOIN latest USING(snapshot_sha256)
                 WHERE manifest.source_id=%s
            """, (SOURCE_ID, SOURCE_ID)).fetchone()
            if not manifest or records_hash != manifest[1].strip():
                raise RuntimeError("normalized_records_not_latest_snapshot")
            representatives = connection.execute("""
                WITH latest AS (
                    SELECT snapshot_sha256 FROM real_preview.source_preview_runs
                     WHERE source_id=%s ORDER BY created_at DESC,run_id DESC LIMIT 1
                )
                SELECT candidate.source_group_key, observation.source_identifier
                  FROM real_preview.candidates candidate
                  JOIN latest USING(snapshot_sha256)
                  JOIN real_preview.observations observation
                    ON observation.preview_id=candidate.representative_observation_id
                   AND observation.snapshot_sha256=candidate.snapshot_sha256
                   AND observation.source_id=candidate.source_id
                  JOIN real_preview.candidate_private_location_evidence location
                    ON location.candidate_id=candidate.candidate_id
                 WHERE candidate.source_id=%s AND candidate.country_code='ES'
                   AND candidate.location_class='unmapped_private_observation'
                   AND candidate.default_map_scope
                   AND location.location_evidence->>'country_code'='ES'
                   AND NULLIF(BTRIM(location.location_evidence->>'address'),'') IS NOT NULL
                   AND NOT EXISTS (
                       SELECT 1 FROM real_preview.geocode_targets target
                       JOIN uec.geocode_jobs job USING(job_id)
                       JOIN uec.public_access_restricted restricted USING(source_record_id)
                       WHERE target.candidate_id=candidate.candidate_id
                   )
                 ORDER BY candidate.candidate_id
                 LIMIT %s
            """, (SOURCE_ID, SOURCE_ID, limit)).fetchall()

    if len(representatives) != limit:
        raise RuntimeError("latest_snapshot_has_fewer_than_requested_eligible_representatives")
    rows = _rows(records_path)
    selected = []
    for registration, record_key in representatives:
        record = rows.get(record_key)
        if record is None:
            raise RuntimeError("latest_snapshot_representative_missing_from_normalized_records")
        values = record.get("source_values") or {}
        normalized = record.get("normalized") or {}
        source_registration = values.get("N_RGSEAA") or normalized.get("establishment_id")
        if registration_key_sha256(str(source_registration)) != registration_key_sha256(str(registration)):
            raise RuntimeError("latest_snapshot_registration_identity_mismatch")
        if not isinstance(normalized.get("address"), str) or not normalized["address"].strip():
            raise RuntimeError("latest_snapshot_representative_address_missing")
        selected.append(record)
    events = enrich_records(selected, limit=limit, lookup=lookup) if lookup else enrich_records(selected, limit=limit)
    append_private_events(output_path, events)
    return {"requests": len(events), "matched": sum(item.get("outcome") == "matched" for item in events),
            "not_found": sum(item.get("outcome") == "not_found" for item in events),
            "ambiguous": sum(item.get("outcome") == "ambiguous_exact_registration" for item in events),
            "province_conflict": sum(item.get("outcome") == "province_conflict" for item in events),
            "other": sum(item.get("outcome") not in {"matched", "not_found", "ambiguous_exact_registration", "province_conflict"} for item in events)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("records", type=Path, help="normalized records JSONL for the current AESAN snapshot")
    parser.add_argument("output", type=Path, help="private event JSONL under UEC_REAL_PREVIEW_RUNS_ROOT")
    parser.add_argument("--database-url", default=os.environ.get("UEC_DATABASE_URL"))
    parser.add_argument("--limit", type=int, default=MAX_LOOKUPS)
    args = parser.parse_args()
    if not args.database_url:
        parser.error("--database-url or UEC_DATABASE_URL is required")
    try:
        counts = acquire(args.database_url, args.records, args.output, limit=args.limit)
    except Exception as error:
        print(f"acquisition_failed: {type(error).__name__}")
        return 1
    print("source=es.locations official_lookup_requests=" + str(counts["requests"]) + " " +
          " ".join(f"{key}={value}" for key, value in counts.items() if key != "requests"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
