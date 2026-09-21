-- Flatten the public history view's nested release/review/suppression joins.
-- Eligibility is still evaluated from append-only control-plane views for every
-- request; this changes only plan shape, not the public contract.
-- Keep the eligibility CTE inline so release/facility filters can push down
-- before the window aggregates. The partition still covers every eligible
-- observation for a facility, preserving history counts and timestamps.
CREATE OR REPLACE VIEW uec.map_facilities_display_history AS
WITH eligible AS (
    SELECT member.release_id,
           member.default_visible AS release_visible,
           observation.observation_id,
           observation.facility_id,
           observation.source_record_id,
           observation.classification_category,
           observation.first_observed_at,
           observation.observed_at,
           facility.canonical_name,
           facility.country_code,
           facility.street_address,
           facility.postal_code,
           facility.city,
           release.ruleset_version AS release_ruleset_version,
           release.created_at AS release_created_at,
           source.origin_type AS provenance_origin_type,
           source.source_id AS provenance_source_id,
           source.name AS provenance_source_name,
           source.official_url AS provenance_source_url,
           artifact.retrieved_at AS provenance_retrieved_at
    FROM uec.release_members AS member
    JOIN uec.releases AS release
      ON release.release_id = member.release_id
    JOIN uec.observations AS observation
      ON observation.observation_id = member.observation_id
    JOIN uec.facilities AS facility
      ON facility.facility_id = member.facility_id
    JOIN uec.source_records AS record
      ON record.source_record_id = observation.source_record_id
    JOIN uec.sources AS source
      ON source.source_id = record.source_id
    JOIN uec.raw_artifacts AS artifact
      ON artifact.artifact_id = record.artifact_id
    JOIN uec.publication_review_release_current AS review
      ON review.source_record_id = observation.source_record_id
     AND review.release_id = member.release_id
    WHERE release.status = 'promoted'
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
          FROM uec.public_access_restricted AS restricted
          WHERE restricted.source_record_id = observation.source_record_id
      )
)
SELECT eligible.release_id,
       'promoted'::text AS release_status,
       eligible.release_visible,
       eligible.observation_id,
       eligible.facility_id,
       eligible.source_record_id,
       eligible.canonical_name,
       eligible.country_code,
       eligible.street_address,
       eligible.postal_code,
       eligible.city,
       CASE WHEN latest.status = 'accepted' AND latest.result IS NOT NULL THEN latest.result
            WHEN latest.status = 'review_required' THEN city.reference_location ELSE NULL END AS display_location,
       CASE WHEN latest.status = 'accepted' AND latest.result IS NOT NULL THEN 'exact'
            WHEN latest.status = 'review_required' AND city.reference_location IS NOT NULL THEN 'city'
            ELSE 'unmapped' END AS display_precision,
       CASE WHEN latest.status = 'accepted' AND latest.result IS NOT NULL THEN 'Accepted geocoder result'
            WHEN latest.status = 'review_required' AND city.reference_location IS NOT NULL THEN 'Approximate city location — multiple geocoder matches'
            ELSE 'No publishable location' END AS display_label,
       latest.status AS geocoding_status,
       latest.provider_id AS geocoder_provider,
       latest.queried_at AS geocoded_at,
       eligible.classification_category,
       min(eligible.first_observed_at) OVER facility_history AS first_observed_at,
       max(eligible.observed_at) OVER facility_history AS last_observed_at,
       (count(*) OVER facility_history)::int AS observation_count,
       COALESCE(lifecycle.status, 'status_unknown') AS lifecycle_status,
       lifecycle.effective_at AS lifecycle_effective_at,
       lifecycle.source_record_id AS lifecycle_source_record_id,
       eligible.release_ruleset_version,
       eligible.release_created_at,
       eligible.provenance_origin_type,
       eligible.provenance_source_id,
       eligible.provenance_source_name,
       eligible.provenance_source_url,
       eligible.provenance_retrieved_at
FROM eligible
LEFT JOIN LATERAL (
    SELECT status, result, provider_id, queried_at
    FROM uec.geocode_results
    WHERE source_record_id = eligible.source_record_id
    ORDER BY queried_at DESC, geocode_result_id DESC
    LIMIT 1
) AS latest ON true
LEFT JOIN LATERAL (
    SELECT reference_location
    FROM uec.city_reference_points
    WHERE country_code = eligible.country_code
      AND lower(city_name) = lower(eligible.city)
      AND (postal_code IS NULL OR postal_code = eligible.postal_code)
    ORDER BY postal_code NULLS LAST
    LIMIT 1
) AS city ON true
LEFT JOIN uec.facility_lifecycle_current AS lifecycle
  ON lifecycle.facility_id = eligible.facility_id
WINDOW facility_history AS (PARTITION BY eligible.release_id, eligible.facility_id);

COMMENT ON VIEW uec.map_facilities_display_history IS
    'V2 public display history with one release-scoped eligibility pass, current suppression, and public-only lifecycle counts.';
