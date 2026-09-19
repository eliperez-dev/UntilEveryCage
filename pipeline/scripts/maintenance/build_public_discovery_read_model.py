#!/usr/bin/env python3
"""Build the manifest-bound public discovery read model atomically."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any

import psycopg

# Keep the documented ``python pipeline/scripts/...`` invocation independent
# of the caller's PYTHONPATH.
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
import sys
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from pipeline.common.source_rights import require_cleared


class ReadModelBlocked(ValueError):
    """The read model cannot safely be activated."""


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise ReadModelBlocked("read model timestamp lacks timezone")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def content_digest(rows: list[tuple[Any, ...]]) -> str:
    digest = hashlib.sha256()
    for row in rows:
        values = []
        for value in row:
            if isinstance(value, memoryview):
                value = value.tobytes().hex()
            elif isinstance(value, bytes):
                value = value.hex()
            elif isinstance(value, datetime):
                value = _timestamp(value)
            values.append("" if value is None else str(value))
        digest.update(("\t".join(values) + "\n").encode("utf-8"))
    return digest.hexdigest()


def _release_manifest(connection: Any, release_id: str) -> str:
    release = connection.execute(
        "SELECT status, test_only, profile FROM uec.releases WHERE release_id=%s",
        (release_id,),
    ).fetchone()
    if not release:
        raise ReadModelBlocked("release is missing")
    if release[0] != "promoted" or release[1]:
        raise ReadModelBlocked("only a non-test promoted release can build a read model")
    stored = connection.execute(
        "SELECT manifest::text, manifest_sha256 FROM uec.release_manifests WHERE release_id=%s",
        (release_id,),
    ).fetchone()
    if not stored:
        raise ReadModelBlocked("release manifest is missing")
    manifest = json.loads(stored[0])
    actual = hashlib.sha256(canonical_json(manifest).encode("utf-8")).hexdigest()
    if actual != stored[1]:
        raise ReadModelBlocked("release manifest checksum mismatch")
    if manifest.get("release_id") != release_id or manifest.get("profile") != release[2]:
        raise ReadModelBlocked("release manifest identity mismatch")
    return stored[1]


# This is deliberately release-scoped and mirrors the live gates in migration
# 037.  The older map_facilities_display_history compatibility view expands its
# public_access_restricted UNION before applying the release predicate, which
# turns a high-volume build into an all-source-records scan.  Keeping the
# review, access, and suppression predicates correlated here changes only the
# plan shape; it does not freeze or bypass a publication decision.
SOURCE_ROWS = """
WITH eligible AS (
    SELECT member.release_id,
           observation.observation_id,
           observation.facility_id,
           observation.source_record_id,
           observation.classification_category,
           observation.first_observed_at,
           observation.observed_at,
           facility.canonical_name,
           facility.country_code,
           facility.postal_code,
           facility.city,
           source.origin_type AS provenance_origin_type,
           source.source_id AS provenance_source_id,
           source.name AS provenance_source_name,
           source.official_url AS provenance_source_url,
           artifact.retrieved_at AS provenance_retrieved_at,
           review.factual_review_status,
           review.privacy_screening_status,
           review.maintainer_approval,
           review.reviewer_role
    FROM uec.release_members member
    JOIN uec.releases release
      ON release.release_id = member.release_id
    JOIN uec.observations observation
      ON observation.observation_id = member.observation_id
    JOIN uec.facilities facility
      ON facility.facility_id = member.facility_id
    JOIN uec.source_records record
      ON record.source_record_id = observation.source_record_id
    JOIN uec.sources source
      ON source.source_id = record.source_id
    JOIN uec.raw_artifacts artifact
      ON artifact.artifact_id = record.artifact_id
    JOIN LATERAL (
        SELECT review.factual_review_status,
               review.privacy_screening_status,
               review.maintainer_approval,
               review.reviewer_role,
               review.publication_eligible
        FROM uec.publication_review_events review
        JOIN uec.publication_review_release_scopes scope
          ON scope.publication_review_event_id = review.publication_review_event_id
         AND scope.release_id = member.release_id
        WHERE review.source_record_id = observation.source_record_id
        ORDER BY review.reviewed_at DESC, review.publication_review_event_id DESC
        LIMIT 1
    ) review ON true
    WHERE member.release_id=%s
      AND release.status = 'promoted'
      AND release.test_only IS NOT TRUE
      AND member.default_visible = true
      AND review.publication_eligible = true
      AND review.privacy_screening_status = 'passed'
      AND review.factual_review_status <> 'rejected'
      AND (
          review.maintainer_approval = 'approved'
          OR (release.profile = 'community'
              AND source.origin_type = 'user_submitted'
              AND review.factual_review_status = 'unreviewed'
              AND review.maintainer_approval = 'pending')
      )
      AND NOT EXISTS (
          SELECT 1
          FROM uec.record_access_current access
          WHERE access.source_record_id = observation.source_record_id
            AND access.action = 'public_access_revoked'
      )
      AND NOT EXISTS (
          SELECT 1
          FROM uec.suppression_case_current current_case
          JOIN uec.suppression_cases case_record
            ON case_record.case_id = current_case.case_id
          JOIN uec.suppression_references ref
            ON ref.case_id = case_record.case_id
          JOIN uec.source_records suppressed_record ON (
              (ref.facility_id IS NOT NULL AND (
                  EXISTS (SELECT 1 FROM uec.facility_source_links link
                          WHERE link.facility_id = ref.facility_id
                            AND link.source_record_id = suppressed_record.source_record_id)
                  OR EXISTS (SELECT 1 FROM uec.observations restricted_observation
                             WHERE restricted_observation.facility_id = ref.facility_id
                               AND restricted_observation.source_record_id = suppressed_record.source_record_id)
              ))
              OR (ref.source_id = suppressed_record.source_id
                  AND ref.source_record_key = suppressed_record.source_record_key)
          )
          WHERE current_case.event_type = 'suppressed'
            AND case_record.status IN ('active', 'review', 'closed', 'expired')
            AND suppressed_record.source_record_id = observation.source_record_id
      )
)
SELECT eligible.facility_id,
       eligible.observation_id,
       eligible.source_record_id,
       eligible.canonical_name,
       eligible.country_code,
       eligible.postal_code,
       eligible.city,
       CASE WHEN geocode.status = 'accepted' AND geocode.result IS NOT NULL THEN geocode.result
            WHEN geocode.status = 'review_required' THEN city.reference_location ELSE NULL END AS display_location,
       CASE WHEN geocode.status = 'accepted' AND geocode.result IS NOT NULL THEN 'exact'
            WHEN geocode.status = 'review_required' AND city.reference_location IS NOT NULL THEN 'city'
            ELSE 'unmapped' END AS display_precision,
       CASE WHEN geocode.status = 'accepted' AND geocode.result IS NOT NULL THEN 'Accepted geocoder result'
            WHEN geocode.status = 'review_required' AND city.reference_location IS NOT NULL THEN 'Approximate city location — multiple geocoder matches'
            ELSE 'No publishable location' END AS display_label,
       geocode.status AS geocoding_status,
       geocode.provider_id AS geocoder_provider,
       geocode.queried_at AS geocoded_at,
       eligible.classification_category,
       eligible.observed_at,
       eligible.first_observed_at,
       eligible.provenance_origin_type,
       eligible.provenance_source_id,
       eligible.provenance_source_name,
       eligible.provenance_source_url,
       eligible.provenance_retrieved_at,
       CASE WHEN source.attribution IS NULL OR btrim(source.attribution) = ''
            THEN 'cleared' ELSE 'attribution_required' END AS source_rights_status
FROM eligible
JOIN uec.sources source ON source.source_id = eligible.provenance_source_id
LEFT JOIN LATERAL (
    SELECT status, result, provider_id, queried_at
    FROM uec.geocode_results
    WHERE source_record_id = eligible.source_record_id
    ORDER BY queried_at DESC, geocode_result_id DESC
    LIMIT 1
) geocode ON true
LEFT JOIN LATERAL (
    SELECT reference_location
    FROM uec.city_reference_points
    WHERE country_code = eligible.country_code
      AND lower(city_name) = lower(eligible.city)
      AND (postal_code IS NULL OR postal_code = eligible.postal_code)
    ORDER BY postal_code NULLS LAST
    LIMIT 1
) city ON true
ORDER BY eligible.facility_id, eligible.observation_id
"""


SELECT_ROWS = """
SELECT facility_id, observation_id, source_record_id, canonical_name,
       country_code, postal_code, city, ST_AsText(display_location::geometry),
       display_precision, display_label, geocoding_status, geocoder_provider,
       geocoded_at, classification_category, observed_at, first_observed_at,
       provenance_origin_type, provenance_source_id, provenance_source_name,
       provenance_source_url, provenance_retrieved_at, source_rights_status
FROM (
""" + SOURCE_ROWS + """
) selected
"""


# Keep the normal activation path set-based.  The source projection is already
# ordered and validated above for its content digest; inserting the same rows
# one at a time makes a large, otherwise safe build spend most of its time in
# client/server round trips.  The live safety view remains the sole source of
# rows, and activation is still committed together with its metadata.
INSERT_ROWS = """
INSERT INTO uec.public_discovery_read_model_rows
    (release_id,facility_id,observation_id,source_record_id,canonical_name,
     country_code,postal_code,city,display_location,display_precision,
     display_label,geocoding_status,geocoder_provider,geocoded_at,
     classification_category,observed_at,first_observed_at,
     provenance_origin_type,provenance_source_id,provenance_source_name,
     provenance_source_url,provenance_retrieved_at,source_rights_status)
SELECT %s, facility_id, observation_id, source_record_id, canonical_name,
       country_code, postal_code, city, display_location, display_precision,
       display_label, geocoding_status, geocoder_provider, geocoded_at,
       classification_category, observed_at, first_observed_at,
       provenance_origin_type, provenance_source_id, provenance_source_name,
       provenance_source_url, provenance_retrieved_at, source_rights_status
FROM (
""" + SOURCE_ROWS + """
) selected
"""


def build(database_url: str, release_id: str, fail_after_rows: int | None = None) -> dict[str, Any]:
    with psycopg.connect(database_url) as connection:
        with connection.transaction():
            manifest_sha256 = _release_manifest(connection, release_id)
            require_cleared(connection, release_id)
            rows = connection.execute(SELECT_ROWS, (release_id,)).fetchall()
            content_sha256 = content_digest(rows)
            existing = connection.execute(
                "SELECT manifest_sha256, content_sha256, row_count FROM uec.public_discovery_read_models WHERE release_id=%s",
                (release_id,),
            ).fetchone()
            if existing:
                if existing != (manifest_sha256, content_sha256, len(rows)):
                    raise ReadModelBlocked("existing read model does not match the current release content")
                stored_rows = connection.execute(
                    "SELECT count(*) FROM uec.public_discovery_read_model_rows WHERE release_id=%s",
                    (release_id,),
                ).fetchone()[0]
                if stored_rows != len(rows):
                    raise ReadModelBlocked("read model metadata exists but row storage is incomplete")
                return {"status": "idempotent", "release_id": release_id, "manifest_sha256": manifest_sha256, "content_sha256": content_sha256, "row_count": len(rows)}

            if fail_after_rows is not None:
                # This hook deliberately retains the row-at-a-time path so
                # tests can interrupt after a known prefix and prove rollback.
                insert_sql = """
                    INSERT INTO uec.public_discovery_read_model_rows
                    (release_id,facility_id,observation_id,source_record_id,canonical_name,
                     country_code,postal_code,city,display_location,display_precision,
                     display_label,geocoding_status,geocoder_provider,geocoded_at,
                     classification_category,observed_at,first_observed_at,
                     provenance_origin_type,provenance_source_id,provenance_source_name,
                     provenance_source_url,provenance_retrieved_at,source_rights_status)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,ST_GeogFromText(%s),%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """
                with connection.cursor() as cursor:
                    for index, row in enumerate(rows, start=1):
                        cursor.execute(insert_sql, (release_id, *row))
                        if index >= fail_after_rows:
                            raise RuntimeError("synthetic interrupted read model build")
            else:
                connection.execute(INSERT_ROWS, (release_id, release_id))
            connection.execute(
                "INSERT INTO uec.public_discovery_read_models (release_id,manifest_sha256,content_sha256,row_count) VALUES (%s,%s,%s,%s)",
                (release_id, manifest_sha256, content_sha256, len(rows)),
            )
            return {"status": "built", "release_id": release_id, "manifest_sha256": manifest_sha256, "content_sha256": content_sha256, "row_count": len(rows)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("release_id")
    parser.add_argument("--database-url", default=os.environ.get("UEC_DATABASE_URL", "postgresql://uec:uec-local-development-only@localhost:5433/uec"))
    args = parser.parse_args()
    try:
        print(json.dumps(build(args.database_url, args.release_id), sort_keys=True))
    except Exception as error:
        print(json.dumps({"status": "blocked", "error": str(error)}, sort_keys=True))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
