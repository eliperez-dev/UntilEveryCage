-- Additive support for the public display projection's per-record lookups.
-- These indexes preserve latest-row semantics: the geocoder lookup must still
-- see the newest result even when that result is unresolved or has no point.
CREATE INDEX IF NOT EXISTS geocode_results_discovery_latest_idx
    ON uec.geocode_results (source_record_id, queried_at DESC, geocode_result_id DESC);

CREATE INDEX IF NOT EXISTS city_reference_points_discovery_lookup_idx
    ON uec.city_reference_points (country_code, lower(city_name), postal_code);

COMMENT ON INDEX uec.geocode_results_discovery_latest_idx IS
    'Supports the latest append-only geocode lookup used by the release display projection.';
COMMENT ON INDEX uec.city_reference_points_discovery_lookup_idx IS
    'Supports country/case-insensitive-city/postal lookup used for coarse public display locations.';
