-- Discovery read-path indexes. These are additive and safe to rerun through the
-- migration ledger. The public projection remains a view so suppression and
-- release-scoped eligibility are evaluated for every request.
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX IF NOT EXISTS release_members_discovery_observation_idx
    ON uec.release_members (release_id, observation_id, facility_id);

CREATE INDEX IF NOT EXISTS facilities_discovery_country_city_idx
    ON uec.facilities (country_code, city, facility_id);

CREATE INDEX IF NOT EXISTS facilities_discovery_name_trgm_idx
    ON uec.facilities USING GIN (lower(canonical_name) gin_trgm_ops);

CREATE INDEX IF NOT EXISTS observations_discovery_category_idx
    ON uec.observations (classification_category, facility_id, observation_id);

COMMENT ON INDEX uec.release_members_discovery_observation_idx IS
    'Supports release-scoped projection joins while the primary key supplies UUID cursor order.';
COMMENT ON INDEX uec.facilities_discovery_name_trgm_idx IS
    'Supports bounded case-insensitive substring search on canonical facility names.';
