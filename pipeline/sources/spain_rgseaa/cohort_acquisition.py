"""Resumable, paced acquisition of AESAN municipality evidence for a full snapshot."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

import psycopg

from .location_enrichment import (
    DEFAULT_REQUEST_INTERVAL_SECONDS,
    FINDER_URL,
    MAX_LOOKUPS,
    SOURCE_ID,
    UnsupportedAesanProvinceError,
    append_private_events,
    enrich_records,
    fetch_filtered_export,
    match_official_result,
    registration_components,
    registration_key_sha256,
    same_official_province,
)

DATABASE = "uec_launch_sources_test_20261025"


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_records(path: Path) -> tuple[dict[str, dict[str, Any]], str]:
    if not path.is_file() or path.is_symlink():
        raise ValueError("normalized_records_file_invalid")
    records: dict[str, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                raise ValueError("normalized_records_json_invalid") from None
            if not isinstance(record, dict) or record.get("source_id") != SOURCE_ID:
                raise ValueError("normalized_records_source_mismatch")
            key = record.get("source_record_key")
            if not isinstance(key, str) or key in records:
                raise ValueError("normalized_records_key_invalid_or_duplicate")
            records[key] = record
    return records, _file_sha256(path)


def _processed_keys(path: Path) -> set[str]:
    if not path.exists():
        return set()
    if path.is_symlink() or not path.is_file():
        raise ValueError("event_checkpoint_invalid")
    processed: set[str] = set()
    with path.open("r", encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                raise ValueError("event_checkpoint_json_invalid") from None
            if (not isinstance(event, dict) or event.get("event_type") != "official_locality_lookup"
                    or event.get("source_id") != SOURCE_ID
                    or not isinstance(event.get("source_record_key"), str)):
                raise ValueError("event_checkpoint_schema_invalid")
            processed.add(event["source_record_key"])
    return processed


def _retain_bulk_export(output_path: Path, approved_root: Path, group: dict[str, Any],
                        export: dict[str, Any], normalized_sha256: str) -> tuple[bool, int]:
    """Retain one private, bounded raw export plus scope/hash provenance when available."""
    raw = export.get("_raw_export_bytes")
    if raw is None:
        return False, 0
    if not isinstance(raw, bytes) or len(raw) > 2 * 1024 * 1024:
        raise ValueError("bulk_export_artifact_invalid_or_over_size")
    response_sha256 = export.get("response_sha256")
    result_page_sha256 = export.get("result_page_sha256")
    if (not isinstance(response_sha256, str) or len(response_sha256) != 64
            or hashlib.sha256(raw).hexdigest() != response_sha256
            or not isinstance(result_page_sha256, str) or len(result_page_sha256) != 64):
        raise ValueError("bulk_export_artifact_checksum_invalid")
    artifact_dir = (output_path.parent / "bulk-export-artifacts").resolve()
    if not artifact_dir.is_relative_to(approved_root):
        raise ValueError("bulk_export_artifact_outside_approved_root")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    scope = f"{group['province']}\x1f{group['sector']}"
    scope_hash = hashlib.sha256(scope.encode("utf-8")).hexdigest()[:16]
    stem = f"{scope_hash}-{response_sha256}"
    raw_path = artifact_dir / f"{stem}.xls"
    metadata_path = artifact_dir / f"{stem}.json"
    if raw_path.is_symlink() or metadata_path.is_symlink():
        raise ValueError("bulk_export_artifact_symlink_invalid")
    metadata = {
        "source_id": SOURCE_ID,
        "source_url": FINDER_URL,
        "query_scope": {"province": group["province"], "sector": str(group["sector"]),
                        "registration_number": "blank",
                        "official_province_option": export.get("query_province_option"),
                        "official_province_option_value": export.get("query_province_option_value")},
        "retrieved_at_utc": export.get("retrieved_at"),
        "response_kind": export.get("response_kind", "official_excel_export"),
        "response_sha256": response_sha256,
        "result_page_sha256": result_page_sha256,
        "response_byte_size": len(raw),
        "content_type": export.get("content_type"),
        "normalized_records_sha256": normalized_sha256,
    }
    metadata_bytes = (json.dumps(metadata, ensure_ascii=False, sort_keys=True,
                                 separators=(",", ":")) + "\n").encode("utf-8")
    retained = False
    if raw_path.exists():
        if _file_sha256(raw_path) != response_sha256:
            raise ValueError("bulk_export_artifact_existing_checksum_mismatch")
    else:
        temporary = raw_path.with_suffix(raw_path.suffix + ".tmp")
        temporary.write_bytes(raw)
        os.replace(temporary, raw_path)
        retained = True
    if metadata_path.exists():
        try:
            existing_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            raise ValueError("bulk_export_metadata_existing_invalid") from None
        stable_fields = ("source_id", "source_url", "query_scope", "response_kind",
                         "response_sha256", "response_byte_size", "content_type",
                         "normalized_records_sha256")
        if any(existing_metadata.get(field) != metadata.get(field) for field in stable_fields):
            raise ValueError("bulk_export_metadata_existing_conflict")
    else:
        temporary = metadata_path.with_suffix(metadata_path.suffix + ".tmp")
        temporary.write_bytes(metadata_bytes)
        os.replace(temporary, metadata_path)
    return retained, len(raw) if retained else 0


def _eligible_representatives(database_url: str, normalized_sha256: str,
                              connect: Any) -> list[tuple[str, str]]:
    with connect(database_url, options="-c default_transaction_read_only=on") as connection:
        with connection.transaction():
            connection.execute("SET TRANSACTION READ ONLY")
            if connection.execute("SELECT current_database()").fetchone()[0] != DATABASE:
                raise RuntimeError("database_identity_invalid")
            manifest = connection.execute("""
                WITH latest AS (
                    SELECT snapshot_sha256 FROM real_preview.source_preview_runs
                     WHERE source_id=%s ORDER BY created_at DESC,run_id DESC LIMIT 1
                )
                SELECT manifest.normalized_sha256
                  FROM real_preview.source_manifests manifest JOIN latest USING(snapshot_sha256)
                 WHERE manifest.source_id=%s
            """, (SOURCE_ID, SOURCE_ID)).fetchone()
            if not manifest or normalized_sha256 != manifest[0].strip():
                raise RuntimeError("normalized_records_not_latest_snapshot")
            return connection.execute("""
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
            """, (SOURCE_ID, SOURCE_ID)).fetchall()


def acquire(database_url: str, records_path: Path, output_path: Path, *,
            limit: int = 1000, max_seconds: float = 3600,
            request_interval_seconds: float = DEFAULT_REQUEST_INTERVAL_SECONDS,
            lookup: Any = None, connect: Any = None) -> dict[str, Any]:
    """Append event checkpoints as batches complete; reruns skip completed source keys."""
    if not 1 <= limit <= 10000:
        raise ValueError("limit_must_be_between_1_and_10000")
    if not 1 <= max_seconds <= 21600:
        raise ValueError("max_seconds_must_be_between_1_and_21600")
    if not 0 <= request_interval_seconds <= 60:
        raise ValueError("request_interval_must_be_between_0_and_60")
    approved_root = os.environ.get("UEC_REAL_PREVIEW_RUNS_ROOT")
    if not approved_root:
        raise ValueError("UEC_REAL_PREVIEW_RUNS_ROOT_required_for_generated_artifacts")
    approved_root_path = Path(approved_root).resolve()
    output_path = output_path.resolve()
    if not output_path.is_relative_to(approved_root_path):
        raise ValueError("event_output_must_be_under_UEC_REAL_PREVIEW_RUNS_ROOT")

    records, normalized_sha256 = _load_records(records_path)
    connect = connect or psycopg.connect
    candidates = _eligible_representatives(database_url, normalized_sha256, connect)
    processed = _processed_keys(output_path)
    queue: list[dict[str, Any]] = []
    for registration, record_key in candidates:
        if record_key in processed:
            continue
        record = records.get(record_key)
        if record is None:
            raise RuntimeError("latest_snapshot_representative_missing_from_normalized_records")
        values = record.get("source_values") or {}
        normalized = record.get("normalized") or {}
        source_registration = values.get("N_RGSEAA") or normalized.get("establishment_id")
        if registration_key_sha256(str(source_registration)) != registration_key_sha256(str(registration)):
            raise RuntimeError("latest_snapshot_registration_identity_mismatch")
        queue.append(record)

    started = time.monotonic()
    attempted = 0
    outcomes: Counter[str] = Counter()
    while queue and attempted < limit and time.monotonic() - started < max_seconds:
        count = min(MAX_LOOKUPS, limit - attempted, len(queue))
        batch = queue[:count]
        if lookup is None:
            events = enrich_records(batch, limit=count,
                                    request_interval_seconds=request_interval_seconds)
        else:
            events = enrich_records(batch, limit=count, lookup=lookup,
                                    request_interval_seconds=request_interval_seconds)
        append_private_events(output_path, events)
        for event in events:
            outcomes[str(event.get("outcome", "unknown"))] += 1
        del queue[:count]
        attempted += len(events)

    return {
        "source_id": SOURCE_ID,
        "eligible_candidates": len(candidates),
        "previously_checkpointed": len(processed),
        "pending_before_run": len(queue) + attempted,
        "requests_this_run": attempted,
        "remaining_after_run": len(queue),
        "outcomes_this_run": dict(sorted(outcomes.items())),
        "request_interval_seconds": request_interval_seconds,
        "elapsed_seconds": round(time.monotonic() - started, 2),
        "external_provider_calls": 0,
        "publication": "none",
    }


def acquire_bulk(database_url: str, records_path: Path, output_path: Path, *,
                 group_limit: int = 10000, max_seconds: float = 3600,
                 request_interval_seconds: float = DEFAULT_REQUEST_INTERVAL_SECONDS,
                 lookup: Any = None, connect: Any = None) -> dict[str, Any]:
    """Recover locality rows with AESAN's ordinary province/sector Excel export.

    Each query leaves the registration number blank and follows the form's
    published Excel control. Export results are exact-joined to the current
    source registration keys, then only minimized locality events are kept.
    """
    if not 1 <= group_limit <= 10000:
        raise ValueError("group_limit_must_be_between_1_and_10000")
    if not 1 <= max_seconds <= 21600:
        raise ValueError("max_seconds_must_be_between_1_and_21600")
    if not 0 <= request_interval_seconds <= 60:
        raise ValueError("request_interval_must_be_between_0_and_60")
    approved_root = os.environ.get("UEC_REAL_PREVIEW_RUNS_ROOT")
    if not approved_root:
        raise ValueError("UEC_REAL_PREVIEW_RUNS_ROOT_required_for_generated_artifacts")
    approved_root_path = Path(approved_root).resolve()
    output_path = output_path.resolve()
    if not output_path.is_relative_to(approved_root_path):
        raise ValueError("event_output_must_be_under_UEC_REAL_PREVIEW_RUNS_ROOT")

    records, normalized_sha256 = _load_records(records_path)
    connect = connect or psycopg.connect
    candidates = _eligible_representatives(database_url, normalized_sha256, connect)
    processed = _processed_keys(output_path)
    pending_by_group: list[dict[str, Any]] = []
    for registration, record_key in candidates:
        if record_key in processed:
            continue
        record = records.get(record_key)
        if record is None:
            raise RuntimeError("latest_snapshot_representative_missing_from_normalized_records")
        values = record.get("source_values") or {}
        normalized = record.get("normalized") or {}
        source_registration = values.get("N_RGSEAA") or normalized.get("establishment_id")
        if registration_key_sha256(str(source_registration)) != registration_key_sha256(str(registration)):
            raise RuntimeError("latest_snapshot_registration_identity_mismatch")
        sector = registration_components(str(source_registration))
        province = normalized.get("province") or values.get("Provincia")
        if sector is None or not isinstance(province, str) or not province.strip():
            raise RuntimeError("latest_snapshot_search_scope_invalid")
        pending_by_group.append({"record": record, "sector": sector[0], "province": province.strip()})

    grouped: list[dict[str, Any]] = []
    for item in pending_by_group:
        group = next((existing for existing in grouped
                      if existing["sector"] == item["sector"]
                      and same_official_province(existing["province"], item["province"])), None)
        if group is None:
            group = {"sector": item["sector"], "province": item["province"], "records": []}
            grouped.append(group)
        group["records"].append(item["record"])

    all_groups = grouped
    total_groups = len(all_groups)
    grouped = all_groups[:group_limit]
    started = time.monotonic()
    outcomes: Counter[str] = Counter()
    completed_groups = 0
    unsupported_groups = 0
    unsupported_candidates = 0
    unsupported_provinces: set[str] = set()
    requests = 0
    response_bytes = 0
    raw_exports_retained = 0
    raw_export_bytes_retained = 0
    completed_group_ids: set[int] = set()
    lookup_fn = lookup or fetch_filtered_export
    for group in grouped:
        if requests and request_interval_seconds:
            # Pace the next ordinary form GET after the previous export POST.
            time.sleep(request_interval_seconds)
        if time.monotonic() - started >= max_seconds:
            break
        try:
            if lookup is None:
                export = lookup_fn(group["province"], group["sector"],
                                   request_interval_seconds=request_interval_seconds,
                                   retain_raw_export=True)
            else:
                export = lookup_fn(group["province"], group["sector"],
                                   request_interval_seconds=request_interval_seconds)
        except UnsupportedAesanProvinceError as error:
            # A source label such as "Bilbao" is not a province alias. Keep
            # its group pending, report it, and continue valid groups once.
            unsupported_groups += 1
            unsupported_candidates += len(group["records"])
            unsupported_provinces.add(group["province"])
            requests += error.http_requests
            response_bytes += error.response_bytes
            continue
        result_url = export["result_url"]
        request_url = export["request_url"]
        events = [match_official_result(record, export.get("results", []),
                    retrieved_at=export["retrieved_at"], result_url=result_url,
                    request_url=request_url) for record in group["records"]]
        for event in events:
            if isinstance(export.get("response_sha256"), str):
                event["bulk_export_response_sha256"] = export["response_sha256"]
            if isinstance(export.get("result_page_sha256"), str):
                event["bulk_export_result_page_sha256"] = export["result_page_sha256"]
            event["bulk_export_query_scope"] = {
                "province": group["province"], "sector": str(group["sector"]),
                "registration_number": "blank",
                "province_option": export.get("query_province_option"),
                "province_option_value": export.get("query_province_option_value"),
            }
        retained, retained_bytes = _retain_bulk_export(
            output_path, approved_root_path, group, export, normalized_sha256)
        raw_exports_retained += int(retained)
        raw_export_bytes_retained += retained_bytes
        append_private_events(output_path, events)
        outcomes.update(str(event.get("outcome", "unknown")) for event in events)
        completed_groups += 1
        completed_group_ids.add(id(group))
        requests += int(export.get("http_requests", 3))
        response_bytes += int(export.get("response_bytes", 0))

    processed_this_run = sum(outcomes.values())
    pending_candidate_events = sum(len(group["records"]) for group in all_groups
                                   if id(group) not in completed_group_ids)
    return {
        "source_id": SOURCE_ID,
        "eligible_candidates": len(candidates),
        "previously_checkpointed": len(processed),
        "filter_queries_this_run": completed_groups,
        "http_requests_this_run": requests,
        "filter_groups_completed": completed_groups,
        "filter_groups_pending": max(0, total_groups - completed_groups),
        "unsupported_groups_this_run": unsupported_groups,
        "unsupported_candidates_this_run": unsupported_candidates,
        "unsupported_province_labels_this_run": sorted(unsupported_provinces),
        "candidate_events_written": processed_this_run,
        "candidate_events_pending": pending_candidate_events,
        "outcomes_this_run": dict(sorted(outcomes.items())),
        "export_response_bytes": response_bytes,
        "raw_exports_retained": raw_exports_retained,
        "raw_export_bytes_retained": raw_export_bytes_retained,
        "request_interval_seconds": request_interval_seconds,
        "elapsed_seconds": round(time.monotonic() - started, 2),
        "external_provider_calls": 0,
        "publication": "none",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("records", type=Path, help="normalized records JSONL for the current AESAN snapshot")
    parser.add_argument("output", type=Path, help="append-only event JSONL under UEC_REAL_PREVIEW_RUNS_ROOT")
    parser.add_argument("--database-url", default=os.environ.get("UEC_DATABASE_URL"))
    parser.add_argument("--limit", type=int, default=10000,
                        help="maximum province/sector filter groups this run")
    parser.add_argument("--max-seconds", type=float, default=3600,
                        help="wall-clock budget; completed batches remain checkpointed")
    parser.add_argument("--request-interval-seconds", type=float,
                        default=DEFAULT_REQUEST_INTERVAL_SECONDS)
    parser.add_argument("--strategy", choices=("bulk", "individual"), default="bulk",
                        help="bulk follows AESAN's ordinary province/sector Excel export")
    args = parser.parse_args()
    if not args.database_url:
        parser.error("--database-url or UEC_DATABASE_URL is required")
    try:
        if args.strategy == "bulk":
            result = acquire_bulk(args.database_url, args.records, args.output,
                                  group_limit=args.limit, max_seconds=args.max_seconds,
                                  request_interval_seconds=args.request_interval_seconds)
        else:
            result = acquire(args.database_url, args.records, args.output, limit=args.limit,
                             max_seconds=args.max_seconds,
                             request_interval_seconds=args.request_interval_seconds)
    except Exception as error:
        print(f"acquisition_failed: {type(error).__name__}")
        return 1
    print("source=es.locations " + " ".join(f"{key}={value}" for key, value in result.items()
                                             if key not in {"source_id", "outcomes_this_run"}))
    for outcome, count in result["outcomes_this_run"].items():
        print(f"outcome_{outcome}={count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
