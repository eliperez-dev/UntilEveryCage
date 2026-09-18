-- Private graph reads are bounded and deterministic. These indexes support
-- entity lookup, dated relationship filters, and review/quarantine queues.
CREATE INDEX IF NOT EXISTS organizations_name_lookup_idx
    ON uec.organizations (lower(canonical_name), organization_id);
CREATE INDEX IF NOT EXISTS facilities_name_lookup_idx
    ON uec.facilities (lower(canonical_name), facility_id);
CREATE INDEX IF NOT EXISTS graph_relationship_private_query_idx
    ON uec.organization_relationship_observations
       (from_organization_id, observed_at DESC, relationship_observation_id DESC);
CREATE INDEX IF NOT EXISTS graph_crosswalk_queue_idx
    ON uec.source_entity_crosswalks (assertion_status, observed_at DESC, crosswalk_id DESC);
CREATE INDEX IF NOT EXISTS graph_claim_review_queue_idx
    ON uec.claims (review_state, observed_at DESC, claim_id DESC);
