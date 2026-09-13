-- Derive map output from immutable evidence; do not copy coordinates into source rows.

CREATE OR REPLACE VIEW uec.map_facilities_current AS
SELECT
    observation.observation_id,
    observation.facility_id,
    observation.source_record_id,
    observation.classification_category,
    observation.default_visible,
    observation.optional_filter,
    facility.canonical_name,
    facility.country_code,
    facility.street_address,
    facility.postal_code,
    facility.city,
    geocode.result AS geocoded_location,
    geocode.provider_id AS geocoder_provider,
    geocode.precision AS geocoder_precision,
    geocode.queried_at AS geocoded_at
FROM uec.observations AS observation
JOIN uec.facilities AS facility ON facility.facility_id = observation.facility_id
JOIN LATERAL (
    SELECT result, provider_id, precision, queried_at
    FROM uec.geocode_results
    WHERE source_record_id = observation.source_record_id
      AND status = 'accepted'
      AND result IS NOT NULL
    ORDER BY queried_at DESC, geocode_result_id DESC
    LIMIT 1
) AS geocode ON true
WHERE observation.default_visible = true;

COMMENT ON VIEW uec.map_facilities_current IS
    'Read-only default map projection. Coordinates come only from accepted geocode evidence; source rows are never mutated.';

CREATE OR REPLACE VIEW uec.map_facilities_release AS
SELECT
    release.release_id,
    release.status AS release_status,
    release_member.default_visible AS release_visible,
    map.*
FROM uec.release_members AS release_member
JOIN uec.releases AS release ON release.release_id = release_member.release_id
JOIN uec.map_facilities_current AS map
  ON map.facility_id = release_member.facility_id
 AND map.observation_id = release_member.observation_id
WHERE release_member.default_visible = true;

COMMENT ON VIEW uec.map_facilities_release IS
    'Read-only release-aware map projection. Callers must explicitly select an eligible release status.';
