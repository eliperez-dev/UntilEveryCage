-- Evidence-backed claims are deliberately typed but value-extensible. The
-- listed domains reserve attachment points for future work; no domain-specific
-- implementation is implied by this foundation.

CREATE TABLE uec.claims (
    claim_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id TEXT NOT NULL REFERENCES uec.sources(source_id),
    source_record_id UUID NOT NULL REFERENCES uec.source_records(source_record_id),
    facility_id UUID REFERENCES uec.facilities(facility_id),
    organization_id UUID REFERENCES uec.organizations(organization_id),
    claim_domain TEXT NOT NULL CHECK (claim_domain IN (
        'identity', 'location', 'operation', 'ownership', 'inspection',
        'violation', 'commitment', 'investigation', 'public_funding', 'animal_count', 'other'
    )),
    claim_kind TEXT NOT NULL,
    value_state TEXT NOT NULL DEFAULT 'known'
        CHECK (value_state IN ('known', 'unknown', 'not_applicable', 'withheld')),
    claim_value JSONB NOT NULL DEFAULT '{}'::jsonb,
    unknown_reason TEXT,
    valid_from DATE,
    valid_to DATE,
    observed_at TIMESTAMPTZ NOT NULL,
    confidence NUMERIC(5,4) CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1),
    review_state TEXT NOT NULL DEFAULT 'review_required'
        CHECK (review_state IN ('unreviewed', 'review_required', 'reviewed', 'accepted', 'disputed', 'rejected')),
    storage_state TEXT NOT NULL DEFAULT 'private'
        CHECK (storage_state IN ('raw', 'private', 'reviewed', 'released')),
    privacy_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (privacy_status IN ('pending', 'passed', 'failed', 'suppressed')),
    publication_status TEXT NOT NULL DEFAULT 'not_eligible'
        CHECK (publication_status IN ('not_eligible', 'eligible', 'released', 'suppressed')),
    release_id TEXT REFERENCES uec.releases(release_id),
    note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK ((facility_id IS NOT NULL) <> (organization_id IS NOT NULL)),
    CHECK (valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from),
    CHECK ((value_state = 'unknown' AND unknown_reason IS NOT NULL AND btrim(unknown_reason) <> '')
        OR (value_state <> 'unknown' AND unknown_reason IS NULL)),
    CHECK (publication_status <> 'released' OR (release_id IS NOT NULL AND storage_state = 'released'
        AND review_state = 'accepted' AND privacy_status = 'passed')),
    CHECK (storage_state <> 'released' OR publication_status = 'released')
);

CREATE INDEX claims_subject_kind_idx
    ON uec.claims (facility_id, organization_id, claim_domain, claim_kind, observed_at DESC);
CREATE INDEX claims_source_idx ON uec.claims (source_id, source_record_id);

CREATE TABLE uec.claim_support (
    claim_support_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    claim_id UUID NOT NULL REFERENCES uec.claims(claim_id),
    source_record_id UUID REFERENCES uec.source_records(source_record_id),
    artifact_id UUID REFERENCES uec.raw_artifacts(artifact_id),
    support_role TEXT NOT NULL CHECK (support_role IN ('primary', 'corroborating', 'contradicting', 'context')),
    observed_at TIMESTAMPTZ NOT NULL,
    storage_state TEXT NOT NULL DEFAULT 'private'
        CHECK (storage_state IN ('raw', 'private', 'reviewed', 'released')),
    note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (source_record_id IS NOT NULL OR artifact_id IS NOT NULL)
);

CREATE INDEX claim_support_claim_idx ON uec.claim_support (claim_id, observed_at DESC);
CREATE INDEX claim_support_record_idx ON uec.claim_support (source_record_id);

CREATE OR REPLACE VIEW uec.claim_current AS
SELECT DISTINCT ON (facility_id, organization_id, claim_domain, claim_kind, value_state, claim_value)
    claim_id,
    source_id,
    source_record_id,
    facility_id,
    organization_id,
    claim_domain,
    claim_kind,
    value_state,
    claim_value,
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
FROM uec.claims
ORDER BY facility_id, organization_id, claim_domain, claim_kind, value_state, claim_value,
         observed_at DESC, claim_id DESC;

CREATE TRIGGER claims_source_match
    BEFORE INSERT ON uec.claims
    FOR EACH ROW EXECUTE FUNCTION uec.assert_graph_source_matches_record();

CREATE TRIGGER claims_append_only
    BEFORE UPDATE OR DELETE ON uec.claims
    FOR EACH ROW EXECUTE FUNCTION uec.reject_evidence_mutation();

CREATE TRIGGER claim_support_append_only
    BEFORE UPDATE OR DELETE ON uec.claim_support
    FOR EACH ROW EXECUTE FUNCTION uec.reject_evidence_mutation();

COMMENT ON TABLE uec.claims IS
    'Append-only claims whose values may conflict. claim_domain includes reserved inspection, violation, commitment, investigation, public-funding, and animal-count attachment points.';
COMMENT ON TABLE uec.claim_support IS
    'Append-only links to retained artifacts or source records; support_role makes corroboration and contradiction explicit.';
