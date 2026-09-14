"""Import a validated private staging run into a disposable candidate database.

This is intentionally a small handoff bridge, not a publication importer.  It
only accepts an explicitly marked local database and creates candidate rows
with review-required defaults.  Raw artifacts remain in the caller-owned
staging/object-storage location; the database stores metadata and private
normalized evidence only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import urlparse
import uuid

import psycopg


class CandidateImportError(ValueError):
    pass


DISPOSABLE_MARKER = "uec-e2e-disposable-v1"
DEFAULT_BATCH_SIZE = 500


def require_disposable_database(database_url: str, acknowledged: bool) -> None:
    """Reject production/shared targets before opening a connection."""
    if not acknowledged:
        raise CandidateImportError("refusing import: pass --disposable-db explicitly")
    parsed = urlparse(database_url)
    host = (parsed.hostname or "").lower()
    if host not in {"127.0.0.1", "::1", "localhost"}:
        raise CandidateImportError("refusing import: database host is not loopback")
    if parsed.port in (None, 5432):
        raise CandidateImportError("refusing import: disposable database must use a non-default port")
    database = (parsed.path or "").lstrip("/").lower()
    if not database.startswith("uec"):
        raise CandidateImportError("refusing import: database name is not a UEC disposable database")


def verify_disposable_marker(connection) -> None:
    """Require a marker provisioned by the disposable DB image, not the CLI."""
    row = connection.execute(
        """SELECT marker
           FROM uec.disposable_import_guard
           WHERE marker=%s AND database_name=current_database() AND role_name=current_user""",
        (DISPOSABLE_MARKER,),
    ).fetchone()
    if row != (DISPOSABLE_MARKER,):
        raise CandidateImportError("refusing import: database lacks the exact disposable server marker")


def load_inputs(manifest_path: Path, normalized_path: Path, raw_path: Path) -> tuple[dict, list[dict]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    required = {"source_id", "source_url", "retrieved_at_utc", "checksum_sha256", "byte_size",
                "normalized_rows", "normalized_sha256", "release_state", "publication_state"}
    missing = sorted(required - manifest.keys())
    if missing:
        raise CandidateImportError(f"manifest missing required keys: {', '.join(missing)}")
    if manifest["release_state"] != "not-created" or manifest["publication_state"] != "private-candidate":
        raise CandidateImportError("manifest is not an unpromoted private candidate")
    raw = raw_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != manifest["checksum_sha256"] or len(raw) != int(manifest["byte_size"]):
        raise CandidateImportError("raw artifact checksum or byte size does not match manifest")
    raw = normalized_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != manifest["normalized_sha256"]:
        raise CandidateImportError("normalized JSONL checksum does not match manifest")
    rows = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line]
    if len(rows) != int(manifest["normalized_rows"]):
        raise CandidateImportError("normalized row count does not match manifest")
    return manifest, rows


def _record_parts(record: dict) -> tuple[str, dict]:
    normalized = record.get("normalized")
    if not isinstance(normalized, dict):
        raise CandidateImportError("record has no normalized object")
    source_id = record.get("source_id")
    source_row = record.get("source_row")
    establishment_id = normalized.get("establishment_id")
    if not isinstance(source_id, str) or not source_id or source_row is None or not establishment_id:
        raise CandidateImportError("record must contain source_id, source_row, and establishment_id")
    key = f"{source_row}:{establishment_id}"
    return key, normalized


def _country_code(manifest: dict, normalized: dict) -> str:
    explicit = manifest.get("country_code") or normalized.get("country_code")
    if explicit:
        return str(explicit)[:2].upper()
    # Do not turn a country name into an invented code. These are the only
    # source-country names currently present in the validated adapters.
    return {"Denmark": "DK", "England": "GB", "Wales": "GB"}.get(normalized.get("nation"), "ZZ")


def _stable_uuid(*parts: object) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, "uec-candidate:" + "|".join(str(part) for part in parts))


def import_candidate(database_url: str, manifest: dict, rows: list[dict], release_id: str,
                     reset: bool, batch_size: int = DEFAULT_BATCH_SIZE) -> int:
    """Append one candidate release; never promotes or marks review complete.

    Batches commit independently so a bounded failure can resume with the same
    release ID. Deterministic IDs and conflict-safe inserts make retries
    idempotent; every committed row remains private and review-required.
    """
    if reset:
        raise CandidateImportError(
            "--reset is intentionally refused: append-only evidence cannot be deleted; "
            "recreate the disposable database with the local-v2 maintenance recipe"
        )
    if batch_size <= 0:
        raise CandidateImportError("batch size must be positive")
    now = manifest["retrieved_at_utc"]
    ruleset = str(manifest.get("config_version") or manifest.get("schema_version") or "unknown")
    with psycopg.connect(database_url) as db:
        verify_disposable_marker(db)
        with db.transaction():
            db.execute("""INSERT INTO uec.sources(source_id,country_code,name,official_url,access_method)
                         VALUES (%s,%s,%s,%s,'validated-private-staging')
                         ON CONFLICT (source_id) DO NOTHING""",
                       (manifest["source_id"], str(manifest.get("country_code", "ZZ"))[:2].upper(),
                        manifest["source_id"], manifest["source_url"]))
            db.execute("""INSERT INTO uec.raw_artifacts(storage_key,sha256,byte_size,media_type,retrieved_at)
                         VALUES (%s,%s,%s,'application/octet-stream',%s)
                         ON CONFLICT (sha256) DO NOTHING""",
                       (f"private-staging/{manifest['source_id']}/{manifest['checksum_sha256']}",
                        manifest["checksum_sha256"], int(manifest["byte_size"]), now))
            artifact_id = db.execute("SELECT artifact_id FROM uec.raw_artifacts WHERE sha256=%s",
                                     (manifest["checksum_sha256"],)).fetchone()[0]
            db.execute("""INSERT INTO uec.acquisition_runs(source_id,checked_at,retrieved_at,ingested_at,status,source_url,code_version,config_version)
                         VALUES (%s,%s,%s,now(),'changed',%s,%s,%s)""",
                       (manifest["source_id"], now, now, manifest["source_url"],
                        manifest.get("code_version", "unknown"), manifest.get("config_version", "unknown")))
            run_id = db.execute("SELECT run_id FROM uec.acquisition_runs WHERE source_id=%s ORDER BY ingested_at DESC LIMIT 1",
                                (manifest["source_id"],)).fetchone()[0]
            db.execute("INSERT INTO uec.acquisition_run_artifacts(run_id,artifact_id) VALUES (%s,%s) ON CONFLICT DO NOTHING",
                       (run_id, artifact_id))
            db.execute("""INSERT INTO uec.releases(release_id,status,ruleset_version,summary,test_only)
                         VALUES (%s,'candidate',%s,%s,true)
                         ON CONFLICT (release_id) DO NOTHING""",
                       (release_id, ruleset, json.dumps({"source_id": manifest["source_id"], "profile": manifest.get("profile")})))
        count = 0
        for offset in range(0, len(rows), batch_size):
            batch_count = 0
            with db.transaction():
                for record in rows[offset:offset + batch_size]:
                    key, normalized = _record_parts(record)
                    country = _country_code(manifest, normalized)
                    name = normalized.get("trading_name")
                    city = normalized.get("city")
                    record_id = _stable_uuid(manifest["source_id"], key, artifact_id)
                    source_inserted = db.execute("""INSERT INTO uec.source_records(source_record_id,source_id,source_record_key,artifact_id,raw_fields,parsed_at)
                        VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (source_id,source_record_key,artifact_id)
                        DO NOTHING RETURNING source_record_id""",
                        (record_id, manifest["source_id"], key, artifact_id,
                         json.dumps({"source_values": record.get("source_values", {})}), now)).fetchone()
                    if source_inserted:
                        record_id = source_inserted[0]
                    else:
                        record_id = db.execute("""SELECT source_record_id FROM uec.source_records
                            WHERE source_id=%s AND source_record_key=%s AND artifact_id=%s""",
                            (manifest["source_id"], key, artifact_id)).fetchone()[0]
                    facility_id = _stable_uuid("facility", manifest["source_id"], key, artifact_id)
                    observation_id = _stable_uuid("observation", manifest["source_id"], key, artifact_id)
                    db.execute("""INSERT INTO uec.facilities(facility_id,canonical_name,country_code,city)
                        VALUES (%s,%s,%s,%s) ON CONFLICT (facility_id) DO NOTHING""",
                               (facility_id, name, country, city))
                    created = db.execute("""INSERT INTO uec.observations(observation_id,facility_id,source_record_id,observed_at,observation,classification,ruleset_id,rule_id,classification_category,classification_review_status,default_visible,coordinate_review_status,first_observed_at)
                        VALUES (%s,%s,%s,%s,%s,'{}',%s,'candidate','unclassified','review_required',false,'review_required',%s)
                        ON CONFLICT (facility_id,source_record_id,observed_at) DO NOTHING RETURNING observation_id""",
                        (observation_id, facility_id, record_id, now, json.dumps(normalized), ruleset, now)).fetchone()
                    observation_ref = created[0] if created else db.execute("""SELECT observation_id FROM uec.observations
                        WHERE facility_id=%s AND source_record_id=%s AND observed_at=%s""",
                        (facility_id, record_id, now)).fetchone()[0]
                    db.execute("INSERT INTO uec.release_members(release_id,facility_id,observation_id,default_visible) VALUES (%s,%s,%s,false) ON CONFLICT DO NOTHING",
                               (release_id, facility_id, observation_ref))
                    if created:
                        db.execute("INSERT INTO uec.publication_review_events(source_record_id,release_id,factual_review_status,privacy_screening_status,maintainer_approval,publication_eligible) VALUES (%s,%s,'unreviewed','pending','pending',false)",
                                   (record_id, release_id))
                        batch_count += 1
            count += batch_count
        return count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--raw", type=Path, required=True, help="preserved raw artifact; independently hash-checked")
    parser.add_argument("--normalized", type=Path, required=True)
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--database-url", default=os.environ.get("UEC_DATABASE_URL", ""))
    parser.add_argument("--disposable-db", action="store_true", help="acknowledge this is a disposable local DB")
    parser.add_argument("--reset", action="store_true", help="rebuild this candidate release only")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    args = parser.parse_args()
    require_disposable_database(args.database_url, args.disposable_db)
    if not args.release_id.startswith("candidate-"):
        raise CandidateImportError("release id must start with candidate-")
    manifest, rows = load_inputs(args.manifest, args.normalized, args.raw)
    print(f"imported {import_candidate(args.database_url, manifest, rows, args.release_id, args.reset, args.batch_size)} candidate rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
