"""One privacy-safe geometry selection contract for public release consumers."""

from __future__ import annotations

from pipeline.common.release_cohort_review import APPROVED_GEOMETRY_MEMBERS_CTE


# The query returns one row per release member, including unmapped members.
# The first bind parameter is always release_id (used by the cohort CTE).
# Only allowlisted method/provenance metadata is projected; source queries,
# addresses, raw fields, and provider response payloads never leave evidence.
GEOMETRY_MEMBERS_CTE = APPROVED_GEOMETRY_MEMBERS_CTE + """
, member_geometry AS (
    SELECT member.release_id, member.facility_id, member.observation_id,
           observation.source_record_id, record.source_id, record.artifact_id,
           observation.coordinate,
           observation.coordinate_method,
           observation.coordinate_precision,
           observation.classification_category,
           member.default_visible,
           observation.observation AS evidence,
           CASE
             WHEN observation.observation #>> '{display_location,evidence_kind}' IS NOT NULL
               THEN observation.observation #>> '{display_location,evidence_kind}'
             WHEN observation.observation #>> '{source_location,latitude}' IS NOT NULL
              AND observation.observation #>> '{source_location,longitude}' IS NOT NULL
               THEN 'source_coordinates'
             ELSE NULL
           END AS geometry_evidence_kind,
           release.summary->>'candidate_only' = 'true' AS is_frozen_candidate,
           scope.excluded_display_categories,
           scope.geometry_interpretation_status,
           scope.classification_interpretation_status,
           approved.member_sha256 AS approved_member_sha256,
           facility.country_code, facility.city, facility.postal_code,
           latest.status AS geocode_status, latest.result AS geocode_result,
           latest.provider_id AS geocode_provider, latest.queried_at AS geocode_queried_at,
           city.reference_location
    FROM uec.release_members member
    JOIN uec.releases release ON release.release_id=member.release_id
    JOIN uec.observations observation ON observation.observation_id=member.observation_id
    JOIN uec.source_records record ON record.source_record_id=observation.source_record_id
    JOIN uec.facilities facility ON facility.facility_id=member.facility_id
    LEFT JOIN uec.release_cohort_review_current scope
      ON scope.release_id=member.release_id
     AND scope.source_id=record.source_id
     AND scope.artifact_id=record.artifact_id
    LEFT JOIN approved_geometry_members approved
      ON approved.release_id=member.release_id
     AND approved.observation_id=member.observation_id
    LEFT JOIN LATERAL (
        SELECT status, result, provider_id, queried_at
        FROM uec.geocode_results
        WHERE source_record_id=observation.source_record_id
        ORDER BY queried_at DESC, geocode_result_id DESC LIMIT 1
    ) latest ON true
    LEFT JOIN LATERAL (
        SELECT reference_location
        FROM uec.city_reference_points
        WHERE country_code=facility.country_code
          AND lower(city_name)=lower(facility.city)
          AND (postal_code IS NULL OR postal_code=facility.postal_code)
        ORDER BY postal_code NULLS LAST LIMIT 1
    ) city ON true
    WHERE member.release_id=%s
), eligibility AS (
    SELECT member_geometry.*,
           CASE WHEN is_frozen_candidate THEN
             approved_member_sha256 IS NOT NULL
             AND classification_interpretation_status='approved'
             AND NOT (COALESCE(excluded_display_categories, '[]'::jsonb) ?
                      COALESCE(classification_category, 'unclassified'))
           ELSE true END AS approved_member_ok,
           CASE WHEN is_frozen_candidate THEN
             (geometry_evidence_kind='source_coordinates'
              OR (geometry_evidence_kind='verified_coarse_reference'
                  AND evidence #>> '{display_location,evidence_id}' IS NOT NULL)
              OR (geometry_evidence_kind='provider_derived'
                  AND evidence #>> '{display_location,provider_status}'='accepted'
                  AND evidence #>> '{display_location,confidence_band}'='high'
                  AND NULLIF(btrim(evidence #>> '{display_location,provider}'),'') IS NOT NULL
                  AND NULLIF(btrim(evidence #>> '{display_location,provider_queried_at}'),'') IS NOT NULL
                  AND NULLIF(btrim(evidence #>> '{display_location,method}'),'') IS NOT NULL
                  AND NULLIF(btrim(evidence #>> '{display_location,precision}'),'') IS NOT NULL
                  AND NULLIF(btrim(evidence #>> '{display_location,evidence_id}'),'') IS NOT NULL
                  AND CASE WHEN evidence #>> '{display_location,confidence}' ~ '^[0-9]+([.][0-9]+)?$'
                           THEN (evidence #>> '{display_location,confidence}')::numeric BETWEEN 0 AND 1
                           ELSE false END))
             AND coordinate IS NOT NULL
             AND (ST_X(coordinate::geometry)<>0 OR ST_Y(coordinate::geometry)<>0)
             AND ST_X(coordinate::geometry) BETWEEN -180 AND 180
             AND ST_Y(coordinate::geometry) BETWEEN -90 AND 90
           ELSE true END AS candidate_geometry_valid
    FROM member_geometry
), eligible_geometry AS (
    SELECT eligibility.*,
           CASE
             WHEN is_frozen_candidate AND approved_member_ok AND candidate_geometry_valid
               THEN coordinate
             WHEN NOT is_frozen_candidate AND geocode_status='accepted'
                  AND geocode_result IS NOT NULL
                  AND (ST_X(geocode_result::geometry)<>0 OR ST_Y(geocode_result::geometry)<>0)
               THEN geocode_result
             WHEN NOT is_frozen_candidate AND geocode_status='review_required'
                  AND reference_location IS NOT NULL
                  AND (ST_X(reference_location::geometry)<>0 OR ST_Y(reference_location::geometry)<>0)
               THEN reference_location
             ELSE NULL::geography
           END AS display_location,
           CASE
             WHEN is_frozen_candidate AND approved_member_ok AND candidate_geometry_valid
               AND geometry_evidence_kind='source_coordinates'
               THEN 'source_reported'
             WHEN is_frozen_candidate AND approved_member_ok AND candidate_geometry_valid
               AND geometry_evidence_kind='provider_derived'
               THEN 'approximate'
             WHEN is_frozen_candidate AND approved_member_ok AND candidate_geometry_valid
               AND geometry_evidence_kind='verified_coarse_reference'
               THEN 'approximate'
             WHEN NOT is_frozen_candidate AND geocode_status='accepted'
                  AND geocode_result IS NOT NULL THEN 'exact'
             WHEN NOT is_frozen_candidate AND geocode_status='review_required'
                  AND reference_location IS NOT NULL THEN 'city'
             ELSE 'unmapped'
           END AS display_precision,
           CASE
             WHEN is_frozen_candidate AND approved_member_ok AND candidate_geometry_valid
               THEN geometry_evidence_kind
             WHEN NOT is_frozen_candidate AND geocode_status='accepted' THEN 'provider_geocode'
             WHEN NOT is_frozen_candidate AND geocode_status='review_required'
                  AND reference_location IS NOT NULL THEN 'city_reference'
             ELSE 'unmapped'
           END AS geometry_origin,
           CASE WHEN is_frozen_candidate AND approved_member_ok AND candidate_geometry_valid
                THEN COALESCE(evidence #>> '{display_location,method}', evidence #>> '{source_location,coordinate_method}', coordinate_method)
                WHEN geocode_status='accepted' THEN 'provider_geocode'
                WHEN geocode_status='review_required' AND reference_location IS NOT NULL THEN 'city_reference'
                ELSE NULL END AS geometry_method,
           CASE WHEN is_frozen_candidate AND approved_member_ok AND candidate_geometry_valid
                THEN jsonb_strip_nulls(jsonb_build_object(
                    'origin', geometry_evidence_kind,
                    'method', COALESCE(evidence #>> '{display_location,method}', evidence #>> '{source_location,coordinate_method}', coordinate_method),
                    'source_precision', COALESCE(coordinate_precision, evidence #>> '{display_location,precision}', evidence #>> '{source_location,precision}'),
                    'provider', evidence #>> '{display_location,provider}',
                    'provider_status', evidence #>> '{display_location,provider_status}',
                    'provider_queried_at', evidence #>> '{display_location,provider_queried_at}',
                    'confidence', evidence #>> '{display_location,confidence}',
                    'confidence_band', evidence #>> '{display_location,confidence_band}',
                    'coordinate_review_status', evidence #>> '{display_location,coordinate_review_status}',
                    'reference_source_id', evidence #>> '{display_location,reference_source_id}',
                    'reference_source', evidence #>> '{display_location,source}',
                    'evidence_kind', evidence #>> '{display_location,evidence_kind}',
                    'evidence_id', evidence #>> '{display_location,evidence_id}'
                ))
                WHEN geocode_status='accepted' THEN jsonb_strip_nulls(jsonb_build_object(
                    'origin', 'provider_geocode', 'method', 'provider_geocode',
                    'provider', geocode_provider, 'provider_status', geocode_status,
                    'provider_queried_at', geocode_queried_at, 'source_precision', 'provider_exact'
                ))
                WHEN geocode_status='review_required' AND reference_location IS NOT NULL
                  THEN jsonb_build_object('origin', 'city_reference', 'method', 'city_reference', 'reference_source', 'city_reference_points')
                ELSE jsonb_build_object('origin', 'unmapped') END AS geometry_provenance
    FROM eligibility
)
"""


def geometry_rows_sql(select_sql: str) -> str:
    """Prefix a SELECT consuming `eligible_geometry`; release_id is bind 1."""
    if not isinstance(select_sql, str) or not select_sql.lstrip().upper().startswith("SELECT "):
        raise ValueError("geometry query must begin with SELECT")
    return GEOMETRY_MEMBERS_CTE + "\n" + select_sql


RELEASE_GATE_METRICS_SQL = geometry_rows_sql("""
SELECT count(*)::int AS release_records,
       count(*) FILTER (WHERE geometry.default_visible)::int AS visible_records,
       count(DISTINCT geometry.observation_id)::int AS distinct_observations,
       (count(*)-count(DISTINCT geometry.observation_id))::int AS duplicate_observations,
       count(*) FILTER (WHERE geometry.default_visible AND (
           CASE WHEN geometry.is_frozen_candidate
             THEN geometry.approved_member_ok IS DISTINCT FROM true
             ELSE observation.classification_review_status<>'approved'
           END))::int AS review_visible,
       count(*) FILTER (WHERE geometry.default_visible AND geometry.display_precision='exact')::int AS exact_display_ready,
       count(*) FILTER (WHERE geometry.default_visible AND geometry.display_precision='source_reported')::int AS source_reported_display_ready,
       count(*) FILTER (WHERE geometry.default_visible AND geometry.display_precision IN ('city','approximate'))::int AS coarse_display_ready,
       count(*) FILTER (WHERE geometry.default_visible AND geometry.display_precision='unmapped')::int AS unmapped_display,
       count(*) FILTER (WHERE geometry.default_visible AND (
           (geometry.is_frozen_candidate AND geometry.geometry_evidence_kind IN
             ('source_coordinates','provider_derived','verified_coarse_reference')
             -- Maintainer authorization: eligible records with unusable
             -- geometry remain listable as unmapped, never as guessed points.
             -- Still block any invalid geometry actually selected for display.
             AND geometry.display_location IS NOT NULL
             AND geometry.candidate_geometry_valid IS DISTINCT FROM true)
           OR (NOT geometry.is_frozen_candidate AND (
             geometry.geocode_status='failed'
             OR (geometry.geocode_status='accepted' AND (
                   geometry.geocode_result IS NULL
                   OR (ST_X(geometry.geocode_result::geometry)=0 AND ST_Y(geometry.geocode_result::geometry)=0)))
             OR (geometry.geocode_status='unresolved' AND geometry.geocode_result IS NOT NULL)
             OR (geometry.geocode_status='review_required' AND geometry.reference_location IS NOT NULL
                 AND ST_X(geometry.reference_location::geometry)=0
                 AND ST_Y(geometry.reference_location::geometry)=0)
           ))))::int AS coordinate_not_ready,
       count(*) FILTER (WHERE geometry.default_visible AND (
           CASE WHEN geometry.is_frozen_candidate
             THEN cohort.release_id IS NULL
               OR cohort.publication_eligible IS DISTINCT FROM true
               OR cohort.privacy_screening_status IS DISTINCT FROM 'passed'
               OR cohort.maintainer_approval IS DISTINCT FROM 'approved'
             ELSE review.release_id IS NULL
               OR review.publication_eligible IS DISTINCT FROM true
               OR review.privacy_screening_status IS DISTINCT FROM 'passed'
               OR review.maintainer_approval IS DISTINCT FROM 'approved'
           END))::int AS publication_not_approved,
       count(*) FILTER (WHERE geometry.default_visible AND restricted.source_record_id IS NOT NULL)::int AS active_suppression,
       count(*) FILTER (WHERE geometry.default_visible
           AND release.summary->'demonstration' IS NOT NULL
           AND release.summary->'demonstration'->>'rights_status' IS DISTINCT FROM 'cleared')::int AS demonstration_rights_not_cleared,
       (SELECT count(*)::int FROM uec.validation_findings finding
        WHERE finding.severity='error'
          AND (finding.source_record_id IS NULL OR finding.source_record_id IN (
              SELECT visible_observation.source_record_id
              FROM uec.release_members visible_member
              JOIN uec.observations visible_observation ON visible_observation.observation_id=visible_member.observation_id
              WHERE visible_member.release_id=%s AND visible_member.default_visible))) AS validation_errors
FROM eligible_geometry geometry
JOIN uec.releases release ON release.release_id=geometry.release_id
JOIN uec.observations observation ON observation.observation_id=geometry.observation_id
LEFT JOIN uec.publication_review_release_current review
  ON review.source_record_id=geometry.source_record_id AND review.release_id=geometry.release_id
LEFT JOIN uec.release_cohort_review_current cohort
  ON cohort.release_id=geometry.release_id AND cohort.source_id=geometry.source_id
 AND cohort.artifact_id=geometry.artifact_id
LEFT JOIN uec.public_access_restricted restricted ON restricted.source_record_id=geometry.source_record_id
""")
