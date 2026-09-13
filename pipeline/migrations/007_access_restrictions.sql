-- Safety restrictions are append-only control-plane events; evidence is untouched.
CREATE TABLE IF NOT EXISTS uec.record_access_events (
    access_event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_record_id UUID NOT NULL REFERENCES uec.source_records(source_record_id),
    action TEXT NOT NULL CHECK (action IN ('public_access_revoked', 'public_access_restored')),
    reason_category TEXT NOT NULL CHECK (reason_category IN ('privacy', 'safety', 'legal', 'other')),
    policy_version TEXT NOT NULL,
    maintainer TEXT NOT NULL,
    note TEXT,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS record_access_events_current_lookup
    ON uec.record_access_events (source_record_id, occurred_at DESC, access_event_id DESC);

CREATE OR REPLACE VIEW uec.record_access_current AS
SELECT DISTINCT ON (source_record_id) source_record_id, action, reason_category,
       policy_version, maintainer, occurred_at
FROM uec.record_access_events
ORDER BY source_record_id, occurred_at DESC, access_event_id DESC;

CREATE OR REPLACE VIEW uec.public_access_restricted AS
SELECT source_record_id, reason_category, policy_version, occurred_at
FROM uec.record_access_current
WHERE action = 'public_access_revoked';

CREATE OR REPLACE VIEW uec.map_facilities_public AS
SELECT map.* FROM uec.map_facilities_release AS map
WHERE map.release_status = 'promoted'
  AND NOT EXISTS (SELECT 1 FROM uec.public_access_restricted r WHERE r.source_record_id = map.source_record_id);

CREATE OR REPLACE VIEW uec.map_facilities_display_base AS
SELECT release.release_id, release.status AS release_status,
       member.default_visible AS release_visible, observation.observation_id,
       observation.facility_id, observation.source_record_id, facility.canonical_name,
       facility.country_code, facility.street_address, facility.postal_code, facility.city,
       CASE WHEN latest.status = 'accepted' AND latest.result IS NOT NULL THEN latest.result
            WHEN latest.status = 'review_required' THEN city.reference_location ELSE NULL END AS display_location,
       CASE WHEN latest.status = 'accepted' AND latest.result IS NOT NULL THEN 'exact'
            WHEN latest.status = 'review_required' AND city.reference_location IS NOT NULL THEN 'city'
            ELSE 'unmapped' END AS display_precision,
       CASE WHEN latest.status = 'accepted' AND latest.result IS NOT NULL THEN 'Accepted geocoder result'
            WHEN latest.status = 'review_required' AND city.reference_location IS NOT NULL THEN 'Approximate city location — multiple geocoder matches'
            ELSE 'No publishable location' END AS display_label,
       latest.status AS geocoding_status, latest.provider_id AS geocoder_provider,
       latest.queried_at AS geocoded_at
FROM uec.release_members member
JOIN uec.releases release ON release.release_id = member.release_id
JOIN uec.observations observation ON observation.observation_id = member.observation_id
JOIN uec.facilities facility ON facility.facility_id = member.facility_id
LEFT JOIN LATERAL (SELECT status, result, provider_id, queried_at FROM uec.geocode_results
                   WHERE source_record_id = observation.source_record_id
                   ORDER BY queried_at DESC, geocode_result_id DESC LIMIT 1) latest ON true
LEFT JOIN LATERAL (SELECT reference_location FROM uec.city_reference_points
                   WHERE country_code = facility.country_code AND lower(city_name) = lower(facility.city)
                     AND (postal_code IS NULL OR postal_code = facility.postal_code)
                   ORDER BY postal_code NULLS LAST LIMIT 1) city ON true
WHERE member.default_visible = true AND release.status = 'promoted';

CREATE OR REPLACE VIEW uec.map_facilities_display AS
SELECT display.* FROM uec.map_facilities_display_base AS display
WHERE NOT EXISTS (SELECT 1 FROM uec.public_access_restricted r WHERE r.source_record_id = display.source_record_id);
