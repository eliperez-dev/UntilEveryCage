"""Export current private facility graph handoffs from a clone, read-only.

The output contains sensitive normalized/source payloads and must be written
only below ignored private staging storage. Credentials are supplied through a
process environment variable and are never included in arguments or reports.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

import psycopg

from pipeline.common.graph_candidate import build_graph_candidate
from pipeline.common.graph_candidates import build_identifier_graph_candidate
from pipeline.common.graph_source_mapping import location_role, name_assertions, source_identifier
from pipeline.contracts.graph_candidate_handoff import canonical_json_bytes
from pipeline.contracts.graph_candidate_handoff import validate_graph_candidate


RETAINED_FACILITY_SOURCES = (
    "fr.dgal.section-i", "fr.dgal.section-ii",
)


def _read_release_scope(path: Path) -> tuple[str, list[str]]:
    release = json.loads(path.read_text(encoding="utf-8"))
    release_id = release.get("release_id")
    source_ids = release.get("source_ids")
    if not isinstance(release_id, str) or not release_id:
        raise ValueError("release manifest release_id is missing")
    if not isinstance(source_ids, list) or not all(isinstance(item, str) for item in source_ids):
        raise ValueError("release manifest source_ids are malformed")
    if len(source_ids) != 14:
        raise ValueError("expected the approved 14-source release scope")
    return release_id, sorted(set(source_ids))


def _source_row(record: dict[str, Any], source_row: int) -> dict[str, Any]:
    normalized = record.get("normalized")
    if not isinstance(normalized, dict):
        raise ValueError("normalized source context missing")
    return {
        "source_id": record["source_id"],
        "source_row": source_row,
        "source_record_key": record["source_record_key"],
        "source_values": record.get("source_values") if isinstance(record.get("source_values"), dict) else {},
        "normalized": normalized,
    }


def _manifest(source_id: str, path: Path, digest: str, counts: Counter[str], locations: Counter[str]) -> dict[str, Any]:
    return {
        "schema_version": "private-graph-candidate-batch-v1",
        "contract_version": "graph-candidate-handoff-v1",
        "source_id": source_id,
        "source_ids": [source_id],
        "candidate_count": counts["candidate_rows"],
        "candidate_rows": counts["candidate_rows"],
        "facility_identifier_candidates": counts["facility_identifier_candidates"],
        "organization_identifier_candidates": counts["organization_identifier_candidates"],
        "name_assertion_candidates": counts["name_assertion_candidates"],
        "location_role_counts": dict(sorted(locations.items())),
        "business_contact_candidates": 0,
        "quarantined_source_rows": counts["skipped_rows"],
        "records_sha256": digest,
        "storage_state": "private",
        "privacy_status": "pending",
        "review_state": "review_required",
        "publication_status": "not_eligible",
        "release_id": None,
        "auto_merge": False,
        "row_payloads_included": True,
        "source_row_semantics": "deterministic ordinal by source_record_key; native source row number unavailable in retained clone",
        "skipped_rows_by_reason": dict(sorted((key, value) for key, value in counts.items() if key.startswith("skipped:"))),
    }


def _write_source(rows: Iterable[tuple[Any, ...]], output_root: Path, *, scope: str) -> dict[str, Any]:
    summary: dict[str, Any] = {"scope": scope, "sources": {}, "total_candidates": 0}
    current_source: str | None = None
    handle = None
    path: Path | None = None
    digest = hashlib.sha256()
    counts: Counter[str] = Counter()
    locations: Counter[str] = Counter()
    source_row = 0

    def close_source() -> None:
        nonlocal handle, current_source, path, digest, counts, locations
        if handle is None or current_source is None or path is None:
            return
        handle.close()
        (path.parent / "manifest.json").write_text(
            json.dumps(_manifest(current_source, path, digest.hexdigest(), counts, locations),
                       ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        summary["sources"][current_source] = dict(counts)
        summary["total_candidates"] += counts["candidate_rows"]
        handle = None
        current_source = None
        path = None
        digest = hashlib.sha256()
        counts = Counter()
        locations = Counter()

    for source_id, key, raw_fields, artifact_sha, observed_at in rows:
        if source_id != current_source:
            close_source()
            current_source = str(source_id)
            source_root = output_root / current_source / "graph-candidates"
            source_root.mkdir(parents=True, exist_ok=True)
            path = source_root / "graph-candidates.jsonl"
            handle = path.open("w", encoding="utf-8", newline="\n")
            source_row = 0
        source_row += 1
        if not isinstance(raw_fields, dict) or not isinstance(raw_fields.get("normalized"), dict):
            counts["skipped_rows"] += 1
            counts["skipped:normalized_missing"] += 1
            continue
        normalized = raw_fields["normalized"]
        if not source_identifier(str(source_id), normalized):
            counts["skipped_rows"] += 1
            counts["skipped:typed_identifier_missing"] += 1
            continue
        source_record = _source_row({
            "source_id": str(source_id), "source_record_key": str(key),
            "source_values": raw_fields.get("source_values", {}), "normalized": normalized,
        }, source_row)
        effective_time = observed_at.isoformat() if hasattr(observed_at, "isoformat") else str(observed_at or "unknown-observation-date")
        if source_id == "it.853-2004":
            typed_id = source_identifier(str(source_id), normalized)
            raw_source_values = source_record["source_values"]
            vat = raw_source_values.get("p_iva") if isinstance(raw_source_values, dict) else None
            candidate = build_identifier_graph_candidate(
                source_id=str(source_id), source_record_key=str(key), source_values=raw_source_values,
                facility_identifier=(typed_id["identifier_type"], typed_id["value"]) if typed_id else None,
                organization_identifier=None,
                organization_identifiers=[("italian_vat", vat)] if isinstance(vat, str) and vat.strip() else [],
                observed_at=effective_time, source_row=source_row,
                artifact_sha256=str(artifact_sha).strip() if artifact_sha else None,
                signal_bundle=([{"kind": "source_identifier_cooccurrence", "identifier_types": ["italian_vat"], "connection_type": "exact"}] if isinstance(vat, str) and vat.strip() else None),
                normalized_values=normalized, name_assertions=name_assertions(str(source_id), normalized),
                location_role=location_role(str(source_id), normalized),
            )
        else:
            candidate = build_graph_candidate(
                source_record,
                artifact_sha256=str(artifact_sha).strip() if artifact_sha else None,
                observed_at=effective_time,
            )
        validate_graph_candidate(candidate)
        payload = canonical_json_bytes(candidate)
        handle.write(payload.decode("utf-8"))
        digest.update(payload)
        counts["candidate_rows"] += 1
        counts["facility_identifier_candidates"] += 1
        counts["organization_identifier_candidates"] += len(candidate.get("organizations", []))
        counts["name_assertion_candidates"] += len(candidate.get("name_assertions", []))
        locations[candidate.get("location_role", "unknown")] += 1
    close_source()
    return summary


def export_clone(database_url: str, release_manifest: Path, output_root: Path) -> dict[str, Any]:
    release_id, release_sources = _read_release_scope(release_manifest)
    staging_root = (Path.cwd() / "data" / "staging").resolve()
    output_root = output_root.resolve()
    try:
        output_root.relative_to(staging_root)
    except ValueError as exc:
        raise ValueError("private handoff output must remain under ignored data/staging") from exc
    output_root.mkdir(parents=True, exist_ok=True)
    connection = psycopg.connect(database_url)
    try:
        connection.execute("SET TRANSACTION READ ONLY")
        actual_db = connection.execute("SELECT current_database()").fetchone()[0]
        if actual_db != "uec_graph_repair_test_20261022":
            raise ValueError("refusing source export from an unapproved database")
        release_rows = connection.cursor(name="uec_release_graph_export")
        release_rows.execute("""
            SELECT sr.source_id, sr.source_record_key, sr.raw_fields, ra.sha256, o.observed_at
            FROM uec.release_members rm
            JOIN uec.observations o ON o.observation_id = rm.observation_id
            JOIN uec.source_records sr ON sr.source_record_id = o.source_record_id
            LEFT JOIN uec.raw_artifacts ra ON ra.artifact_id = sr.artifact_id
            WHERE rm.release_id = %s AND sr.source_id = ANY(%s)
            ORDER BY sr.source_id, sr.source_record_key, o.observed_at, o.observation_id
        """, (release_id, release_sources))
        release_result = _write_source(release_rows, output_root / "released", scope="approved-release-membership")
        private_rows = connection.cursor(name="uec_private_graph_export")
        private_rows.execute("""
            WITH ranked AS (
                SELECT sr.source_id, sr.source_record_key, sr.raw_fields, ra.sha256,
                       sr.parsed_at, ROW_NUMBER() OVER (
                           PARTITION BY sr.source_id, sr.source_record_key
                           ORDER BY sr.parsed_at DESC, sr.source_record_id DESC
                       ) AS version_rank
                FROM uec.source_records sr
                LEFT JOIN uec.raw_artifacts ra ON ra.artifact_id = sr.artifact_id
                WHERE sr.source_id = ANY(%s)
            )
            SELECT source_id, source_record_key, raw_fields, sha256, parsed_at
            FROM ranked WHERE version_rank = 1 AND raw_fields ? 'normalized'
            ORDER BY source_id, source_record_key
        """, [list(RETAINED_FACILITY_SOURCES)])
        private_result = _write_source(private_rows, output_root / "retained-private", scope="latest-current-source-record-per-native-key")
        connection.rollback()
    finally:
        connection.close()
    return {
        "schema_version": "private-graph-corpus-export-v1",
        "database": "uec_graph_repair_test_20261022",
        "release_id": release_id,
        "release_source_count": len(release_sources),
        "release_source_records_expected": 69220,
        "release": release_result,
        "retained_private": private_result,
        "external_retained_families": {
            "fr.georisques.icpe.animal": "requires existing retained ICPE handoff under staging; not in clone source_records",
            "gb.scot.marine.aquaculture": "requires existing retained Scotland handoff under staging; not in clone source_records",
            "us.aphis.annual-reports": "evidence-event handoff is owned by APHIS evidence lane",
            "us.inspections": "evidence-event handoff is owned by APHIS evidence lane",
        },
        "privacy": {"private_rows_written_to_ignored_output": True, "rows_emitted_to_stdout": False, "database_writes": False, "publication_authorized": False},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url-env", default="UEC_GRAPH_EXPORT_URL")
    parser.add_argument("--release-manifest", required=True)
    parser.add_argument("--output-root", required=True)
    args = parser.parse_args()
    url = os.environ.get(args.database_url_env)
    if not url:
        raise SystemExit("private graph export database environment variable is unavailable")
    report = export_clone(url, Path(args.release_manifest), Path(args.output_root))
    print(json.dumps(report, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
