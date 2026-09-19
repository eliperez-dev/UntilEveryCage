#!/usr/bin/env python3
"""Package one explicitly promoted, public release as CSV and GeoJSON.

The query is intentionally release/profile scoped and repeats the publication
and suppression gates. It never reads raw fields and never promotes a release.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import timezone
from pathlib import Path

import psycopg

# Keep the documented ``python pipeline/scripts/...`` invocation independent
# of the caller's PYTHONPATH.
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from pipeline.common.data_product import SUPPORTED_PROFILES, write_package
from pipeline.common.source_rights import require_cleared


def _utc(value) -> str:
    if value is None:
        raise ValueError("release metadata has no timestamp")
    if value.tzinfo is None:
        raise ValueError("release metadata timestamp has no timezone")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _rights(attribution: str | None) -> str:
    return "attribution_required" if attribution and attribution.strip() else "unknown"


def export_release(database_url: str, release_id: str, profile: str, output_dir: Path, generated_at: str | None = None) -> dict:
    if profile not in SUPPORTED_PROFILES:
        raise ValueError("profile is unsupported")
    with psycopg.connect(database_url) as connection:
        with connection.transaction():
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            release = connection.execute(
                """
                SELECT release_id, profile, status, test_only, ruleset_version, created_at
                FROM uec.releases
                WHERE release_id=%s AND profile=%s
                """,
                (release_id, profile),
            ).fetchone()
            if not release:
                raise ValueError("release/profile not found")
            if release[2] != "promoted" or release[3]:
                raise ValueError("only a non-test promoted release can be packaged")
            require_cleared(connection, release_id)
            rows = connection.execute(
                """
                SELECT h.facility_id, h.canonical_name, h.country_code, h.city,
                       h.classification_category, h.display_precision,
                       ST_Y(h.display_location::geometry), ST_X(h.display_location::geometry),
                       h.lifecycle_status, h.first_observed_at, h.last_observed_at,
                       h.observation_count, h.provenance_origin_type,
                       review.factual_review_status, review.privacy_screening_status,
                       review.maintainer_approval, review.reviewer_role,
                       h.provenance_source_id, h.provenance_source_name,
                       h.provenance_source_url, h.provenance_retrieved_at,
                       source.attribution
                FROM uec.map_facilities_display_history h
                JOIN uec.releases release ON release.release_id=h.release_id
                JOIN uec.publication_review_release_current review
                  ON review.source_record_id=h.source_record_id
                 AND review.release_id=h.release_id
                JOIN uec.sources source ON source.source_id=h.provenance_source_id
                WHERE h.release_id=%s
                  AND release.status='promoted'
                  AND release.test_only IS NOT TRUE
                  AND release.profile=%s
                  AND review.publication_eligible=true
                  AND review.privacy_screening_status='passed'
                  AND (release.profile='community' OR review.maintainer_approval='approved')
                  AND NOT EXISTS (
                    SELECT 1 FROM uec.public_access_restricted restricted
                    WHERE restricted.source_record_id=h.source_record_id
                  )
                ORDER BY h.facility_id, h.provenance_source_id
                """,
                (release_id, profile),
            ).fetchall()

    projection = []
    for row in rows:
        # require_cleared above proves the decision; attribution remains an
        # independent presentation obligation and does not grant clearance.
        rights = "attribution_required" if row[21] and row[21].strip() else "cleared"
        projection.append(
            {
                "facility_id": str(row[0]), "canonical_name": row[1], "country_code": row[2],
                "city": row[3], "category": row[4], "display_precision": row[5],
                "latitude": row[6], "longitude": row[7], "lifecycle_status": row[8],
                "first_observed_at": _utc(row[9]) if row[9] else None,
                "last_observed_at": _utc(row[10]) if row[10] else None,
                "observation_count": row[11], "source_type": row[12],
                "factual_review_status": row[13] or "unreviewed",
                "privacy_screening_status": row[14], "project_approval": row[15],
                "reviewer_role": row[16],
                "publication_warning": (
                    "Unreviewed community claim — not verified by Until Every Cage"
                    if profile == "community" and (row[13] or "unreviewed") == "unreviewed" else None
                ),
                "publication_profile": profile, "release_id": release_id,
                "release_ruleset_version": release[4], "provenance_source_id": row[17],
                "provenance_source_name": row[18], "provenance_source_url": row[19],
                "provenance_retrieved_at": _utc(row[20]), "source_rights_status": rights,
                "source_attribution": row[21],
                "publication_eligible": True,
            }
        )
    by_source = defaultdict(list)
    for row in projection:
        by_source[row["provenance_source_id"]].append(row)
    coverage = [
        {
            "source_id": source_id,
            "row_count": len(source_rows),
            "retrieved_at": {"first": min(r["provenance_retrieved_at"] for r in source_rows), "last": max(r["provenance_retrieved_at"] for r in source_rows)},
            "rights_status": sorted({r["source_rights_status"] for r in source_rows}),
            "attribution": sorted({r["source_attribution"] for r in source_rows if r.get("source_attribution")}),
        }
        for source_id, source_rows in sorted(by_source.items())
    ]
    retrieved = min((r["provenance_retrieved_at"] for r in projection), default=_utc(release[5]))
    metadata = {
        "release_id": release_id, "profile": profile, "status": "promoted", "test_only": False,
        "eligible": True, "publication_state": "project-published", "ruleset_version": release[4],
        "schema_version": "uec-location-projection-v1", "generated_at": generated_at or _utc(release[5]),
        "retrieved_at": retrieved, "source_coverage": coverage,
        "row_counts": {"eligible_rows": len(projection)},
        "checksums": {},
        "review_state": "privacy-screened; may contain community-unreviewed claims" if profile == "community" else "project-approved and privacy-screened",
        "limitations": [
            "Facility projection rows are not animal counts or a complete story-wide denominator.",
            "Coordinates are exact or city-level display points only; unmapped and privacy-restricted locations are omitted.",
            "Source availability and government origin do not certify factual accuracy or current operation.",
            "Reuse is limited to the per-source rights status in each row; no project licence is implied.",
        ],
        "supersedes": None,
    }
    # write_package computes the projection checksum after validating all rows.
    return write_package(output_dir, metadata, projection)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("release_id")
    parser.add_argument("--profile", required=True, choices=sorted(SUPPORTED_PROFILES))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--database-url", default=os.environ.get("UEC_DATABASE_URL", "postgresql://uec:uec-local-development-only@localhost:5433/uec"))
    parser.add_argument("--generated-at", help="Stable UTC timestamp for reproducible packaging; defaults to release creation time")
    args = parser.parse_args()
    try:
        result = export_release(args.database_url, args.release_id, args.profile, args.output_dir, args.generated_at)
    except Exception as error:
        print(json.dumps({"status": "blocked", "error": str(error)}), file=sys.stderr)
        return 1
    print(json.dumps({"status": "packaged", "manifest_sha256": result["manifest_sha256"], "output_dir": str(args.output_dir)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
