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
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qsl, urlsplit

import psycopg

from pipeline.common.graph_candidate import build_graph_candidate
from pipeline.common.graph_candidates import build_identifier_graph_candidate
from pipeline.common.graph_source_mapping import (
    additional_source_identifiers, location_role, name_assertions,
    operator_asserted, organization_identifiers, source_identifier,
)
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


def _source_urls() -> dict[str, str]:
    registry_path = Path("pipeline/source_registry.json")
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    return {
        item["source_id"]: item["url"]
        for item in registry.get("sources", [])
        if isinstance(item, dict) and isinstance(item.get("source_id"), str)
        and isinstance(item.get("url"), str) and item["url"]
    }


COUNTRY_BY_SOURCE = {
    "au.npi.facilities": "AU", "au.sa.epa.licensed-activities": "AU",
    "be.locations": "BE", "br.sif.registered": "BR", "ca.ontario.meat-plants": "CA",
    "dk.smiley": "DK", "es.cat.feed-sandach": "ES",
    "fsa_approved_establishments": "GB", "fss_approved_establishments": "GB",
    "it.1069-2009": "IT", "it.853-2004": "IT", "nl.nvwa.approved-food": "NL",
    "us.aphis": "US", "us.fsis": "US", "fr.dgal.section-i": "FR",
    "fr.dgal.section-ii": "FR",
    "de.locations": "DE", "es.locations": "ES", "fr.georisques.icpe.animal": "FR",
    "mx.locations": "MX", "nz.locations": "NZ",
}


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


def _manifest(source_id: str, path: Path, digest: str, counts: Counter[str], locations: Counter[str],
              *, artifact_sha: str, retrieved_at: str, source_url: str, country_code: str) -> dict[str, Any]:
    return {
        "schema_version": "private-graph-candidate-batch-v1",
        "contract_version": "graph-candidate-handoff-v1",
        "source_id": source_id,
        "source_ids": [source_id],
        "source_url": source_url,
        "country_code": country_code,
        "retrieved_at_utc": retrieved_at,
        "checksum_sha256": artifact_sha,
        "source_artifact_sha256": artifact_sha,
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


def _write_source(rows: Iterable[tuple[Any, ...]], output_root: Path, *, scope: str,
                  source_urls: dict[str, str]) -> dict[str, Any]:
    summary: dict[str, Any] = {"scope": scope, "sources": {}, "total_candidates": 0}
    current_source: str | None = None
    current_artifact_sha: str | None = None
    current_retrieved_at: str | None = None
    current_url: str | None = None
    current_country: str | None = None
    handle = None
    path: Path | None = None
    digest = hashlib.sha256()
    counts: Counter[str] = Counter()
    locations: Counter[str] = Counter()
    source_row = 0

    def close_source() -> None:
        nonlocal handle, current_source, current_artifact_sha, current_retrieved_at, current_url, current_country, path, digest, counts, locations
        if handle is None or current_source is None or path is None:
            return
        handle.close()
        (path.parent / "manifest.json").write_text(
            json.dumps(_manifest(current_source, path, digest.hexdigest(), counts, locations,
                                 artifact_sha=current_artifact_sha or "",
                                 retrieved_at=current_retrieved_at or "unknown",
                                 source_url=current_url or "unknown",
                                 country_code=current_country or COUNTRY_BY_SOURCE.get(current_source, "unknown")),
                       ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        source_counts = summary["sources"].setdefault(current_source, Counter())
        source_counts.update(counts)
        summary["total_candidates"] += counts["candidate_rows"]
        handle = None
        current_source = None
        current_artifact_sha = None
        current_retrieved_at = None
        current_url = None
        current_country = None
        path = None
        digest = hashlib.sha256()
        counts = Counter()
        locations = Counter()

    try:
        for source_id, key, raw_fields, source_values, artifact_sha, artifact_retrieved_at, observed_at in rows:
            artifact_sha = str(artifact_sha).strip() if artifact_sha else ""
            if not artifact_sha:
                raise ValueError(f"source artifact SHA is missing for {source_id}")
            if source_id != current_source or artifact_sha != current_artifact_sha:
                close_source()
                current_source = str(source_id)
                current_artifact_sha = artifact_sha
                current_retrieved_at = artifact_retrieved_at.isoformat() if hasattr(artifact_retrieved_at, "isoformat") else str(artifact_retrieved_at or "unknown")
                current_url = source_urls.get(current_source, "unknown")
                source_root = output_root / current_source / artifact_sha / "graph-candidates"
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
                "source_values": source_values if isinstance(source_values, dict) else {}, "normalized": normalized,
            }, source_row)
            if current_country is None:
                country = normalized.get("country_code")
                current_country = country if isinstance(country, str) and country else COUNTRY_BY_SOURCE.get(str(source_id), "unknown")
            effective_time = observed_at.isoformat() if hasattr(observed_at, "isoformat") else str(observed_at or "unknown-observation-date")
            if source_id in {"it.853-2004", "it.1069-2009"}:
                typed_id = source_identifier(str(source_id), normalized)
                raw_source_values = source_record["source_values"]
                business_ids = organization_identifiers(str(source_id), normalized, raw_source_values)
                candidate = build_identifier_graph_candidate(
                    source_id=str(source_id), source_record_key=str(key), source_values=raw_source_values,
                    facility_identifier=(typed_id["identifier_type"], typed_id["value"]) if typed_id else None,
                    organization_identifier=None,
                    organization_identifiers=[(item["identifier_type"], item["value"]) for item in business_ids],
                    observed_at=effective_time, source_row=source_row,
                    artifact_sha256=str(artifact_sha).strip() if artifact_sha else None,
                    signal_bundle=([{"kind": "source_identifier_cooccurrence", "identifier_types": [item["identifier_type"] for item in business_ids], "connection_type": "exact"}] if business_ids else None),
                    normalized_values=normalized, name_assertions=name_assertions(str(source_id), normalized, raw_source_values),
                    location_role=location_role(str(source_id), normalized, raw_source_values),
                    operator_asserted=operator_asserted(str(source_id), raw_source_values),
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
    except Exception:
        if handle is not None:
            handle.close()
        raise
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
    try:
        connection = psycopg.connect(database_url)
    except Exception:
        raise CandidateExportError("candidate_database_unavailable") from None
    try:
        connection.execute("SET TRANSACTION READ ONLY")
        actual_db = connection.execute("SELECT current_database()").fetchone()[0]
        if actual_db != "uec_graph_repair_test_20261022":
            raise ValueError("refusing source export from an unapproved database")
        source_urls = _source_urls()
        release_rows = connection.cursor(name="uec_release_graph_export")
        release_rows.execute("""
            WITH ranked_current AS (
                SELECT current.source_id, current.source_record_key, current.raw_fields,
                       current_ra.sha256, ROW_NUMBER() OVER (
                           PARTITION BY current.source_id, current.source_record_key
                           ORDER BY current.parsed_at DESC, current.source_record_id DESC
                       ) AS version_rank
                FROM uec.source_records current
                LEFT JOIN uec.raw_artifacts current_ra ON current_ra.artifact_id = current.artifact_id
                WHERE current.source_id = ANY(%s)
            )
            SELECT sr.source_id, sr.source_record_key, sr.raw_fields,
                   CASE WHEN jsonb_typeof(sr.raw_fields->'source_values') = 'object'
                        THEN sr.raw_fields->'source_values'
                        ELSE COALESCE(current.raw_fields->'source_values', '{}'::jsonb) END AS source_values,
                   ra.sha256, ra.retrieved_at, o.observed_at
            FROM uec.release_members rm
            JOIN uec.observations o ON o.observation_id = rm.observation_id
            JOIN uec.source_records sr ON sr.source_record_id = o.source_record_id
            LEFT JOIN uec.raw_artifacts ra ON ra.artifact_id = sr.artifact_id
            LEFT JOIN ranked_current current
              ON current.source_id = sr.source_id
             AND current.source_record_key = sr.source_record_key
             AND current.sha256 = ra.sha256
             AND current.version_rank = 1
            WHERE rm.release_id = %s AND sr.source_id = ANY(%s)
            ORDER BY sr.source_id, ra.sha256, sr.source_record_key, o.observed_at, o.observation_id
        """, (release_sources, release_id, release_sources))
        release_result = _write_source(release_rows, output_root / "released", scope="approved-release-membership", source_urls=source_urls)
        private_rows = connection.cursor(name="uec_private_graph_export")
        private_rows.execute("""
            WITH ranked AS (
                SELECT sr.source_id, sr.source_record_key, sr.raw_fields,
                       COALESCE(sr.raw_fields->'source_values', '{}'::jsonb) AS source_values,
                       ra.sha256, ra.retrieved_at,
                       sr.parsed_at, ROW_NUMBER() OVER (
                           PARTITION BY sr.source_id, sr.source_record_key
                           ORDER BY sr.parsed_at DESC, sr.source_record_id DESC
                       ) AS version_rank
                FROM uec.source_records sr
                LEFT JOIN uec.raw_artifacts ra ON ra.artifact_id = sr.artifact_id
                WHERE sr.source_id = ANY(%s)
            )
            SELECT source_id, source_record_key, raw_fields, source_values, sha256, retrieved_at, parsed_at
            FROM ranked
            WHERE version_rank = 1 AND raw_fields ? 'normalized'
              AND NOT EXISTS (
                  SELECT 1
                  FROM uec.release_members rm
                  JOIN uec.observations released_observation ON released_observation.observation_id = rm.observation_id
                  JOIN uec.source_records released_record ON released_record.source_record_id = released_observation.source_record_id
                  WHERE rm.release_id = %s
                    AND released_record.source_id = ranked.source_id
                    AND released_record.source_record_key = ranked.source_record_key
              )
            ORDER BY source_id, sha256, source_record_key
        """, [list(RETAINED_FACILITY_SOURCES), release_id])
        private_result = _write_source(private_rows, output_root / "retained-private", scope="latest-current-source-record-per-native-key", source_urls=source_urls)
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


class CandidateExportError(ValueError):
    """Safe failure for the explicit frozen-candidate export path."""

    def __init__(self, category: str):
        super().__init__(category)
        self.category = category


_CANDIDATE_DATABASE = "uec_country_release_test_20261027"
_CANDIDATE_RELEASE = "release-2026-10-27-r2"
_CANDIDATE_FREEZE_RELEASE = "v0-candidate-country-2026-10-27"
_CANDIDATE_FREEZE_BINDING = "release-2026-10-27"

_CANDIDATE_MEMBER_SQL = """
SELECT member.release_id, member.facility_id::text, member.observation_id::text,
       observation.source_record_id::text, record.source_id, record.artifact_id::text,
       artifact.sha256, taxonomy.contract,
       record.source_record_key, record.raw_fields,
       CASE WHEN jsonb_typeof(record.raw_fields->'source_values') = 'object'
            THEN record.raw_fields->'source_values' ELSE '{}'::jsonb END AS source_values,
       artifact.retrieved_at, observation.observed_at,
       restricted.source_record_id IS NOT NULL AS is_restricted
FROM uec.release_members member
JOIN uec.observations observation ON observation.observation_id=member.observation_id
JOIN uec.source_records record ON record.source_record_id=observation.source_record_id
JOIN uec.raw_artifacts artifact ON artifact.artifact_id=record.artifact_id
LEFT JOIN uec.public_access_restricted restricted ON restricted.source_record_id=record.source_record_id
LEFT JOIN LATERAL (
    SELECT jsonb_build_object(
        'taxonomy_version', assignment_set.taxonomy_version,
        'crosswalk_version', assignment_set.crosswalk_version,
        'ruleset_version', assignment_set.ruleset_version,
        'display_category', assignment_set.display_category,
        'assignments', COALESCE(jsonb_agg(jsonb_build_object(
            'assignment_ordinal', assignment.assignment_ordinal,
            'primary_key', assignment.primary_key, 'leaf_key', assignment.leaf_key,
            'leaf_label', assignment.leaf_label,
            'source_code_reference', assignment.source_code_reference,
            'source_label_reference', assignment.source_label_reference,
            'source_code', assignment.source_code, 'source_label', assignment.source_label,
            'mapping_method', assignment.mapping_method, 'mapping_status', assignment.mapping_status
        ) ORDER BY assignment.assignment_ordinal), '[]'::jsonb)
    ) AS contract
    FROM uec.observation_taxonomy_assignment_sets assignment_set
    LEFT JOIN uec.observation_taxonomy_assignments assignment USING (assignment_set_id)
    WHERE assignment_set.observation_id=observation.observation_id
      AND assignment_set.source_record_id=observation.source_record_id
      AND assignment_set.source_id=record.source_id
      AND assignment_set.artifact_id=record.artifact_id
      AND NOT EXISTS (
          SELECT 1 FROM uec.observation_taxonomy_assignment_sets newer
          WHERE newer.observation_id=assignment_set.observation_id
            AND newer.taxonomy_version=assignment_set.taxonomy_version
            AND (newer.created_at,newer.assignment_set_id)>(assignment_set.created_at,assignment_set.assignment_set_id)
      )
    GROUP BY assignment_set.assignment_set_id
    ORDER BY assignment_set.created_at DESC, assignment_set.assignment_set_id DESC
    LIMIT 1
) taxonomy ON true
WHERE member.release_id=%s
ORDER BY member.release_id, member.facility_id, member.observation_id,
         observation.source_record_id, record.source_id, record.artifact_id
"""

_CANDIDATE_EXPORT_SQL = """
SELECT record.source_id, record.source_record_key, record.raw_fields,
       CASE WHEN jsonb_typeof(record.raw_fields->'source_values') = 'object'
            THEN record.raw_fields->'source_values' ELSE '{}'::jsonb END AS source_values,
       artifact.sha256, artifact.retrieved_at, observation.observed_at,
       restricted.source_record_id IS NOT NULL AS is_restricted
FROM uec.release_members member
JOIN uec.observations observation ON observation.observation_id=member.observation_id
JOIN uec.source_records record ON record.source_record_id=observation.source_record_id
JOIN uec.raw_artifacts artifact ON artifact.artifact_id=record.artifact_id
LEFT JOIN uec.public_access_restricted restricted ON restricted.source_record_id=record.source_record_id
WHERE member.release_id=%s
ORDER BY record.source_id, artifact.sha256, record.source_record_key,
         observation.observed_at, observation.observation_id
"""


def _candidate_paths(freeze_path: Path, review_path: Path, output_root: Path) -> tuple[dict[str, Any], dict[str, Any], Path]:
    reports_root = (Path.cwd() / "data" / "reports").resolve()
    staging_root = (Path.cwd() / "data" / "staging").resolve()
    try:
        for path in (freeze_path, review_path):
            resolved = path.resolve(strict=True)
            if path.is_symlink() or not resolved.is_file() or reports_root not in resolved.parents:
                raise CandidateExportError("candidate_control_file_invalid")
        freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
        review = json.loads(review_path.read_text(encoding="utf-8"))
    except CandidateExportError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise CandidateExportError("candidate_control_file_invalid") from None
    if not isinstance(freeze, dict) or not isinstance(review, dict):
        raise CandidateExportError("candidate_control_file_invalid")
    from pipeline.common.release_cohort_review import canonical_sha256
    expected_hashes = (review.get("freeze_sha256"), review.get("inventory_sha256"), review.get("member_sha256"))
    if (freeze.get("schema_version") != "v0-candidate-freeze-v1"
            or review.get("schema_version") != "uec-release-cohort-review-v1"
            or review.get("release_id") != _CANDIDATE_RELEASE
            or not isinstance(review.get("member_count"), int) or review["member_count"] < 1
            or any(not isinstance(value, str) or len(value) != 64
                   or any(character not in "0123456789abcdef" for character in value)
                   for value in expected_hashes)
            or not isinstance(freeze.get("inventory_sha256"), str)
            or len(freeze["inventory_sha256"]) != 64
            or freeze.get("release_id") != _CANDIDATE_FREEZE_RELEASE
            or review.get("freeze_sha256") != canonical_sha256({**freeze, "release_id": _CANDIDATE_FREEZE_BINDING})
            or review.get("inventory_sha256") != freeze.get("inventory_sha256")):
        raise CandidateExportError("candidate_control_hash_mismatch")
    output = output_root.resolve(strict=False)
    try:
        output.relative_to(staging_root)
    except ValueError:
        raise CandidateExportError("candidate_output_outside_staging") from None
    if output == staging_root or output.exists() or output_root.is_symlink() or not output.parent.is_dir():
        raise CandidateExportError("candidate_output_must_be_new")
    return freeze, review, output


def _validate_candidate_database_url(database_url: str, expected_database: str) -> None:
    try:
        parsed = urlsplit(database_url)
        routing = {key.lower() for key, _ in parse_qsl(parsed.query, keep_blank_values=True)}
    except ValueError:
        raise CandidateExportError("candidate_database_mismatch") from None
    if (parsed.scheme not in {"postgres", "postgresql"}
            or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
            or parsed.path.lstrip("/") != expected_database
            or routing.intersection({"host", "hostaddr", "service", "servicefile"})
            or expected_database != _CANDIDATE_DATABASE):
        raise CandidateExportError("candidate_database_mismatch")


def _member_payload(values: list[Any]) -> bytes:
    return (json.dumps(values, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _verify_candidate_export(output_root: Path, expected_groups: dict[tuple[str, str], int]) -> int:
    actual_groups: dict[tuple[str, str], int] = {}
    total_rows = 0
    manifests = sorted(output_root.rglob("manifest.json"))
    if len(manifests) != len(expected_groups):
        raise CandidateExportError("candidate_export_manifest_scope_mismatch")
    for manifest_path in manifests:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            raise CandidateExportError("candidate_export_manifest_invalid") from None
        source_id = manifest.get("source_id")
        artifact_sha = manifest.get("source_artifact_sha256")
        if (not isinstance(source_id, str) or not isinstance(artifact_sha, str)
                or len(artifact_sha) != 64 or manifest_path.parent.name != "graph-candidates"
                or manifest_path.parent.parent.name != artifact_sha
                or manifest_path.parent.parent.parent.name != source_id):
            raise CandidateExportError("candidate_export_manifest_invalid")
        group = (source_id, artifact_sha)
        if group not in expected_groups or group in actual_groups:
            raise CandidateExportError("candidate_export_manifest_scope_mismatch")
        records_path = manifest_path.parent / "graph-candidates.jsonl"
        digest = hashlib.sha256()
        row_count = 0
        try:
            with records_path.open("rb") as stream:
                for payload in stream:
                    if not payload.endswith(b"\n"):
                        raise CandidateExportError("candidate_export_record_invalid")
                    candidate = json.loads(payload.decode("utf-8"))
                    validate_graph_candidate(candidate)
                    if (candidate.get("source_id") != source_id
                            or not isinstance(candidate.get("source_record_key"), str)):
                        raise CandidateExportError("candidate_export_record_invalid")
                    digest.update(payload)
                    row_count += 1
        except CandidateExportError:
            raise
        except (OSError, UnicodeError, json.JSONDecodeError):
            raise CandidateExportError("candidate_export_record_invalid") from None
        if (row_count != expected_groups[group] or row_count != manifest.get("candidate_count")
                or digest.hexdigest() != manifest.get("records_sha256")):
            raise CandidateExportError("candidate_export_digest_or_count_mismatch")
        actual_groups[group] = row_count
        total_rows += row_count
    if actual_groups != expected_groups:
        raise CandidateExportError("candidate_export_manifest_scope_mismatch")
    return total_rows


def export_frozen_candidate(database_url: str, *, expected_database: str, release_id: str,
                            freeze_path: Path, review_path: Path, output_root: Path) -> dict[str, Any]:
    """Export only exact, unrestricted members of the assigned frozen candidate."""
    if release_id != _CANDIDATE_RELEASE:
        raise CandidateExportError("candidate_release_mismatch")
    _validate_candidate_database_url(database_url, expected_database)
    freeze, review, output = _candidate_paths(freeze_path, review_path, output_root)
    if review.get("release_id") != release_id:
        raise CandidateExportError("candidate_control_release_mismatch")
    selected = freeze.get("selected_sources")
    if not isinstance(selected, list) or not selected:
        raise CandidateExportError("candidate_freeze_scope_invalid")
    selected_ids = [item.get("source_id") for item in selected if isinstance(item, dict)]
    if (len(selected_ids) != len(selected) or not all(isinstance(item, str) and item for item in selected_ids)
            or len(set(selected_ids)) != len(selected_ids)):
        raise CandidateExportError("candidate_freeze_scope_invalid")
    frozen_sources = sorted(selected_ids)
    frozen_artifacts = {
        item["source_id"]: item.get("source_artifact_sha256")
        for item in selected
    }
    if any(not isinstance(value, str) or len(value) != 64 for value in frozen_artifacts.values()):
        raise CandidateExportError("candidate_freeze_scope_invalid")

    connection = psycopg.connect(database_url)
    try:
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        actual_db = connection.execute("SELECT current_database()").fetchone()[0]
        if actual_db != expected_database:
            raise CandidateExportError("candidate_database_mismatch")
        release = connection.execute(
            "SELECT status,profile,test_only,ruleset_version,summary FROM uec.releases WHERE release_id=%s",
            (release_id,),
        ).fetchone()
        if release is None:
            raise CandidateExportError("candidate_release_missing")
        status, profile, test_only, ruleset, summary = release
        summary = summary if isinstance(summary, dict) else {}
        summary_sources = summary.get("selected_sources")
        replacement_sources = summary.get("replacement_sources", summary_sources)
        if (status != "candidate" or profile != review.get("profile") or test_only is not False
                or ruleset != review.get("ruleset_version") or summary.get("candidate_only") is not True
                or summary.get("freeze_sha256") != review.get("freeze_sha256")
                or summary.get("inventory_sha256") != review.get("inventory_sha256")
                or not isinstance(summary_sources, list)
                or summary_sources != sorted(set(summary_sources))
                or not isinstance(replacement_sources, list)
                or sorted(replacement_sources) != frozen_sources):
            raise CandidateExportError("candidate_release_controls_mismatch")
        member_count = int(connection.execute(
            "SELECT count(*) FROM uec.release_members WHERE release_id=%s", (release_id,)
        ).fetchone()[0])
        if member_count != review.get("member_count"):
            raise CandidateExportError("candidate_member_count_mismatch")

        member_digest = hashlib.sha256()
        seen_members = 0
        restricted_count = 0
        member_sources: set[str] = set()
        source_urls = _source_urls()
        member_cursor = connection.cursor(name="uec_frozen_candidate_membership_verify")
        member_cursor.execute(_CANDIDATE_MEMBER_SQL, (release_id,))
        for row in member_cursor:
            (row_release, facility_id, observation_id, source_record_id, source_id,
             artifact_id, artifact_sha, taxonomy, _source_record_key, _raw_fields, _source_values,
             _retrieved_at, _observed_at, is_restricted) = row
            if taxonomy is None:
                raise CandidateExportError("candidate_taxonomy_missing")
            member_digest.update(_member_payload([
                row_release, facility_id, observation_id, source_record_id, source_id,
                artifact_id, artifact_sha, taxonomy,
            ]))
            seen_members += 1
            member_sources.add(source_id)
            if source_id in frozen_artifacts and artifact_sha != frozen_artifacts[source_id]:
                raise CandidateExportError("candidate_frozen_artifact_mismatch")
            if is_restricted:
                restricted_count += 1
        if (seen_members != member_count or member_digest.hexdigest() != review.get("member_sha256")):
            raise CandidateExportError("candidate_member_hash_mismatch")
        if sorted(member_sources) != summary_sources or not set(frozen_sources).issubset(member_sources):
            raise CandidateExportError("candidate_member_source_scope_mismatch")

        export_cursor = connection.cursor(name="uec_frozen_candidate_graph_export")
        export_cursor.execute(_CANDIDATE_EXPORT_SQL, (release_id,))
        expected_groups: Counter[tuple[str, str]] = Counter()
        exported_member_count = 0

        def export_rows():
            nonlocal exported_member_count
            for row in export_cursor:
                (source_id, source_record_key, raw_fields, source_values,
                 artifact_sha, retrieved_at, observed_at, is_restricted) = row
                if is_restricted:
                    continue
                if not isinstance(raw_fields, dict) or "normalized" not in raw_fields:
                    raise CandidateExportError("candidate_normalized_payload_missing")
                expected_groups[(source_id, artifact_sha)] += 1
                exported_member_count += 1
                yield (source_id, source_record_key, raw_fields, source_values,
                       artifact_sha, retrieved_at, observed_at)

        with tempfile.TemporaryDirectory(prefix=".candidate-graph-export-", dir=str(output.parent)) as temporary:
            temporary_root = Path(temporary)
            result = _write_source(export_rows(), temporary_root / "released", scope="frozen-candidate-membership",
                                  source_urls=source_urls)
            if result["total_candidates"] != exported_member_count:
                raise CandidateExportError("candidate_export_incomplete")
            verified_rows = _verify_candidate_export(temporary_root / "released", expected_groups)
            if verified_rows != exported_member_count:
                raise CandidateExportError("candidate_export_digest_or_count_mismatch")
            manifest = {
                "schema_version": "private-frozen-candidate-graph-export-v1",
                "database": expected_database, "release_id": release_id,
                "freeze_sha256": review["freeze_sha256"], "inventory_sha256": review["inventory_sha256"],
                "member_count": member_count, "member_sha256": review["member_sha256"],
                "restricted_member_count_excluded": restricted_count,
                "exported_member_count": exported_member_count,
                "release": result,
                "privacy": {"rows_emitted_to_stdout": False, "database_writes": False,
                            "publication_authorized": False},
            }
            (temporary_root / "manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
            # On Windows, rename to an existing target fails rather than replacing it.
            os.rename(temporary_root, output)
        connection.rollback()
    except CandidateExportError:
        connection.rollback()
        raise
    except Exception:
        connection.rollback()
        raise CandidateExportError("candidate_export_failed") from None
    finally:
        connection.close()
    return {
        "status": "exported", "release_id": release_id, "member_count": member_count,
        "restricted_member_count_excluded": restricted_count, "exported_member_count": exported_member_count,
        "member_sha256": review["member_sha256"], "output_created": True,
        "database_writes": False, "publication_authorized": False,
    }


def replay_retained_it853(source_run: Path, output_root: Path) -> dict[str, Any]:
    """Create a versioned semantic replay of the already-retained 853 evidence.

    This reads the sealed adapter graph handoff and its normalized records; it
    never queries or duplicates the current source_records census.
    """
    staging_root = (Path.cwd() / "data" / "staging").resolve()
    output_root = output_root.resolve()
    try:
        output_root.relative_to(staging_root)
    except ValueError as exc:
        raise ValueError("private replay output must remain under ignored data/staging") from exc
    manifest = json.loads((source_run / "manifest.json").read_text(encoding="utf-8"))
    graph_root = source_run / "graph"
    graph_path = graph_root / "graph-candidates.jsonl"
    graph_manifest = json.loads((graph_root / "graph-candidates-manifest.json").read_text(encoding="utf-8"))
    if manifest.get("source_id") != "it.853-2004" or graph_manifest.get("candidate_count") != 47375:
        raise ValueError("retained 853 artifact does not match the inventoried sealed handoff")
    normalized_by_key: dict[str, dict[str, Any]] = {}
    with (source_run / "normalized" / "records.jsonl").open(encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            if isinstance(record.get("source_record_key"), str) and isinstance(record.get("normalized"), dict):
                normalized_by_key[record["source_record_key"]] = record["normalized"]
    output_root.mkdir(parents=True, exist_ok=True)
    target = output_root / "graph-candidates.jsonl"
    temp_path: Path | None = None
    digest = hashlib.sha256()
    counts: Counter[str] = Counter()
    locations: Counter[str] = Counter()
    try:
        with tempfile.NamedTemporaryFile("wb", dir=output_root, prefix=".replay-", delete=False) as handle:
            temp_path = Path(handle.name)
            with graph_path.open(encoding="utf-8") as original:
                for line in original:
                    candidate = json.loads(line)
                    key = candidate["source_record_key"]
                    values = candidate.get("source_values", {})
                    vat = values.get("p_iva") if isinstance(values, dict) else None
                    # The original retained handoff has the documented native
                    # VAT/operator assertions. Exclude personal fiscal codes.
                    candidate["organizations"] = [entity for entity in candidate.get("organizations", [])
                        if entity.get("source_identifier", {}).get("identifier_type") == "italian_vat"]
                    mapped_ids = organization_identifiers("it.853-2004", {}, values)
                    if candidate["organizations"] and mapped_ids:
                        candidate["organizations"][0]["source_identifier"].update(mapped_ids[0])
                    candidate["relationships"] = [edge for edge in candidate.get("relationships", [])
                        if edge.get("relationship_type") == "operator"
                        and edge.get("from_organization_ref") in {e["local_ref"] for e in candidate["organizations"]}]
                    for edge in candidate["relationships"]:
                        edge["signal_bundle"] = [{"kind": "source_identifier_cooccurrence",
                            "identifier_types": ["italian_vat"], "connection_type": "exact"}]
                    candidate["signal_bundle"] = [{"kind": "source_identifier_cooccurrence",
                        "identifier_types": ["italian_vat"], "connection_type": "exact"}] if candidate["organizations"] else []
                    normalized = normalized_by_key.get(key)
                    if normalized is not None:
                        candidate["normalized_values"] = normalized
                    candidate["name_assertions"] = name_assertions("it.853-2004", normalized or {}, values)
                    if not candidate["name_assertions"]:
                        candidate.pop("name_assertions", None)
                    candidate["location_role"] = location_role("it.853-2004", normalized or {}, values)
                    payload = canonical_json_bytes(candidate)
                    handle.write(payload)
                    digest.update(payload)
                    counts["candidate_rows"] += 1
                    counts["facility_identifier_candidates"] += bool(candidate.get("facilities"))
                    counts["organization_identifier_candidates"] += len(candidate["organizations"])
                    counts["operator_relationship_candidates"] += len(candidate["relationships"])
                    counts["name_assertion_candidates"] += len(candidate.get("name_assertions", []))
                    locations[candidate["location_role"]] += 1
        temp_path.replace(target)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()
    output_manifest = {
        "schema_version": "private-graph-candidate-batch-v1", "contract_version": "graph-candidate-handoff-v1",
        "source_id": "it.853-2004", "source_ids": ["it.853-2004"],
        "source_artifact_sha256": manifest["checksum_sha256"], "checksum_sha256": manifest["checksum_sha256"],
        "retrieved_at_utc": manifest["retrieved_at_utc"], "source_url": manifest["source_url"], "country_code": "IT",
        "candidate_count": counts["candidate_rows"], "candidate_rows": counts["candidate_rows"],
        "facility_identifier_candidates": counts["facility_identifier_candidates"],
        "organization_identifier_candidates": counts["organization_identifier_candidates"],
        "operator_relationship_candidates": counts["operator_relationship_candidates"],
        "name_assertion_candidates": counts["name_assertion_candidates"], "location_role_counts": dict(sorted(locations.items())),
        "records_sha256": digest.hexdigest(), "replay_of": str(graph_path.resolve().relative_to(Path.cwd().resolve())),
        "replay_of_sha256": graph_manifest["sha256"], "storage_state": "private", "privacy_status": "pending",
        "review_state": "review_required", "publication_status": "not_eligible", "release_id": None,
    }
    (output_root / "manifest.json").write_text(json.dumps(output_manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return {key: output_manifest[key] for key in ("source_id", "candidate_count", "facility_identifier_candidates",
        "organization_identifier_candidates", "operator_relationship_candidates", "name_assertion_candidates",
        "location_role_counts", "records_sha256", "replay_of_sha256")}


def replay_existing_handoff(source_id: str, records_path: Path, source_manifest_path: Path,
                            output_root: Path) -> dict[str, Any]:
    """Version retained ICPE/Scotland candidates with typed name/location roles."""
    staging_root = (Path.cwd() / "data" / "staging").resolve()
    output_root = output_root.resolve()
    try:
        output_root.relative_to(staging_root)
    except ValueError as exc:
        raise ValueError("private replay output must remain under ignored data/staging") from exc
    metadata = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    artifact_sha = metadata.get("checksum_sha256") or metadata.get("sha256")
    retrieved_at = metadata.get("retrieved_at_utc") or metadata.get("retrieved_at")
    source_url = metadata.get("source_url") or metadata.get("canonical_url")
    if not isinstance(artifact_sha, str) or len(artifact_sha) != 64:
        raise ValueError("retained source artifact checksum missing")
    output_root.mkdir(parents=True, exist_ok=True)
    target = output_root / "graph-candidates.jsonl"
    digest = hashlib.sha256()
    counts: Counter[str] = Counter()
    locations: Counter[str] = Counter()
    with target.open("wb") as handle, records_path.open(encoding="utf-8") as original:
        for line in original:
            candidate = json.loads(line)
            if candidate.get("source_id") != source_id:
                raise ValueError("retained handoff source id mismatch")
            source_values = candidate.get("source_values", {})
            normalized = candidate.get("normalized_values", {})
            if source_id == "fr.georisques.icpe.animal":
                candidate["name_assertions"] = name_assertions(source_id,
                    normalized if isinstance(normalized, dict) else {},
                    source_values if isinstance(source_values, dict) else {})
                facility = (candidate.get("facilities") or [None])[0]
                aliases = additional_source_identifiers(source_id,
                    normalized if isinstance(normalized, dict) else {},
                    source_values if isinstance(source_values, dict) else {})
                if facility is not None and aliases:
                    facility["additional_source_identifiers"] = aliases
                candidate["organizations"] = [entity for entity in candidate.get("organizations", [])
                    if entity.get("source_identifier", {}).get("identifier_type") != "french_siret"]
                candidate["relationships"] = [edge for edge in candidate.get("relationships", [])
                    if edge.get("relationship_type") != "operator"]
            candidate["location_role"] = location_role(source_id,
                normalized if isinstance(normalized, dict) else {},
                source_values if isinstance(source_values, dict) else {})
            for entity in candidate.get("organizations", []):
                identifier = entity.get("source_identifier", {})
                # No undocumented authority namespace is inferred here.
                identifier.setdefault("id_namespace", source_id)
            payload = canonical_json_bytes(candidate)
            handle.write(payload)
            digest.update(payload)
            counts["candidate_rows"] += 1
            counts["facility_identifier_candidates"] += bool(candidate.get("facilities"))
            counts["organization_identifier_candidates"] += len(candidate.get("organizations", []))
            counts["operator_relationship_candidates"] += len(candidate.get("relationships", []))
            counts["name_assertion_candidates"] += len(candidate.get("name_assertions", []))
            locations[candidate["location_role"]] += 1
    replay_sha = hashlib.sha256(records_path.read_bytes()).hexdigest()
    result = {
        "schema_version": "private-graph-candidate-batch-v1", "contract_version": "graph-candidate-handoff-v1",
        "source_id": source_id, "source_ids": [source_id], "source_artifact_sha256": artifact_sha,
        "checksum_sha256": artifact_sha, "retrieved_at_utc": retrieved_at, "source_url": source_url,
        "country_code": COUNTRY_BY_SOURCE.get(source_id, "unknown"), "candidate_count": counts["candidate_rows"],
        "candidate_rows": counts["candidate_rows"], "facility_identifier_candidates": counts["facility_identifier_candidates"],
        "organization_identifier_candidates": counts["organization_identifier_candidates"],
        "operator_relationship_candidates": counts["operator_relationship_candidates"],
        "name_assertion_candidates": counts["name_assertion_candidates"], "location_role_counts": dict(sorted(locations.items())),
        "records_sha256": digest.hexdigest(), "replay_of": str(records_path.resolve().relative_to(Path.cwd().resolve())),
        "replay_of_sha256": replay_sha, "storage_state": "private", "privacy_status": "pending",
        "review_state": "review_required", "publication_status": "not_eligible", "release_id": None,
    }
    (output_root / "manifest.json").write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return {key: result[key] for key in ("source_id", "candidate_count", "facility_identifier_candidates",
        "organization_identifier_candidates", "operator_relationship_candidates", "name_assertion_candidates",
        "location_role_counts", "records_sha256", "replay_of_sha256")}


def write_final_source_coverage(export_root: Path, receipt_path: Path, *,
                               release_manifest: Path,
                               additional_manifests: Iterable[Path] = ()) -> dict[str, Any]:
    """Write a row-free manifest inventory for released and retained handoffs."""
    export_root = export_root.resolve()
    receipt_path = receipt_path.resolve()
    staging_root = (Path.cwd() / "data" / "staging").resolve()
    if export_root != staging_root and staging_root not in export_root.parents:
        raise ValueError("coverage inputs must remain under ignored data/staging")
    if staging_root not in receipt_path.parents:
        raise ValueError("coverage receipt must remain under ignored data/staging")
    artifacts = []
    handoff_checks = []
    manifest_paths = sorted(export_root.rglob("manifest.json")) + sorted(Path(path) for path in additional_manifests)
    for manifest_path in manifest_paths:
        if manifest_path.name != "manifest.json":
            continue
        try:
            value = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        source_id = value.get("source_id")
        if not isinstance(source_id, str) or not isinstance(value.get("candidate_count"), int):
            continue
        candidate_path = manifest_path.parent / "graph-candidates.jsonl"
        if not candidate_path.is_file():
            raise ValueError(f"candidate file missing for {source_id}")
        file_digest = hashlib.sha256()
        row_count = 0
        keys: set[str] = set()
        with candidate_path.open("rb") as binary, candidate_path.open(encoding="utf-8") as text:
            for payload_line, json_line in zip(binary, text):
                file_digest.update(payload_line)
                candidate = json.loads(json_line)
                validate_graph_candidate(candidate)
                if candidate.get("source_id") != source_id or not isinstance(candidate.get("source_record_key"), str):
                    raise ValueError(f"source key provenance invalid for {source_id}")
                keys.add(candidate["source_record_key"])
                row_count += 1
        if row_count != value["candidate_count"] or file_digest.hexdigest() != value.get("records_sha256"):
            raise ValueError(f"candidate count or checksum mismatch for {source_id}")
        handoff_checks.append({"source_id": source_id, "scope": "approved-release-membership" if "\\released\\" in str(manifest_path.resolve()) else "retained-private",
            "candidate_rows_validated": row_count, "distinct_native_record_keys": len(keys),
            "native_keys_preserved": True, "candidate_sha256_verified": True,
            "artifact_sha256_present": isinstance(value.get("source_artifact_sha256") or value.get("checksum_sha256"), str)})
        resolved_manifest = manifest_path.resolve()
        artifacts.append({"source_id": source_id, "scope": "approved-release-membership" if "\\released\\" in str(resolved_manifest) else "retained-private",
            "manifest_path": str(resolved_manifest.relative_to(Path.cwd().resolve())),
            "artifact_sha256": value.get("source_artifact_sha256") or value.get("checksum_sha256"),
            "source_artifact_sha256": value.get("source_artifact_sha256"),
            "candidate_count": value.get("candidate_count"),
            "facility_identifier_candidates": value.get("facility_identifier_candidates"),
            "organization_identifier_candidates": value.get("organization_identifier_candidates"),
            "operator_relationship_candidates": value.get("operator_relationship_candidates"),
            "name_assertion_candidates": value.get("name_assertion_candidates"),
            "location_role_counts": value.get("location_role_counts", {}),
            "records_sha256": value.get("records_sha256")})
    scope_counts: Counter[str] = Counter()
    for artifact in artifacts:
        scope_counts[artifact["scope"]] += artifact["candidate_count"]
    released_sources = sorted({item["source_id"] for item in artifacts if item["scope"] == "approved-release-membership"})
    retained_sources = sorted({item["source_id"] for item in artifacts if item["scope"] == "retained-private"})
    approved_release_id, approved_sources = _read_release_scope(release_manifest)
    receipt = {
        "schema_version": "whole-dataset-graph-source-coverage-v1",
        "release_id": approved_release_id, "released_source_count": len(released_sources),
        "released_source_ids": released_sources, "released_candidate_rows": scope_counts["approved-release-membership"],
        "released_candidate_rows_expected": 69220, "released_count_matches_approved_manifest": scope_counts["approved-release-membership"] == 69220,
        "released_source_ids_match_approved_manifest": released_sources == approved_sources,
        "retained_source_ids": retained_sources, "retained_candidate_rows": scope_counts["retained-private"],
        "artifact_handoffs": sorted(artifacts, key=lambda item: (item["scope"], item["source_id"], str(item["artifact_sha256"]))),
        "handoff_validation": {"candidate_contracts_validated": True, "checks": handoff_checks,
            "native_record_keys_copied_without_transformation": True,
            "all_artifact_sha256_present": all(item["artifact_sha256_present"] for item in handoff_checks)},
        "retained_families_without_handoff": {
            "us.aphis.annual-reports": "Evidence lane owns event handoff; no handoff root supplied in this lane.",
            "us.inspections": "Evidence lane owns event handoff; no handoff root supplied in this lane.",
        },
        "privacy": {"row_values_included": False, "private_candidate_data_under_ignored_staging": True,
            "database_writes": False, "publication_authorized": False},
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return {key: receipt[key] for key in ("released_source_count", "released_candidate_rows", "released_count_matches_approved_manifest", "retained_source_ids", "retained_candidate_rows", "retained_families_without_handoff")}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url-env", default="UEC_GRAPH_EXPORT_URL")
    parser.add_argument("--candidate-export", action="store_true",
                        help="export the exact assigned frozen candidate, separately from legacy release mode")
    parser.add_argument("--expected-database", choices=[_CANDIDATE_DATABASE])
    parser.add_argument("--candidate-release-id", choices=[_CANDIDATE_RELEASE])
    parser.add_argument("--freeze", type=Path)
    parser.add_argument("--review-template", type=Path)
    parser.add_argument("--release-manifest")
    parser.add_argument("--output-root", required=True)
    args = parser.parse_args()
    url = os.environ.get(args.database_url_env)
    if not url:
        raise SystemExit("private graph export database environment variable is unavailable")
    if args.candidate_export:
        if not all((args.expected_database, args.candidate_release_id, args.freeze, args.review_template)):
            parser.error("candidate mode requires --expected-database, --candidate-release-id, --freeze and --review-template")
        try:
            report = export_frozen_candidate(
                url, expected_database=args.expected_database, release_id=args.candidate_release_id,
                freeze_path=args.freeze, review_path=args.review_template, output_root=Path(args.output_root),
            )
        except CandidateExportError as error:
            print(json.dumps({"status": "blocked", "reason": error.category}, sort_keys=True))
            return 2
    else:
        if not args.release_manifest:
            parser.error("legacy mode requires --release-manifest")
        report = export_clone(url, Path(args.release_manifest), Path(args.output_root))
    print(json.dumps(report, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
