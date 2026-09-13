-- Coarse display geometry is presentation data, never a replacement for evidence.

CREATE TABLE IF NOT EXISTS uec.city_reference_points (
    city_reference_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    country_code CHAR(2) NOT NULL,
    city_name TEXT NOT NULL,
    postal_code TEXT,
    reference_location GEOGRAPHY(Point, 4326) NOT NULL,
    reference_source TEXT NOT NULL,
    source_retrieved_at TIMESTAMPTZ NOT NULL,
    UNIQUE (country_code, city_name, postal_code, reference_source)
);

CREATE OR REPLACE VIEW uec.map_facilities_display AS
SELECT
    release.release_id,
    release.status AS release_status,
    member.default_visible AS release_visible,
    observation.observation_id,
    observation.facility_id,
    observation.source_record_id,
    facility.canonical_name,
    facility.country_code,
    facility.street_address,
    facility.postal_code,
    facility.city,
    CASE
        WHEN latest_geocode.status = 'accepted' AND latest_geocode.result IS NOT NULL THEN latest_geocode.result
        WHEN latest_geocode.status = 'review_required' THEN city.reference_location
        ELSE NULL
    END AS display_location,
    CASE
        WHEN latest_geocode.status = 'accepted' AND latest_geocode.result IS NOT NULL THEN 'exact'
        WHEN latest_geocode.status = 'review_required' AND city.reference_location IS NOT NULL THEN 'city'
        ELSE 'unmapped'
    END AS display_precision,
    CASE
        WHEN latest_geocode.status = 'accepted' AND latest_geocode.result IS NOT NULL THEN 'Accepted geocoder result'
        WHEN latest_geocode.status = 'review_required' AND city.reference_location IS NOT NULL THEN 'Approximate city location — multiple geocoder matches'
        ELSE 'No publishable location'
    END AS display_label,
    latest_geocode.status AS geocoding_status,
    latest_geocode.provider_id AS geocoder_provider,
    latest_geocode.queried_at AS geocoded_at
FROM uec.release_members AS member
JOIN uec.releases AS release ON release.release_id = member.release_id
JOIN uec.observations AS observation ON observation.observation_id = member.observation_id
JOIN uec.facilities AS facility ON facility.facility_id = member.facility_id
LEFT JOIN LATERAL (
    SELECT status, result, provider_id, queried_at
    FROM uec.geocode_results
    WHERE source_record_id = observation.source_record_id
    ORDER BY queried_at DESC, geocode_result_id DESC
    LIMIT 1
) AS latest_geocode ON true
LEFT JOIN LATERAL (
    SELECT reference_location
    FROM uec.city_reference_points
    WHERE country_code = facility.country_code
      AND lower(city_name) = lower(facility.city)
      AND (postal_code IS NULL OR postal_code = facility.postal_code)
    ORDER BY postal_code NULLS LAST
    LIMIT 1
) AS city ON true
WHERE member.default_visible = true
  AND release.status = 'promoted';

COMMENT ON VIEW uec.map_facilities_display IS
    'Public display projection. Exact geocodes remain evidence; review-required matches use a separately sourced city reference point.';
