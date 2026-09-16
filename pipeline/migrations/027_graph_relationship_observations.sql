-- Dated relationship observations. A later observation is a projection input;
-- it does not rewrite or erase an earlier observation.

CREATE TABLE uec.organization_relationship_observations (
    relationship_observation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id TEXT NOT NULL REFERENCES uec.sources(source_id),
    source_record_id UUID NOT NULL REFERENCES uec.source_records(source_record_id),
    from_organization_id UUID REFERENCES uec.organizations(organization_id),
    target_facility_id UUID REFERENCES uec.facilities(facility_id),
    target_organization_id UUID REFERENCES uec.organizations(organization_id),
    relationship_type TEXT CHECK (relationship_type IN ('operator', 'owner', 'parent', 'brand', 'supplier', 'customer')),
    assertion_status TEXT NOT NULL DEFAULT 'asserted'
        CHECK (assertion_status IN ('asserted', 'unknown', 'disputed', 'rejected')),
    unknown_reason TEXT,
    valid_from DATE,
    valid_to DATE,
    observed_at TIMESTAMPTZ NOT NULL,
    confidence NUMERIC(5,4) CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1),
    review_state TEXT NOT NULL DEFAULT 'review_required'
        CHECK (review_state IN ('unreviewed', 'review_required', 'reviewed', 'accepted', 'rejected')),
    storage_state TEXT NOT NULL DEFAULT 'private'
        CHECK (storage_state IN ('raw', 'private', 'reviewed', 'released')),
    privacy_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (privacy_status IN ('pending', 'passed', 'failed', 'suppressed')),
    publication_status TEXT NOT NULL DEFAULT 'not_eligible'
        CHECK (publication_status IN ('not_eligible', 'eligible', 'released', 'suppressed')),
    release_id TEXT REFERENCES uec.releases(release_id),
    note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from),
    CHECK ((assertion_status = 'unknown'
            AND relationship_type IS NULL
            AND from_organization_id IS NULL
            AND unknown_reason IS NOT NULL AND btrim(unknown_reason) <> '')
        OR (assertion_status <> 'unknown'
            AND relationship_type IS NOT NULL
            AND from_organization_id IS NOT NULL
            AND unknown_reason IS NULL)),
    CHECK ((target_facility_id IS NOT NULL) <> (target_organization_id IS NOT NULL)),
    CHECK (publication_status <> 'released' OR (release_id IS NOT NULL AND storage_state = 'released'
        AND review_state = 'accepted' AND privacy_status = 'passed')),
    CHECK (storage_state <> 'released' OR publication_status = 'released')
);

CREATE INDEX organization_relationship_observations_current_idx
    ON uec.organization_relationship_observations
       (from_organization_id, target_facility_id, target_organization_id, relationship_type,
        observed_at DESC, relationship_observation_id DESC);
CREATE INDEX organization_relationship_observations_source_idx
    ON uec.organization_relationship_observations (source_id, source_record_id);

CREATE OR REPLACE VIEW uec.organization_relationship_current AS
SELECT DISTINCT ON (from_organization_id, target_facility_id, target_organization_id, relationship_type)
    relationship_observation_id,
    source_id,
    source_record_id,
    from_organization_id,
    target_facility_id,
    target_organization_id,
    relationship_type,
    assertion_status,
    unknown_reason,
    valid_from,
    valid_to,
    observed_at,
    confidence,
    review_state,
    storage_state,
    privacy_status,
    publication_status,
    release_id,
    note,
    created_at
FROM uec.organization_relationship_observations
ORDER BY from_organization_id, target_facility_id, target_organization_id, relationship_type,
         observed_at DESC, relationship_observation_id DESC;

CREATE TRIGGER organization_relationship_observations_source_match
    BEFORE INSERT ON uec.organization_relationship_observations
    FOR EACH ROW EXECUTE FUNCTION uec.assert_graph_source_matches_record();

CREATE TRIGGER organization_relationship_observations_append_only
    BEFORE UPDATE OR DELETE ON uec.organization_relationship_observations
    FOR EACH ROW EXECUTE FUNCTION uec.reject_evidence_mutation();

COMMENT ON TABLE uec.organization_relationship_observations IS
    'Append-only dated assertions, disputes, rejections, and explicit unknowns. Supplier/customer rows require evidence like every other type.';
COMMENT ON VIEW uec.organization_relationship_current IS
    'Latest observation for each scoped endpoint/type. Different target organizations remain visible so contradictory ownership/operator observations coexist.';
