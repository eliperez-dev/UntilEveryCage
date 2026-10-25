#!/usr/bin/env python3
"""Append the versioned Germany BLtU taxonomy projection to the private preview.

Dry-run is read-only. --apply only inserts immutable assignment sets through
the shared taxonomy persistence API; source observations and candidate rows are
never changed.
"""
from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from typing import Any

import psycopg

from pipeline.taxonomy.persistence import persist_preview_candidate_assignment_set
from pipeline.taxonomy_crosswalk import (
    crosswalk_document,
    persistence_assignments,
    project_observation,
)


SOURCE_ID = "de.locations"
EXPECTED_DATABASE = "uec_launch_sources_test_20261025"
CROSSWALK_VERSION = "de-bltu-source-crosswalk-v1"


def _as_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if item is not None and str(item).strip()]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list):
            return [str(item) for item in parsed if item is not None and str(item).strip()]
        return [value] if value.strip() else []
    return [str(value)]


def project_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    """Project only retained source activity code/label values."""
    return project_observation({
        "source_id": SOURCE_ID,
        "normalized": {
            "activity_codes": _as_values(candidate.get("source_activity_codes")),
            "activity_descriptions": _as_values(candidate.get("source_activity_labels")),
        },
    })


def reproject(database_url: str, *, apply_changes: bool = False) -> dict[str, Any]:
    with psycopg.connect(database_url) as connection:
        with connection.transaction():
            connection.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE" +
                               ("" if apply_changes else ", READ ONLY"))
            actual_database = connection.execute("SELECT current_database()").fetchone()[0]
            if actual_database != EXPECTED_DATABASE:
                raise RuntimeError("database_identity_invalid")

            latest = connection.execute(
                """SELECT COALESCE(
                       (SELECT run.snapshot_sha256 FROM real_preview.source_preview_runs run
                        WHERE run.source_id=%s ORDER BY run.created_at DESC,run.run_id DESC LIMIT 1),
                       (SELECT manifest.snapshot_sha256 FROM real_preview.source_manifests manifest
                        WHERE manifest.source_id=%s ORDER BY manifest.retrieved_at DESC,manifest.snapshot_sha256 DESC LIMIT 1)
                   )""",
                (SOURCE_ID, SOURCE_ID),
            ).fetchone()
            snapshot = latest[0] if latest else None
            if not snapshot:
                raise RuntimeError("latest_snapshot_missing")
            rows = connection.execute(
                """SELECT candidate_id::text,representative_observation_id::text,
                          snapshot_sha256,source_id,source_activity_codes,source_activity_labels
                     FROM real_preview.candidates
                    WHERE source_id=%s AND snapshot_sha256=%s
                    ORDER BY candidate_id""",
                (SOURCE_ID, snapshot),
            ).fetchall()
            if not rows:
                raise RuntimeError("latest_snapshot_has_no_candidates")

            before = connection.execute(
                """SELECT count(*) FROM real_preview.candidate_taxonomy_assignment_sets
                    WHERE source_id=%s AND snapshot_sha256=%s AND crosswalk_version=%s""",
                (SOURCE_ID, snapshot, CROSSWALK_VERSION),
            ).fetchone()[0]
            status_counts: Counter[str] = Counter()
            primary_counts: Counter[str] = Counter()
            document = crosswalk_document(SOURCE_ID)
            if document["crosswalk_version"] != CROSSWALK_VERSION:
                raise RuntimeError("germany_crosswalk_version_mismatch")

            for row in rows:
                candidate = {
                    "source_activity_codes": row[4],
                    "source_activity_labels": row[5],
                }
                projected = project_candidate(candidate)
                status_counts[projected["taxonomy_mapping_status"]] += 1
                for primary in projected["taxonomy_primaries"]:
                    primary_counts[primary] += 1
                if apply_changes:
                    persist_preview_candidate_assignment_set(
                        connection,
                        candidate_id=row[0],
                        representative_observation_id=row[1],
                        snapshot_sha256=row[2],
                        source_id=row[3],
                        document=document,
                        assignment_rows=persistence_assignments(projected),
                    )

            after = before
            if apply_changes:
                after = connection.execute(
                    """SELECT count(*) FROM real_preview.candidate_taxonomy_assignment_sets
                        WHERE source_id=%s AND snapshot_sha256=%s AND crosswalk_version=%s""",
                    (SOURCE_ID, snapshot, CROSSWALK_VERSION),
                ).fetchone()[0]
                if int(after) != len(rows):
                    raise RuntimeError("germany_assignment_set_count_mismatch")

            return {
                "mode": "applied" if apply_changes else "dry_run",
                "source_id": SOURCE_ID,
                "candidate_count": len(rows),
                "existing_assignment_sets": int(before),
                "current_assignment_sets": int(after),
                "expected_assignment_sets": len(rows),
                "mapping_status_counts": dict(sorted(status_counts.items())),
                "mapped_primary_counts": dict(sorted(primary_counts.items())),
                "new_public_rows": 0,
                "source_rows_modified": 0,
            }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.environ.get("UEC_DATABASE_URL"))
    parser.add_argument("--apply", action="store_true", help="append Germany-only assignment sets")
    args = parser.parse_args()
    if not args.database_url:
        return 2
    try:
        report = reproject(args.database_url, apply_changes=args.apply)
    except Exception as error:
        print(f"germany_taxonomy_reprojection_failed: {type(error).__name__}")
        return 1
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
