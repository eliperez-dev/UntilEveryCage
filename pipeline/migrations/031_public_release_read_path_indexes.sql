-- Additive indexes for the release-scoped public read path. These support
-- existing joins only; they do not alter eligibility, ordering, or suppression.
CREATE INDEX IF NOT EXISTS release_members_public_discovery_idx
    ON uec.release_members (release_id, default_visible, observation_id, facility_id);

CREATE INDEX IF NOT EXISTS publication_review_scopes_release_event_idx
    ON uec.publication_review_release_scopes (release_id, publication_review_event_id);

COMMENT ON INDEX uec.release_members_public_discovery_idx IS
    'Supports release-scoped public discovery membership checks without changing visibility semantics.';
COMMENT ON INDEX uec.publication_review_scopes_release_event_idx IS
    'Supports release-scoped publication review joins without changing the current-decision ordering.';
