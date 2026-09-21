-- Planner support for the live public read path. These indexes are additive:
-- eligibility, profile, and suppression continue to be evaluated by the view.
CREATE INDEX IF NOT EXISTS releases_public_promoted_lookup_idx
    ON uec.releases (profile, created_at DESC, release_id DESC)
    WHERE status = 'promoted' AND test_only IS NOT TRUE;

CREATE INDEX IF NOT EXISTS release_members_public_facility_order_idx
    ON uec.release_members (release_id, facility_id, observation_id)
    WHERE default_visible = true;

CREATE INDEX IF NOT EXISTS facilities_discovery_search_fields_trgm_idx
    ON uec.facilities USING GIN (
        lower(coalesce(canonical_name, '') || ' ' || coalesce(city, '') || ' ' || country_code)
        gin_trgm_ops
    );

COMMENT ON INDEX uec.releases_public_promoted_lookup_idx IS
    'Bounds promoted-release selection without changing release eligibility.';
COMMENT ON INDEX uec.release_members_public_facility_order_idx IS
    'Supports deterministic facility cursor traversal for visible release members.';
COMMENT ON INDEX uec.facilities_discovery_search_fields_trgm_idx IS
    'Supports bounded case-insensitive search over public facility identity fields.';
