#!/usr/bin/env python3
"""Create a small, still-candidate demonstration release from a private candidate.

The selection document contains only opaque source-record UUIDs.  This stage
does not approve, validate, promote, geocode, or publish anything.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.common.demonstration_release import load_selection


def prepare(database_url: str, selection_path: Path, release_id: str, profile: str, receipt_path: Path | None = None) -> dict:
    selection = load_selection(selection_path)
    if release_id == selection["candidate_release_id"]:
        raise ValueError("demonstration release must have a new release_id")
    if profile not in {"official", "secondary", "community"}:
        raise ValueError("profile is unsupported")
    record_ids = selection["record_ids"]
    with psycopg.connect(database_url) as connection:
        with connection.transaction():
            source_release = connection.execute(
                "SELECT status, test_only, profile, ruleset_version FROM uec.releases WHERE release_id=%s",
                (selection["candidate_release_id"],),
            ).fetchone()
            if not source_release:
                raise ValueError("candidate release not found")
            if source_release[0] not in {"candidate", "validated"}:
                raise ValueError("source release must still be a candidate or validated release")
            rows = connection.execute(
                """
                SELECT member.facility_id, member.observation_id, observation.source_record_id,
                       source.source_id, artifact.sha256,
                       member.default_visible, observation.classification_review_status,
                       observation.coordinate_review_status, observation.default_visible,
                       source_record.source_state,
                       COALESCE(geocode.status, 'unresolved')
                FROM uec.release_members member
                JOIN uec.observations observation ON observation.observation_id=member.observation_id
                JOIN uec.source_records source_record ON source_record.source_record_id=observation.source_record_id
                JOIN uec.sources source ON source.source_id=source_record.source_id
                JOIN uec.raw_artifacts artifact ON artifact.artifact_id=source_record.artifact_id
                LEFT JOIN LATERAL (
                    SELECT status FROM uec.geocode_results
                    WHERE source_record_id=observation.source_record_id
                    ORDER BY queried_at DESC, geocode_result_id DESC LIMIT 1
                ) geocode ON true
                WHERE member.release_id=%s AND observation.source_record_id = ANY(%s::uuid[])
                ORDER BY observation.source_record_id
                """,
                (selection["candidate_release_id"], record_ids),
            ).fetchall()
            if len(rows) != len(record_ids):
                raise ValueError("selection contains a source record outside the candidate release")
            if any(row[3] != selection["source_id"] for row in rows):
                raise ValueError("demonstration selection must contain one source_id")
            if any(row[4] != selection["source_artifact_sha256"] for row in rows):
                raise ValueError("selection artifact digest does not match candidate rows")
            if any(not row[5] or row[6] != "approved" or row[7] != "approved" or not row[8] or row[9] in {"rejected", "superseded"} or row[10] != "accepted" for row in rows):
                raise ValueError("every selected row must already pass classification, coordinate, visibility, and source-state gates")
            summary = {
                "demonstration": {
                    "version": "uec-reviewed-demonstration-v1",
                    "source_release_id": selection["candidate_release_id"],
                    "source_id": selection["source_id"],
                    "source_artifact_sha256": selection["source_artifact_sha256"],
                    "selection_count": len(rows),
                    "selection_reason": selection["selection_reason"],
                    "rights_status": "pending",
                    "review_status": "pending",
                }
            }
            connection.execute(
                """
                INSERT INTO uec.releases(release_id,status,ruleset_version,profile,test_only,summary)
                VALUES (%s,'candidate',%s,%s,false,%s)
                """,
                (release_id, f"{source_release[3]}-demo", profile, json.dumps(summary)),
            )
            for facility_id, observation_id, *_ in rows:
                connection.execute(
                    "INSERT INTO uec.release_members(release_id,facility_id,observation_id,default_visible) VALUES (%s,%s,%s,true)",
                    (release_id, facility_id, observation_id),
                )
            receipt = {
                "status": "candidate_prepared",
                "release_id": release_id,
                "source_release_id": selection["candidate_release_id"],
                "profile": profile,
                "source_id": selection["source_id"],
                "source_artifact_sha256": selection["source_artifact_sha256"],
                "selected_record_count": len(rows),
                "test_only": False,
                "approval": "not-recorded",
                "publication": "not-promoted",
            }
    if receipt_path:
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--profile", choices=("official", "secondary", "community"), default="official")
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--database-url", default=os.environ.get("UEC_DATABASE_URL", "postgresql://uec:uec-local-development-only@localhost:5433/uec"))
    args = parser.parse_args()
    try:
        print(json.dumps(prepare(args.database_url, args.selection, args.release_id, args.profile, args.receipt), sort_keys=True))
        return 0
    except Exception as error:
        print(json.dumps({"status": "blocked", "error": str(error)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
