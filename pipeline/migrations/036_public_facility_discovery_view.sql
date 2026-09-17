-- Release-bound public discovery read model.
--
-- Component rows are immutable membership facts built from a verified release
-- manifest. This view re-evaluates publication, profile, privacy, and
-- suppression gates on every read; it is an acceleration structure, never a
-- cached publication decision. Missing metadata or a stale manifest produces
-- no rows. The API separately fails closed when the selected release is not
-- ready.
CREATE OR REPLACE VIEW uec.map_facilities_public_discovery AS
WITH eligible AS (
    SELECT component.release_id,
           true AS release_visible,
           component.observation_id,
           component.facility_id,
           component.source_record_id,
           component.classification_category,
           component.first_observed_at,
           component.observed_at,
           facility.canonical_name,
           facility.country_code,
           facility.postal_code,
           facility.city,
           release.ruleset_version AS release_ruleset_version,
           release.created_at AS release_created_at,
           source.origin_type AS provenance_origin_type,
           source.source_id AS provenance_source_id,
           source.name AS provenance_source_name,
           source.official_url AS provenance_source_url,
           artifact.retrieved_at AS provenance_retrieved_at,
           review.factual_review_status,
           review.privacy_screening_status,
           review.maintainer_approval,
           review.reviewer_role
    FROM uec.release_summary_component_rows AS component
    JOIN uec.release_summary_components AS component_meta
      ON component_meta.release_id = component.release_id
    JOIN uec.releases AS release
      ON release.release_id = component.release_id
    JOIN uec.release_manifests AS manifest
      ON manifest.release_id = component.release_id
     AND manifest.manifest_sha256 = component_meta.manifest_sha256
    JOIN uec.facilities AS facility
      ON facility.facility_id = component.facility_id
    JOIN uec.source_records AS record
      ON record.source_record_id = component.source_record_id
    JOIN uec.sources AS source
      ON source.source_id = record.source_id
    JOIN uec.raw_artifacts AS artifact
      ON artifact.artifact_id = record.artifact_id
    JOIN uec.publication_review_release_current AS review
      ON review.source_record_id = component.source_record_id
     AND review.release_id = component.release_id
    WHERE release.status = 'promoted'
      AND release.test_only IS NOT TRUE
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
          WHERE restricted.source_record_id = component.source_record_id
      )
), summary AS (
    SELECT release_id,
           facility_id,
           min(first_observed_at) AS first_observed_at,
           max(observed_at) AS last_observed_at,
           count(*)::int AS observation_count
    FROM eligible
    GROUP BY release_id, facility_id
), latest AS (
    SELECT DISTINCT ON (release_id, facility_id) eligible.*
    FROM eligible
    ORDER BY release_id, facility_id, observation_id
)
SELECT latest.release_id,
       'promoted'::text AS release_status,
       latest.release_visible,
       latest.observation_id,
       latest.facility_id,
       latest.source_record_id,
       latest.canonical_name,
       latest.country_code,
       latest.city,
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
       latest.classification_category,
       summary.first_observed_at,
       summary.last_observed_at,
       summary.observation_count,
       coalesce(lifecycle.status, 'status_unknown') AS lifecycle_status,
       lifecycle.effective_at AS lifecycle_effective_at,
       lifecycle.source_record_id AS lifecycle_source_record_id,
       latest.release_ruleset_version,
       latest.release_created_at,
       latest.provenance_origin_type,
       latest.provenance_source_id,
       latest.provenance_source_name,
       latest.provenance_source_url,
       latest.provenance_retrieved_at,
       latest.factual_review_status,
       latest.privacy_screening_status,
       latest.maintainer_approval,
       latest.reviewer_role
FROM latest
JOIN summary
  ON summary.release_id = latest.release_id
 AND summary.facility_id = latest.facility_id
LEFT JOIN LATERAL (
    SELECT status, result, provider_id, queried_at
    FROM uec.geocode_results
    WHERE source_record_id = latest.source_record_id
    ORDER BY queried_at DESC, geocode_result_id DESC
    LIMIT 1
) AS geocode ON true
LEFT JOIN LATERAL (
    SELECT reference_location
    FROM uec.city_reference_points
    WHERE country_code = latest.country_code
      AND lower(city_name) = lower(latest.city)
      AND (postal_code IS NULL OR postal_code = latest.postal_code)
    ORDER BY postal_code NULLS LAST
    LIMIT 1
) AS city ON true
LEFT JOIN uec.facility_lifecycle_current AS lifecycle
  ON lifecycle.facility_id = latest.facility_id;

COMMENT ON VIEW uec.map_facilities_public_discovery IS
    'Manifest-bound public discovery view using immutable release membership and live publication, privacy, profile, and suppression gates.';
