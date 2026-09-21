-- Additive indexes for the live public eligibility path.
-- These indexes do not change review ordering, suppression semantics, or the
-- flattened live projection. Migration 033 remains a non-public prototype.

CREATE INDEX IF NOT EXISTS publication_review_events_record_current_idx
    ON uec.publication_review_events
       (source_record_id, reviewed_at DESC, publication_review_event_id DESC);

CREATE INDEX IF NOT EXISTS publication_review_release_scopes_event_release_idx
    ON uec.publication_review_release_scopes
       (publication_review_event_id, release_id);

CREATE INDEX IF NOT EXISTS record_access_events_record_current_idx
    ON uec.record_access_events
       (source_record_id, occurred_at DESC, access_event_id DESC);

CREATE INDEX IF NOT EXISTS observations_source_record_lookup_idx
    ON uec.observations (source_record_id, observation_id, facility_id);

COMMENT ON INDEX uec.publication_review_events_record_current_idx IS
    'Supports append-only latest review lookup while preserving reviewed_at and event-id ordering.';
COMMENT ON INDEX uec.publication_review_release_scopes_event_release_idx IS
    'Supports release-scoped review event expansion without changing eligibility semantics.';
COMMENT ON INDEX uec.record_access_events_record_current_idx IS
    'Supports current access restriction lookup by source record without exposing restricted payloads.';
COMMENT ON INDEX uec.observations_source_record_lookup_idx IS
    'Supports release eligibility and suppression crosswalk joins by source record.';
