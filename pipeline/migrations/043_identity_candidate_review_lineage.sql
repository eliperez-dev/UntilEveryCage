-- D4 identity candidates: uncertain connections are retained as private,
-- reviewable evidence and never become canonical identities automatically.
CREATE TABLE uec.identity_candidate_edges (
    candidate_edge_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id TEXT NOT NULL REFERENCES uec.sources(source_id),
    source_record_id UUID NOT NULL REFERENCES uec.source_records(source_record_id),
    left_identifier_id UUID NOT NULL REFERENCES uec.source_entity_identifiers(identifier_id),
    right_identifier_id UUID NOT NULL REFERENCES uec.source_entity_identifiers(identifier_id),
    match_method TEXT NOT NULL,
    confidence_score NUMERIC(6,5) NOT NULL CHECK (confidence_score BETWEEN 0 AND 1),
    confidence_band TEXT NOT NULL CHECK (confidence_band IN ('exact', 'high', 'probable', 'possible', 'low')),
    contributing_features JSONB NOT NULL DEFAULT '{}'::jsonb,
    contradictory_evidence JSONB NOT NULL DEFAULT '[]'::jsonb,
    provenance JSONB NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    algorithm_version TEXT NOT NULL,
    disclaimer TEXT NOT NULL,
    review_state TEXT NOT NULL DEFAULT 'review_required'
        CHECK (review_state IN ('unreviewed', 'review_required', 'accepted', 'rejected', 'deferred', 'conflicted', 'superseded', 'reversed')),
    storage_state TEXT NOT NULL DEFAULT 'private' CHECK (storage_state IN ('private', 'reviewed')),
    privacy_status TEXT NOT NULL DEFAULT 'pending' CHECK (privacy_status IN ('pending', 'passed', 'failed', 'suppressed')),
    publication_status TEXT NOT NULL DEFAULT 'not_eligible' CHECK (publication_status = 'not_eligible'),
    automatic_merge BOOLEAN NOT NULL DEFAULT false CHECK (automatic_merge = false),
    transfers_claims BOOLEAN NOT NULL DEFAULT false CHECK (transfers_claims = false),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (left_identifier_id <> right_identifier_id),
    CHECK (jsonb_typeof(contributing_features) = 'object'),
    CHECK (jsonb_typeof(contradictory_evidence) = 'array'),
    CHECK (jsonb_typeof(provenance) = 'object')
);

CREATE INDEX identity_candidate_edges_review_idx
    ON uec.identity_candidate_edges (review_state, confidence_band, observed_at DESC);
CREATE INDEX identity_candidate_edges_pair_idx
    ON uec.identity_candidate_edges (left_identifier_id, right_identifier_id, observed_at DESC);

CREATE OR REPLACE FUNCTION uec.validate_identity_candidate_edge()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    left_source TEXT;
    right_source TEXT;
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM uec.source_records
        WHERE source_record_id = NEW.source_record_id AND source_id = NEW.source_id
    ) THEN
        RAISE EXCEPTION 'identity candidate source_id must match source_record_id %', NEW.source_record_id;
    END IF;
    SELECT source_id INTO left_source FROM uec.source_entity_identifiers WHERE identifier_id = NEW.left_identifier_id;
    SELECT source_id INTO right_source FROM uec.source_entity_identifiers WHERE identifier_id = NEW.right_identifier_id;
    IF left_source IS NULL OR right_source IS NULL THEN
        RAISE EXCEPTION 'identity candidate endpoints must reference source identifiers';
    END IF;
    IF left_source = 'us.aphis' AND right_source = 'us.fsis'
       OR left_source = 'us.fsis' AND right_source = 'us.aphis' THEN
        IF NEW.review_state <> 'review_required' THEN
            RAISE EXCEPTION 'APHIS/FSIS candidates remain review-required until explicit human adjudication';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER identity_candidate_edges_scope_guard
    BEFORE INSERT ON uec.identity_candidate_edges
    FOR EACH ROW EXECUTE FUNCTION uec.validate_identity_candidate_edge();

CREATE TABLE uec.identity_review_events (
    identity_review_event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_edge_id UUID NOT NULL REFERENCES uec.identity_candidate_edges(candidate_edge_id),
    action TEXT NOT NULL CHECK (action IN ('accept', 'reject', 'defer', 'conflict', 'supersede', 'reverse')),
    reason TEXT NOT NULL CHECK (btrim(reason) <> ''),
    reviewer_role TEXT NOT NULL CHECK (btrim(reviewer_role) <> ''),
    previous_event_id UUID REFERENCES uec.identity_review_events(identity_review_event_id),
    decided_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    publication_status TEXT NOT NULL DEFAULT 'not_eligible' CHECK (publication_status = 'not_eligible')
);
CREATE INDEX identity_review_events_candidate_idx
    ON uec.identity_review_events (candidate_edge_id, decided_at DESC, identity_review_event_id DESC);

CREATE TABLE uec.identity_lineage_events (
    identity_lineage_event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_edge_id UUID NOT NULL REFERENCES uec.identity_candidate_edges(candidate_edge_id),
    event_type TEXT NOT NULL CHECK (event_type IN ('merge', 'split', 'reversal', 'supersede')),
    subject_identifier_ids JSONB NOT NULL,
    reason TEXT NOT NULL CHECK (btrim(reason) <> ''),
    actor_role TEXT NOT NULL CHECK (btrim(actor_role) <> ''),
    occurred_at TIMESTAMPTZ NOT NULL,
    canonical_merge_executed BOOLEAN NOT NULL DEFAULT false CHECK (canonical_merge_executed = false),
    publication_status TEXT NOT NULL DEFAULT 'not_eligible' CHECK (publication_status = 'not_eligible'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (jsonb_typeof(subject_identifier_ids) = 'array' AND jsonb_array_length(subject_identifier_ids) > 0)
);
CREATE INDEX identity_lineage_events_candidate_idx
    ON uec.identity_lineage_events (candidate_edge_id, occurred_at DESC, identity_lineage_event_id DESC);

CREATE TRIGGER identity_candidate_edges_append_only
    BEFORE UPDATE OR DELETE ON uec.identity_candidate_edges
    FOR EACH ROW EXECUTE FUNCTION uec.reject_evidence_mutation();
CREATE TRIGGER identity_review_events_append_only
    BEFORE UPDATE OR DELETE ON uec.identity_review_events
    FOR EACH ROW EXECUTE FUNCTION uec.reject_evidence_mutation();
CREATE TRIGGER identity_lineage_events_append_only
    BEFORE UPDATE OR DELETE ON uec.identity_lineage_events
    FOR EACH ROW EXECUTE FUNCTION uec.reject_evidence_mutation();

COMMENT ON TABLE uec.identity_candidate_edges IS
    'Private probabilistic or deterministic identity leads. Candidate edges never create canonical merges or transfer claims.';
COMMENT ON TABLE uec.identity_review_events IS
    'Append-only review decisions for identity candidates; corrections are new events.';
COMMENT ON TABLE uec.identity_lineage_events IS
    'Append-only merge/split/reversal history. This D4 table records intent/history only; it never rewrites entity IDs.';
