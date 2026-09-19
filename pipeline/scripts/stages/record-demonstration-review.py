#!/usr/bin/env python3
"""Append an explicit human review decision for a prepared demo release.

The review document is operator-authored.  This command records its decision;
it does not establish who is authorized, provide legal clearance, validate the
release, or promote it.
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

from pipeline.common.demonstration_release import load_review


def record(database_url: str, review_path: Path, receipt_path: Path | None = None) -> dict:
    review = load_review(review_path)
    decisions = review["decisions"]
    ids = [item["source_record_id"] for item in decisions]
    with psycopg.connect(database_url) as connection:
        with connection.transaction():
            release = connection.execute(
                "SELECT status, test_only, profile, summary FROM uec.releases WHERE release_id=%s FOR UPDATE",
                (review["release_id"],),
            ).fetchone()
            if not release:
                raise ValueError("demonstration release not found")
            if release[0] != "candidate" or release[1]:
                raise ValueError("demonstration release must be a non-test candidate")
            summary = release[3] or {}
            demo = summary.get("demonstration") if isinstance(summary, dict) else None
            if not isinstance(demo, dict) or demo.get("source_id") != review["source_id"]:
                raise ValueError("release is not a prepared demonstration for this source")
            if demo.get("source_artifact_sha256") != review["source_artifact_sha256"]:
                raise ValueError("review artifact digest does not match prepared release")
            members = connection.execute(
                """
                SELECT observation.source_record_id, source.source_id, artifact.sha256
                FROM uec.release_members member
                JOIN uec.observations observation ON observation.observation_id=member.observation_id
                JOIN uec.source_records source_record ON source_record.source_record_id=observation.source_record_id
                JOIN uec.sources source ON source.source_id=source_record.source_id
                JOIN uec.raw_artifacts artifact ON artifact.artifact_id=source_record.artifact_id
                WHERE member.release_id=%s
                ORDER BY observation.source_record_id
                """,
                (review["release_id"],),
            ).fetchall()
            member_ids = {str(row[0]) for row in members}
            if member_ids != set(ids):
                raise ValueError("review decisions must cover exactly every prepared release member")
            if any(row[1] != review["source_id"] or row[2] != review["source_artifact_sha256"] for row in members):
                raise ValueError("review source provenance does not match every release member")
            existing = connection.execute(
                "SELECT 1 FROM uec.publication_review_release_current WHERE release_id=%s AND source_record_id = ANY(%s::uuid[]) LIMIT 1",
                (review["release_id"], ids),
            ).fetchone()
            if existing:
                raise ValueError("release already has a review decision; append a separate correction event deliberately")
            for decision in decisions:
                connection.execute(
                    """
                    INSERT INTO uec.publication_review_events
                        (source_record_id,release_id,factual_review_status,privacy_screening_status,
                         maintainer_approval,publication_eligible,reviewer_role,reviewed_at,note)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (decision["source_record_id"], review["release_id"], decision["factual_review_status"], decision["privacy_screening_status"], decision["maintainer_approval"], decision["publication_eligible"], review["reviewer_role"], review["reviewed_at"], decision["note"]),
                )
            summary["demonstration"].update({
                "rights_status": review["rights_status"],
                "rights_reference": review["rights_reference"],
                "review_status": "approved",
                "reviewer_role": review["reviewer_role"],
                "reviewed_at": review["reviewed_at"],
            })
            connection.execute("UPDATE uec.releases SET summary=%s WHERE release_id=%s", (json.dumps(summary), review["release_id"]))
            receipt = {
                "status": "review_recorded",
                "release_id": review["release_id"],
                "source_id": review["source_id"],
                "source_artifact_sha256": review["source_artifact_sha256"],
                "reviewed_record_count": len(decisions),
                "rights_status": review["rights_status"],
                "review_status": "approved",
                "publication": "not-promoted",
            }
    if receipt_path:
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--database-url", default=os.environ.get("UEC_DATABASE_URL", "postgresql://uec:uec-local-development-only@localhost:5433/uec"))
    args = parser.parse_args()
    try:
        print(json.dumps(record(args.database_url, args.review, args.receipt), sort_keys=True))
        return 0
    except Exception as error:
        print(json.dumps({"status": "blocked", "error": str(error)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
