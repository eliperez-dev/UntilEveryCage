"""Regenerate a private FSIS graph-candidate handoff from one retained release.

This read-only replay intentionally carries only source-native establishment
IDs, selected-release source-record keys, and FSIS DBA/alternate-name fields.
It does not modify the database or create a public release.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.common.graph_candidate import write_graph_candidates
from pipeline.common.graph_persistence import require_private_graph_target


QUERY = """
SELECT DISTINCT ON (record.source_record_id)
       record.source_record_key,
       record.raw_fields->'normalized' AS normalized,
       artifact.retrieved_at AS observed_at,
       artifact.sha256 AS artifact_sha256
FROM uec.release_members member
JOIN uec.observations observation ON observation.observation_id=member.observation_id
JOIN uec.source_records record ON record.source_record_id=observation.source_record_id
JOIN uec.raw_artifacts artifact ON artifact.artifact_id=record.artifact_id
WHERE member.release_id=%s AND record.source_id='us.fsis'
ORDER BY record.source_record_id, observation.observed_at DESC, member.observation_id
"""


def _timestamp(value: Any) -> str:
    if isinstance(value, datetime):
        stamp = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return stamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return "unknown-observation-date"


def replay(database_url: str, database_name: str, release_id: str, output: Path) -> dict[str, Any]:
    if not release_id or len(release_id) > 96:
        raise ValueError("release id is invalid")
    require_private_graph_target(
        database_url, expected_database=database_name,
        purpose="private-graph-materialization-v1",
    )
    output = output.resolve()
    staging = (ROOT / "data" / "staging").resolve()
    if output != staging and staging not in output.parents:
        raise ValueError("output must be inside repository data/staging")
    if output.exists():
        raise FileExistsError("refusing to overwrite an existing replay handoff")

    with psycopg.connect(database_url, connect_timeout=15, row_factory=dict_row) as connection:
        connection.execute("SET TRANSACTION READ ONLY")
        identity = connection.execute("SELECT current_database() AS name").fetchone()
        if not identity or identity["name"] != database_name:
            raise ValueError("connected database does not match the expected private target")
        raw_rows = connection.execute(QUERY, (release_id,)).fetchall()

    artifact_ids = {str(row["artifact_sha256"]).lower() for row in raw_rows if row["artifact_sha256"]}
    if len(artifact_ids) != 1 or any(not row["artifact_sha256"] for row in raw_rows):
        raise ValueError("selected FSIS release must resolve to exactly one retained source artifact")

    records: list[dict[str, Any]] = []
    aliases_bearing = 0
    for index, row in enumerate(raw_rows, start=1):
        normalized = row["normalized"]
        if not isinstance(normalized, dict):
            continue
        native_id = normalized.get("establishment_id") or normalized.get("establishment_number")
        source_record_key = row["source_record_key"]
        if not isinstance(native_id, str) or not native_id.strip() or not isinstance(source_record_key, str) or not source_record_key.strip():
            continue
        safe_normalized = {
            "establishment_id": native_id.strip(),
            "alternate_names": normalized.get("alternate_names", []),
            "dba_names": normalized.get("dba_names"),
            "observed_at": _timestamp(row["observed_at"]),
        }
        aliases = safe_normalized["alternate_names"]
        has_alias = bool(aliases) or bool(safe_normalized["dba_names"])
        aliases_bearing += int(has_alias)
        records.append({
            "source_id": "us.fsis",
            "source_record_key": source_record_key,
            "source_row": index,
            "source_values": {},
            "normalized": safe_normalized,
        })
    if not records:
        raise ValueError("selected release has no usable FSIS source-native facility rows")

    manifest = write_graph_candidates(
        output, records, artifact_sha256=next(iter(artifact_ids)),
        observed_at=_timestamp(raw_rows[0]["observed_at"]),
    )
    # Preserve the original selected-release artifact identity. This makes
    # graph persistence resolve the existing source_record_id/artifact_id
    # pairs rather than minting duplicate, unbound source observations.
    manifest["source_artifact_sha256"] = next(iter(artifact_ids))
    manifest["retrieved_at_utc"] = _timestamp(raw_rows[0]["observed_at"])
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        "status": "ready",
        "release_id": release_id,
        "source_id": "us.fsis",
        "candidate_rows": manifest["candidate_rows"],
        "rows_with_alias_fields": aliases_bearing,
        "artifact_count": len(artifact_ids),
        "private_payloads_in_report": False,
        "handoff_sha256": manifest["records_sha256"],
        "output": str(output),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--database-name", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    database_url = os.environ.get("UEC_GRAPH_DATABASE_URL", "")
    if not database_url:
        print(json.dumps({"status": "blocked", "reason": "UEC_GRAPH_DATABASE_URL is required"}, sort_keys=True))
        return 2
    try:
        result = replay(database_url, args.database_name, args.release_id, args.output)
    except Exception as error:
        # Never emit driver or database details; they can contain credentials
        # or source payload snippets.
        print(json.dumps({"status": "blocked", "error_type": type(error).__name__}, sort_keys=True))
        return 2
    result.pop("output", None)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
