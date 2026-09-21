-- Accountability Graph foundation: distinct organizations, source-native
-- identifiers, and source-scoped crosswalks. Nothing here asserts that two
-- source identifiers are universally the same entity.

CREATE TABLE uec.organizations (
    organization_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    canonical_name TEXT,
    country_code CHAR(2),
    organization_type TEXT NOT NULL DEFAULT 'unknown'
        CHECK (organization_type IN ('company', 'government', 'nonprofit', 'cooperative', 'unknown', 'other')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE uec.organizations IS
    'Canonical organization projection; evidence about names, ownership, and relationships lives in append-only graph rows.';

CREATE TABLE uec.source_entity_identifiers (
    identifier_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id TEXT NOT NULL REFERENCES uec.sources(source_id),
    source_record_id UUID NOT NULL REFERENCES uec.source_records(source_record_id),
    entity_type TEXT NOT NULL CHECK (entity_type IN ('facility', 'organization')),
    facility_id UUID REFERENCES uec.facilities(facility_id),
    organization_id UUID REFERENCES uec.organizations(organization_id),
    identifier_type TEXT NOT NULL,
    source_identifier TEXT NOT NULL,
    value_as_observed TEXT,
    observed_at TIMESTAMPTZ NOT NULL,
    review_state TEXT NOT NULL DEFAULT 'unreviewed'
        CHECK (review_state IN ('unreviewed', 'review_required', 'reviewed', 'accepted', 'rejected')),
    storage_state TEXT NOT NULL DEFAULT 'private'
        CHECK (storage_state IN ('raw', 'private', 'reviewed', 'released')),
    privacy_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (privacy_status IN ('pending', 'passed', 'failed', 'suppressed')),
    publication_status TEXT NOT NULL DEFAULT 'not_eligible'
        CHECK (publication_status IN ('not_eligible', 'eligible', 'released', 'suppressed')),
    release_id TEXT REFERENCES uec.releases(release_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK ((entity_type = 'facility' AND facility_id IS NOT NULL AND organization_id IS NULL)
        OR (entity_type = 'organization' AND organization_id IS NOT NULL AND facility_id IS NULL)),
    CHECK (publication_status <> 'released' OR (release_id IS NOT NULL AND storage_state = 'released'
        AND review_state = 'accepted' AND privacy_status = 'passed')),
    CHECK (storage_state <> 'released' OR publication_status = 'released')
);

CREATE INDEX source_entity_identifiers_lookup_idx
    ON uec.source_entity_identifiers (source_id, identifier_type, source_identifier);
CREATE INDEX source_entity_identifiers_entity_idx
    ON uec.source_entity_identifiers (entity_type, facility_id, organization_id, observed_at DESC);

CREATE TABLE uec.source_entity_crosswalks (
    crosswalk_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    left_identifier_id UUID NOT NULL REFERENCES uec.source_entity_identifiers(identifier_id),
    right_identifier_id UUID NOT NULL REFERENCES uec.source_entity_identifiers(identifier_id),
    source_id TEXT NOT NULL REFERENCES uec.sources(source_id),
    source_record_id UUID NOT NULL REFERENCES uec.source_records(source_record_id),
    assertion_status TEXT NOT NULL DEFAULT 'review_required'
        CHECK (assertion_status IN ('candidate', 'accepted', 'rejected', 'review_required', 'disputed')),
    identity_scope TEXT NOT NULL DEFAULT 'source_scoped'
        CHECK (identity_scope = 'source_scoped'),
    match_method TEXT NOT NULL,
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
    observed_at TIMESTAMPTZ NOT NULL,
    note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (left_identifier_id <> right_identifier_id),
    CHECK (publication_status <> 'released' OR (release_id IS NOT NULL AND storage_state = 'released'
        AND review_state = 'accepted' AND privacy_status = 'passed')),
    CHECK (storage_state <> 'released' OR publication_status = 'released')
);

CREATE INDEX source_entity_crosswalks_pair_idx
    ON uec.source_entity_crosswalks (left_identifier_id, right_identifier_id, observed_at DESC);
CREATE INDEX source_entity_crosswalks_evidence_idx
    ON uec.source_entity_crosswalks (source_id, source_record_id);

CREATE OR REPLACE FUNCTION uec.assert_graph_source_matches_record()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM uec.source_records
        WHERE source_record_id = NEW.source_record_id
          AND source_id = NEW.source_id
    ) THEN
        RAISE EXCEPTION 'graph source_id must match source_record_id %', NEW.source_record_id;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER source_entity_identifiers_source_match
    BEFORE INSERT ON uec.source_entity_identifiers
    FOR EACH ROW EXECUTE FUNCTION uec.assert_graph_source_matches_record();

CREATE TRIGGER source_entity_crosswalks_source_match
    BEFORE INSERT ON uec.source_entity_crosswalks
    FOR EACH ROW EXECUTE FUNCTION uec.assert_graph_source_matches_record();

CREATE TRIGGER source_entity_identifiers_append_only
    BEFORE UPDATE OR DELETE ON uec.source_entity_identifiers
    FOR EACH ROW EXECUTE FUNCTION uec.reject_evidence_mutation();

CREATE TRIGGER source_entity_crosswalks_append_only
    BEFORE UPDATE OR DELETE ON uec.source_entity_crosswalks
    FOR EACH ROW EXECUTE FUNCTION uec.reject_evidence_mutation();

COMMENT ON TABLE uec.source_entity_identifiers IS
    'Source-native identifiers remain qualified by source and record; identifiers are not global IDs.';
COMMENT ON TABLE uec.source_entity_crosswalks IS
    'Append-only, source-scoped candidate/decision links. Rejected or disputed mappings remain evidence.';
