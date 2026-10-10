#!/usr/bin/env python3
"""Reproject retained taxonomy or reconcile a frozen private preview.

The legacy JSONL mode defaults to a dry run and writes only the derived
``taxonomy`` object when applied. Frozen-preview mode is read-only by default;
``--apply`` appends v2 assignment sets after exact frozen identity checks and
leaves immutable real-preview source and candidate rows unchanged.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from urllib.parse import parse_qsl, unquote, urlsplit

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from pipeline.taxonomy_crosswalk import CROSSWALK_VERSION, reproject
from pipeline.taxonomy_crosswalk import crosswalk_document, persistence_assignments
from pipeline.taxonomy.persistence import persist_preview_candidate_assignment_set, persist_uec_assignment_set

def _utc_identity(value):
    if hasattr(value, "isoformat"):
        value = value.isoformat()
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.utcoffset() is None:
        raise ValueError("frozen preview retrieval timestamp is timezone-naive")
    return parsed.astimezone(timezone.utc)


def _load_bridge_module():
    path = ROOT / "pipeline" / "scripts" / "maintenance" / "bridge-v0-candidates.py"
    spec = importlib.util.spec_from_file_location("uec_v0_candidate_bridge_for_reprojection", path)
    if spec is None or spec.loader is None:
        raise ValueError("candidate bridge unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _validate_preview_database_url(database_url: str, expected_database: str) -> None:
    if expected_database not in {"uec_v0_review_r2", "uec", "uec_v0_api_repair"}:
        raise ValueError("expected database must be an approved isolated preview database")
    try:
        parsed = urlsplit(database_url)
        host = (parsed.hostname or "").casefold()
        database = unquote(parsed.path.lstrip("/"))
        authority_host = parsed.netloc.rsplit("@", 1)[-1]
        query = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True) if parsed.query else []
    except ValueError:
        raise ValueError("database URL must target the exact expected loopback database") from None
    if parsed.scheme.casefold() not in {"postgresql", "postgres"}:
        raise ValueError("database URL must use the PostgreSQL scheme")
    # libpq accepts routing overrides in URI query parameters; reject them all,
    # along with multi-host authorities. sslmode is the sole permitted option.
    if "," in authority_host or (query and (len(query) != 1 or query[0][0].casefold() != "sslmode"
                                               or query[0][1].casefold() not in {
                                                   "disable", "allow", "prefer", "require", "verify-ca", "verify-full"
                                               })):
        raise ValueError("database URL routing overrides are not allowed")
    if host not in {"localhost", "127.0.0.1", "::1"} or database != expected_database:
        raise ValueError("database URL must target the exact expected loopback database")


def _json_digest(connection, query: str, params: tuple = ()) -> str:
    """Hash rows incrementally; do not materialize retained private rows or log them."""
    import hashlib
    hasher = hashlib.sha256()
    cursor_name = "v0_taxonomy_audit"
    with connection.cursor(name=cursor_name) as cursor:
        cursor.itersize = 512
        cursor.execute(query, params)
        for row in cursor:
            hasher.update(json.dumps(row[0], ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":"), default=str).encode("utf-8"))
            hasher.update(b"\n")
    return hasher.hexdigest()


def _frozen_progress(source_id: str, phase: str, candidate_groups: int) -> None:
    sys.stderr.write(json.dumps({"source_id": source_id, "phase": phase,
                                 "candidate_groups": candidate_groups}, sort_keys=True) + "\n")


def _blocked_report(error: Exception) -> dict:
    report = {"mode": "blocked", "reason_code": "candidate_preview_reconciliation_failed",
              "error_class": type(error).__name__, "private_payload_included": False}
    if type(error).__name__ == "BridgeError":
        reason = str(error)
        if re.fullmatch(r"[a-z][a-z0-9_]{0,95}", reason):
            report["reason_code"] = reason
    else:
        sqlstate = getattr(error, "sqlstate", None)
        if (type(error).__module__.startswith("psycopg") and isinstance(sqlstate, str)
                and re.fullmatch(r"[0-9A-Z]{5}", sqlstate)):
            report["reason_code"] = "database_operation_failed"
            report["database_sqlstate"] = sqlstate
        elif isinstance(error, ValueError):
            report["reason_code"] = "taxonomy_reconciliation_validation_failed"
    return report


def _assert_preview_source_identity(connection, source: str, entry: dict, handoff: dict, importer) -> dict:
    snapshot = entry["snapshot_sha256"]
    run = connection.execute("""SELECT source_artifact_sha256,normalized_sha256,source_url,retrieved_at,
            accepted_count,quarantined_count,imported_observation_count,facility_count,public_rows
        FROM real_preview.source_preview_runs WHERE source_id=%s AND snapshot_sha256=%s""",
        (source, snapshot)).fetchone()
    manifest = connection.execute("""SELECT source_artifact_sha256,normalized_sha256,normalized_rows,
            source_url,retrieved_at,code_version,config_version
        FROM real_preview.source_manifests WHERE source_id=%s AND snapshot_sha256=%s""",
        (source, snapshot)).fetchone()
    latest = connection.execute("""SELECT snapshot_sha256 FROM real_preview.source_preview_runs
        WHERE source_id=%s ORDER BY created_at DESC,run_id DESC LIMIT 1""", (source,)).fetchone()
    if run is None or manifest is None or latest is None or str(latest[0]).strip() != snapshot:
        raise ValueError("frozen preview snapshot missing or stale")
    expected = entry
    if (str(run[0]).strip() != expected["source_artifact_sha256"]
            or str(run[1]).strip() != expected["normalized_sha256"]
            or str(manifest[0]).strip() != expected["source_artifact_sha256"]
            or str(manifest[1]).strip() != expected["normalized_sha256"]
            or int(manifest[2]) != len(handoff["rows"])
            or int(run[4]) != entry["accepted_count"]
            or int(run[5]) != entry["quarantined_count"]
            or int(run[6]) != len(handoff["rows"])
            or int(run[7]) != len(handoff["representatives"])
            or int(run[8]) != 0 or run[2] != manifest[3] or run[3] != manifest[4]
            or run[2] != handoff["source_url"]
            or _utc_identity(run[3]) != _utc_identity(handoff["manifest"].get("retrieved_at_utc"))
            or manifest[5] != handoff["manifest"].get("code_version")
            or manifest[6] != handoff["manifest"].get("config_version")):
        raise ValueError("frozen preview provenance or counts mismatch")
    parsed_rows = handoff["rows"]
    observations = connection.execute("""SELECT preview_id::text,source_identifier,location_class,country_code,
            city,postal_code,latitude,longitude,coordinate_precision,source_observed_at,facility_candidate
        FROM real_preview.observations WHERE source_id=%s AND snapshot_sha256=%s""", (source, snapshot)).fetchall()
    by_identifier = {str(row[1]): row for row in observations}
    if len(observations) != len(parsed_rows) or len(by_identifier) != len(parsed_rows):
        raise ValueError("frozen preview observation identity mismatch")
    expected_rep_ids = {}
    for group in handoff["groups"]:
        representative = handoff["representatives"][group]
        expected_rep_ids[group] = str(representative[0][0])
    for parsed, _raw in parsed_rows:
        identifier = str(parsed[0])
        actual = by_identifier.get(identifier)
        if actual is None:
            raise ValueError("frozen preview source identifier missing")
        expected_tuple = (parsed[1], parsed[2], parsed[3], parsed[4], parsed[5], parsed[6], parsed[7], parsed[8])
        actual_tuple = tuple(actual[2:10])
        if actual_tuple != expected_tuple:
            raise ValueError("frozen preview observation projection mismatch")
        group = str(parsed[importer.SOURCE_GROUP_KEY_INDEX])
        if bool(actual[10]) != (expected_rep_ids[group] == identifier):
            raise ValueError("frozen preview representative flag mismatch")
    candidates = connection.execute("""SELECT candidate_id::text,source_group_key,
            representative_observation_id::text,location_class,country_code,city,postal_code,
            latitude,longitude,coordinate_precision,observation_count
        FROM real_preview.candidates WHERE source_id=%s AND snapshot_sha256=%s""", (source, snapshot)).fetchall()
    by_group = {str(row[1]): row for row in candidates}
    if len(candidates) != len(handoff["representatives"]) or set(by_group) != set(handoff["groups"]):
        raise ValueError("frozen preview candidate group set mismatch")
    preview_id_by_identifier = {str(row[1]): str(row[0]) for row in observations}
    for group, (representative_parsed, _raw) in handoff["representatives"].items():
        row = by_group[group]
        if (str(row[2]) != preview_id_by_identifier[expected_rep_ids[group]]
                or int(row[10]) != len(handoff["groups"][group])
                or row[3:10] != (representative_parsed[1], representative_parsed[2], representative_parsed[3],
                                 representative_parsed[4], representative_parsed[5], representative_parsed[6],
                                 representative_parsed[7])):
            raise ValueError("frozen preview candidate representative mismatch")
    return {"groups": by_group, "preview_ids": preview_id_by_identifier,
            "observation_count": len(observations)}


def _reconcile_preview_freeze_in_transaction(connection, freeze_path: Path, inventory_path: Path, *,
                                             apply_changes: bool, expected_database: str) -> dict:
    """Reconcile only frozen real-preview taxonomy assignments/projection fields."""
    bridge = _load_bridge_module()
    freeze, inventory = bridge.load_freeze(freeze_path, inventory_path)
    inventory_sources = {row["source_id"]: row for row in inventory["source_scope"]["sources"]}
    importer = bridge.IMPORTER
    actual_database = connection.execute("SELECT current_database()").fetchone()[0]
    if actual_database != expected_database:
        raise ValueError("connected database does not match expected database")
    if apply_changes:
        connection.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("v0-taxonomy-reconciliation:" + freeze["release_id"],))
    before_candidates = {}
    before_observations = {}
    before_v1_assignments = {}
    projected = {}
    results = []
    for entry in freeze["selected_sources"]:
        source = entry["source_id"]
        expected_group_count = int(entry["facility_count"])
        _frozen_progress(source, "handoff_verification_started", expected_group_count)
        handoff = bridge.verify_handoff(entry, inventory_sources[source])
        checked = _assert_preview_source_identity(connection, source, entry, handoff, importer)
        snapshot = entry["snapshot_sha256"]
        before_candidates[source] = _json_digest(connection, """SELECT to_jsonb(candidate)
            FROM real_preview.candidates candidate WHERE source_id=%s AND snapshot_sha256=%s ORDER BY candidate_id""",
            (source, snapshot))
        before_observations[source] = _json_digest(connection, """SELECT to_jsonb(observation)
            FROM real_preview.observations observation WHERE source_id=%s AND snapshot_sha256=%s ORDER BY preview_id""",
            (source, snapshot))
        before_v1_assignments[source] = _json_digest(connection, """SELECT jsonb_build_object(
              'set',to_jsonb(assignment_set),'rows',COALESCE((SELECT jsonb_agg(to_jsonb(assignment)
                  ORDER BY assignment.assignment_ordinal) FROM real_preview.candidate_taxonomy_assignments assignment
                  WHERE assignment.assignment_set_id=assignment_set.assignment_set_id),'[]'::jsonb))
            FROM real_preview.candidate_taxonomy_assignment_sets assignment_set
            JOIN real_preview.candidates candidate USING(candidate_id)
            WHERE candidate.source_id=%s AND candidate.snapshot_sha256=%s
              AND assignment_set.crosswalk_version='uec-source-crosswalk-v1'
            ORDER BY assignment_set.candidate_id""", (source, snapshot))
        group_results = {}
        for group, members in handoff["groups"].items():
            contracts = [importer.activity_contract(raw.get("normalized", {}), source, raw.get("source_values", {}))
                         for _, raw in members]
            group_results[group] = importer.merge_activity_contracts(contracts, source)
        projected[source] = (handoff, checked, group_results, before_candidates[source],
                              before_observations[source], before_v1_assignments[source])
        results.append({"source_id": source, "observations": checked["observation_count"],
                        "candidate_groups": len(group_results)})
        _frozen_progress(source, "preview_identity_verified", len(group_results))

    if apply_changes:
        for source, (handoff, checked, group_results, candidate_hash, observation_hash, v1_hash) in projected.items():
            snapshot = next(row["snapshot_sha256"] for row in freeze["selected_sources"] if row["source_id"] == source)
            document = crosswalk_document(source)
            for group, activity in group_results.items():
                candidate = checked["groups"][group]
                representative = handoff["representatives"][group][0]
                preview_id = checked["preview_ids"][str(representative[0])]
                persist_preview_candidate_assignment_set(
                    connection, candidate_id=str(candidate[0]), representative_observation_id=preview_id,
                    snapshot_sha256=snapshot, source_id=source, document=document,
                    assignment_rows=activity["taxonomy_assignment_rows"],
                )
            # Strict bridge verification checks append-only v2 assignment sets;
            # legacy candidate taxonomy columns remain unchanged and immutable.
            bridge._verify_preview_source(connection, source,
                next(row for row in freeze["selected_sources"] if row["source_id"] == source), handoff)
            if _json_digest(connection, """SELECT to_jsonb(candidate)
                    FROM real_preview.candidates candidate WHERE source_id=%s AND snapshot_sha256=%s ORDER BY candidate_id""",
                (source, snapshot)) != candidate_hash:
                raise ValueError("candidate source evidence changed")
            if _json_digest(connection, """SELECT to_jsonb(observation) FROM real_preview.observations observation
                WHERE source_id=%s AND snapshot_sha256=%s ORDER BY preview_id""", (source, snapshot)) != observation_hash:
                raise ValueError("source observations changed")
            if _json_digest(connection, """SELECT jsonb_build_object(
                      'set',to_jsonb(assignment_set),'rows',COALESCE((SELECT jsonb_agg(to_jsonb(assignment)
                          ORDER BY assignment.assignment_ordinal) FROM real_preview.candidate_taxonomy_assignments assignment
                          WHERE assignment.assignment_set_id=assignment_set.assignment_set_id),'[]'::jsonb))
                    FROM real_preview.candidate_taxonomy_assignment_sets assignment_set
                    JOIN real_preview.candidates candidate USING(candidate_id)
                    WHERE candidate.source_id=%s AND candidate.snapshot_sha256=%s
                      AND assignment_set.crosswalk_version='uec-source-crosswalk-v1'
                ORDER BY assignment_set.candidate_id""", (source, snapshot)) != v1_hash:
                raise ValueError("prior taxonomy assignments changed")
            v2_count = connection.execute("""SELECT count(*) FROM real_preview.candidate_taxonomy_assignment_sets
                WHERE source_id=%s AND snapshot_sha256=%s AND crosswalk_version=%s""",
                (source, snapshot, CROSSWALK_VERSION)).fetchone()[0]
            if int(v2_count) != len(group_results):
                raise ValueError("v2 assignment set count mismatch")
            _frozen_progress(source, "append_only_assignments_verified", len(group_results))
    public_state = connection.execute("""SELECT
        (SELECT count(*) FROM uec.releases),
        (SELECT count(*) FROM uec.release_members)""").fetchone()
    if expected_database != "uec_v0_api_repair" and any(int(value) != 0 for value in public_state):
        raise ValueError("candidate-only database contains release or membership state")
    return {"mode": "applied" if apply_changes else "dry_run", "candidate_freeze_id": freeze["release_id"],
            "selected_source_count": len(results), "sources": results,
            "public_release_rows_created": 0, "public_release_members_created": 0,
            "approval_events_created": 0, "private_payload_included": False}


def reconcile_preview_freeze(connection, freeze_path: Path, inventory_path: Path, *,
                             apply_changes: bool, expected_database: str) -> dict:
    """Run all database checks and (optionally) changes in one guarded transaction."""
    with connection.transaction():
        if apply_changes:
            connection.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
        else:
            connection.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE, READ ONLY")
        return _reconcile_preview_freeze_in_transaction(
            connection, freeze_path, inventory_path, apply_changes=apply_changes,
            expected_database=expected_database)


def read_jsonl(path: Path) -> list[dict]:
    records = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                raise ValueError(f"blank JSONL row at line {line_number}")
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(f"JSONL row is not an object at line {line_number}")
            records.append(row)
    return records


def atomic_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            for record in records:
                stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True, default=list) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, nargs="?", help="retained observation JSONL (legacy mode)")
    parser.add_argument("--apply", action="store_true", help="apply the selected projection mode")
    parser.add_argument("--output", type=Path, help="required with --apply; must not be the input path")
    parser.add_argument("--report", type=Path, help="write the aggregate report; defaults to stdout")
    parser.add_argument("--database-url", help="optional database target; requires --apply and lineage IDs on every row")
    parser.add_argument("--preview-freeze", type=Path, help="frozen candidate-only preview selection; enables reconciliation mode")
    parser.add_argument("--inventory", type=Path, help="measured inventory matching --preview-freeze")
    parser.add_argument("--expected-database", help="required loopback database name: approved isolated preview target")
    args = parser.parse_args()
    if args.preview_freeze:
        if args.input is not None or args.output is not None:
            parser.error("frozen-preview mode does not accept JSONL input or --output")
        if args.inventory is None or args.expected_database is None:
            parser.error("--preview-freeze requires --inventory and --expected-database")
        database_url = args.database_url or os.environ.get("UEC_DATABASE_URL")
        if not database_url:
            parser.error("frozen-preview mode requires --database-url or UEC_DATABASE_URL")
        try:
            _validate_preview_database_url(database_url, args.expected_database)
        except ValueError as error:
            parser.error(str(error))
        if args.report and args.report.resolve() in {args.preview_freeze.resolve(), args.inventory.resolve()}:
            parser.error("--report must not overwrite freeze or inventory")
        import psycopg
        try:
            with psycopg.connect(database_url) as connection:
                report = reconcile_preview_freeze(connection, args.preview_freeze, args.inventory,
                                                  apply_changes=args.apply, expected_database=args.expected_database)
        except Exception as error:
            blocked = _blocked_report(error)
            payload = json.dumps(blocked, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
            if args.report:
                args.report.parent.mkdir(parents=True, exist_ok=True)
                args.report.write_text(payload, encoding="utf-8")
            else:
                sys.stderr.write(payload)
            return 1
    else:
        if args.input is None:
            parser.error("JSONL mode requires input, or use --preview-freeze")
        if args.inventory or args.expected_database:
            parser.error("--inventory and --expected-database require --preview-freeze")
    if args.apply and not args.preview_freeze and (args.output is None or args.output.resolve() == args.input.resolve()):
        parser.error("--apply requires --output distinct from input")
    if not args.apply and args.output is not None:
        parser.error("--output requires --apply")
    if args.report and args.input and args.report.resolve() == args.input.resolve():
        parser.error("--report must not overwrite input")
    if args.apply and not args.preview_freeze and args.report and args.output.resolve() == args.report.resolve():
        parser.error("--report and --output must be distinct paths")
    if not args.preview_freeze and args.database_url and not args.apply:
        parser.error("--database-url requires --apply; dry runs are non-mutating")
    if not args.preview_freeze:
        rows = read_jsonl(args.input)
        projected, report = reproject(rows)
        if args.apply:
            if args.database_url:
                import psycopg
                with psycopg.connect(args.database_url) as connection:
                    for row in projected:
                        source_id = str(row.get("source_id") or "")
                        document = crosswalk_document(source_id)
                        assignment_rows = persistence_assignments(row["taxonomy"])
                        preview = row.get("preview_lineage") if isinstance(row.get("preview_lineage"), dict) else row
                        if all(preview.get(key) for key in ("candidate_id", "representative_observation_id", "snapshot_sha256")):
                            persist_preview_candidate_assignment_set(
                                connection,
                                candidate_id=str(preview["candidate_id"]),
                                representative_observation_id=str(preview["representative_observation_id"]),
                                snapshot_sha256=str(preview["snapshot_sha256"]),
                                source_id=source_id,
                                document=document,
                                assignment_rows=assignment_rows,
                            )
                        elif all(row.get(key) for key in ("observation_id", "source_record_id", "artifact_id")):
                            persist_uec_assignment_set(
                                connection,
                                observation_id=str(row["observation_id"]),
                                source_record_id=str(row["source_record_id"]),
                                artifact_id=str(row["artifact_id"]),
                                document=document,
                                assignment_rows=assignment_rows,
                            )
                        else:
                            raise ValueError("database reprojection row lacks genuine UEC or real_preview lineage")
            atomic_jsonl(args.output, projected)
            report["applied"] = True
            report["output"] = str(args.output)
        else:
            report["applied"] = False
    payload = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(payload, encoding="utf-8")
    else:
        sys.stdout.write(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
