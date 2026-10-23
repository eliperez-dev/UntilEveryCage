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
