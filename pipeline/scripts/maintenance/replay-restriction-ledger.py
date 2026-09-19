"""Replay an external, payload-free restriction ledger into a restored DB.

Only opaque source_id/source_record_key references are read from the ledger.
The transaction fails if a reference is absent or ambiguous, so a partial
replay can never be mistaken for a safe restore. This command is for private
staging/recovery; the service-start gate must run after it.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path



def _require_psycopg():
    """Load the database driver only for operations that contact PostgreSQL."""
    try:
        import psycopg
    except ModuleNotFoundError as exc:
        raise RuntimeError("database replay requires the 'psycopg' package; install pipeline requirements") from exc
    return psycopg


def _ledger_module():
    path = Path(__file__).with_name("restriction-ledger-gate.py")
    spec = importlib.util.spec_from_file_location("restriction_ledger_gate", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("restriction ledger verifier is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def replay(database_url: str, ledger_path: Path, actor: str = "external-ledger-replay") -> dict[str, int | str]:
    verifier = _ledger_module()
    ledger = verifier.load_ledger(ledger_path)
    psycopg = _require_psycopg()
    restrictions = ledger["active_restrictions"]
    if any(item.get("scope") != "whole_record" for item in restrictions):
        raise ValueError("ledger replay supports only whole_record suppression references")
    applied = 0
    with psycopg.connect(database_url) as connection:
        with connection.transaction():
            for item in restrictions:
                rows = connection.execute(
                    "SELECT source_record_id FROM uec.source_records WHERE source_id = %s AND source_record_key = %s",
                    (item["source_id"], item["source_record_key"]),
                ).fetchall()
                if len(rows) != 1:
                    raise ValueError("restriction reference is absent or ambiguous in restored database")
                record_id = rows[0][0]
                inserted = connection.execute(
                    """
                    INSERT INTO uec.record_access_events
                        (source_record_id, action, reason_category, policy_version, maintainer, note)
                    SELECT %s, 'public_access_revoked', 'privacy', 'ethics-v1', %s, 'External restriction ledger replay'
                    WHERE NOT EXISTS (
                        SELECT 1 FROM uec.record_access_current
                        WHERE source_record_id = %s AND action = 'public_access_revoked'
                    )
                    RETURNING access_event_id
                    """,
                    (record_id, actor, record_id),
                ).fetchone()
                applied += int(inserted is not None)
    return {"status": "pass", "ledger_revision": ledger["revision"], "reference_count": len(restrictions), "new_events": applied}


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def replay_sql(ledger_path: Path, actor: str = "external-ledger-replay") -> str:
    """Emit safe, idempotent SQL for a portless recovery container."""
    verifier = _ledger_module()
    ledger = verifier.load_ledger(ledger_path)
    restrictions = ledger["active_restrictions"]
    if any(item.get("scope") != "whole_record" for item in restrictions):
        raise ValueError("ledger replay supports only whole_record suppression references")
    statements = ["BEGIN;"]
    for item in restrictions:
        source_id = _sql_literal(item["source_id"])
        source_key = _sql_literal(item["source_record_key"])
        actor_sql = _sql_literal(actor)
        statements.append(f"""
DO $$
DECLARE matched_count integer;
BEGIN
    SELECT count(*) INTO matched_count
    FROM uec.source_records
    WHERE source_id = {source_id} AND source_record_key = {source_key};
    IF matched_count <> 1 THEN
        RAISE EXCEPTION 'restriction reference is absent or ambiguous in restored database';
    END IF;
    INSERT INTO uec.record_access_events
        (source_record_id, action, reason_category, policy_version, maintainer, note)
    SELECT source_record_id, 'public_access_revoked', 'privacy', 'ethics-v1', {actor_sql}, 'External restriction ledger replay'
    FROM uec.source_records
    WHERE source_id = {source_id} AND source_record_key = {source_key}
      AND NOT EXISTS (
          SELECT 1 FROM uec.record_access_current current_access
          WHERE current_access.source_record_id = uec.source_records.source_record_id
            AND current_access.action = 'public_access_revoked'
      );
END $$;""".strip())
    statements.append("COMMIT;")
    return "\n".join(statements) + "\n"


def write_replayed_snapshot(database_url: str, ledger_path: Path, output: Path) -> dict[str, int | str]:
    """Write a row-free snapshot after confirming each reference is suppressed."""
    verifier = _ledger_module()
    ledger = verifier.load_ledger(ledger_path)
    psycopg = _require_psycopg()
    restrictions = ledger["active_restrictions"]
    if any(item.get("scope") != "whole_record" for item in restrictions):
        raise ValueError("snapshot export supports only whole_record suppression references")
    with psycopg.connect(database_url) as connection:
        with connection.transaction():
            for item in restrictions:
                count = connection.execute(
                    """
                    SELECT count(*)
                    FROM uec.source_records source_record
                    WHERE source_record.source_id = %s
                      AND source_record.source_record_key = %s
                      AND EXISTS (
                          SELECT 1 FROM uec.public_access_restricted restricted
                          WHERE restricted.source_record_id = source_record.source_record_id
                      )
                    """,
                    (item["source_id"], item["source_record_key"]),
                ).fetchone()[0]
                if count != 1:
                    raise ValueError("restriction reference is not currently suppressed in restored database")
    snapshot = {
        "ledger_revision": ledger["revision"],
        "ledger_sha256": ledger["ledger_sha256"],
        "active_restrictions": restrictions,
    }
    if not output.parent.is_dir():
        raise ValueError("snapshot output directory is unavailable")
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=output.parent, prefix=f".{output.name}.", delete=False) as handle:
        handle.write(json.dumps(snapshot, sort_keys=True, separators=(",", ":")) + "\n")
        temporary = Path(handle.name)
    os.replace(temporary, output)
    return {"status": "pass", "ledger_revision": ledger["revision"], "reference_count": len(restrictions)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.environ.get("UEC_DATABASE_URL"))
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--actor", default="external-ledger-replay")
    parser.add_argument("--emit-sql", action="store_true", help="emit idempotent SQL for a portless recovery container")
    parser.add_argument("--snapshot-output", type=Path, help="write a row-free post-replay snapshot after database verification")
    args = parser.parse_args()
    if not args.database_url and not args.emit_sql:
        parser.error("--database-url or UEC_DATABASE_URL is required")
    try:
        if args.emit_sql and args.snapshot_output:
            parser.error("--emit-sql and --snapshot-output cannot be combined")
        if args.emit_sql:
            print(replay_sql(args.ledger, args.actor), end="")
        else:
            result = replay(args.database_url, args.ledger, args.actor)
            if args.snapshot_output:
                result = write_replayed_snapshot(args.database_url, args.ledger, args.snapshot_output)
            print(json.dumps(result, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
