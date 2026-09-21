-- D4 private graph persistence boundary.
-- These tables are append-only, private ingest evidence. They do not create a
-- release and are intentionally excluded from public graph projections.

CREATE TABLE uec.graph_ingest_runs (
    ingest_run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id TEXT NOT NULL REFERENCES uec.sources(source_id),
    source_kind TEXT NOT NULL CHECK (source_kind IN ('facility_master', 'evidence_event')),
    contract_version TEXT NOT NULL,
    handoff_sha256 CHAR(64) NOT NULL,
    item_count INTEGER NOT NULL CHECK (item_count >= 0),
    inserted_count INTEGER NOT NULL DEFAULT 0 CHECK (inserted_count >= 0),
    already_present_count INTEGER NOT NULL DEFAULT 0 CHECK (already_present_count >= 0),
    rejected_count INTEGER NOT NULL DEFAULT 0 CHECK (rejected_count >= 0),
    status TEXT NOT NULL DEFAULT 'in_progress'
        CHECK (status IN ('in_progress', 'completed', 'failed')),
    error_summary TEXT,
    storage_state TEXT NOT NULL DEFAULT 'private' CHECK (storage_state = 'private'),
    review_state TEXT NOT NULL DEFAULT 'review_required' CHECK (review_state = 'review_required'),
    privacy_status TEXT NOT NULL DEFAULT 'pending' CHECK (privacy_status = 'pending'),
    publication_status TEXT NOT NULL DEFAULT 'not_eligible' CHECK (publication_status = 'not_eligible'),
    release_id TEXT REFERENCES uec.releases(release_id),
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    UNIQUE (source_id, handoff_sha256),
    CHECK (release_id IS NULL),
    CHECK (status <> 'completed' OR completed_at IS NOT NULL),
    CHECK (status = 'failed' OR error_summary IS NULL)
);

CREATE TABLE uec.graph_ingest_items (
    ingest_item_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ingest_run_id UUID NOT NULL REFERENCES uec.graph_ingest_runs(ingest_run_id),
    source_id TEXT NOT NULL REFERENCES uec.sources(source_id),
    source_record_key TEXT NOT NULL,
    item_sha256 CHAR(64) NOT NULL,
    item_kind TEXT NOT NULL CHECK (item_kind IN ('facility_candidate', 'evidence_event')),
    status TEXT NOT NULL CHECK (status IN ('inserted', 'already_present', 'rejected')),
    rejection_code TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source_id, item_sha256),
    CHECK (status <> 'rejected' OR rejection_code IS NOT NULL),
    CHECK (status <> 'inserted' OR rejection_code IS NULL)
);

CREATE INDEX graph_ingest_items_run_idx ON uec.graph_ingest_items (ingest_run_id, status);
CREATE INDEX graph_ingest_items_source_key_idx ON uec.graph_ingest_items (source_id, source_record_key);

CREATE TABLE uec.graph_evidence_events (
    evidence_event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id TEXT NOT NULL REFERENCES uec.sources(source_id),
    source_record_id UUID NOT NULL REFERENCES uec.source_records(source_record_id),
    source_record_key TEXT NOT NULL,
    event_key TEXT NOT NULL,
    event_type TEXT NOT NULL,
    event_date DATE,
    event_period TEXT,
    event_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    observed_at TIMESTAMPTZ NOT NULL,
    review_state TEXT NOT NULL DEFAULT 'review_required'
        CHECK (review_state IN ('unreviewed', 'review_required', 'reviewed', 'accepted', 'rejected')),
    storage_state TEXT NOT NULL DEFAULT 'private'
        CHECK (storage_state IN ('raw', 'private', 'reviewed', 'released')),
    privacy_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (privacy_status IN ('pending', 'passed', 'failed', 'suppressed')),
    publication_status TEXT NOT NULL DEFAULT 'not_eligible'
        CHECK (publication_status IN ('not_eligible', 'eligible', 'released', 'suppressed')),
    release_id TEXT REFERENCES uec.releases(release_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source_id, event_key),
    CHECK (release_id IS NULL),
    CHECK (publication_status <> 'released' OR (release_id IS NOT NULL AND storage_state = 'released'
        AND review_state = 'accepted' AND privacy_status = 'passed'))
);

CREATE INDEX graph_evidence_events_source_idx
    ON uec.graph_evidence_events (source_id, observed_at DESC, evidence_event_id DESC);
CREATE INDEX graph_evidence_events_review_idx
    ON uec.graph_evidence_events (review_state, privacy_status, publication_status);

CREATE TABLE uec.graph_evidence_links (
    evidence_link_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    evidence_event_id UUID NOT NULL REFERENCES uec.graph_evidence_events(evidence_event_id),
    target_source_id TEXT NOT NULL REFERENCES uec.sources(source_id),
    target_identifier_type TEXT NOT NULL,
    target_source_identifier TEXT NOT NULL,
    identity_scope TEXT NOT NULL DEFAULT 'source_scoped' CHECK (identity_scope = 'source_scoped'),
    match_method TEXT NOT NULL,
    confidence NUMERIC(5,4) CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1),
    assertion_status TEXT NOT NULL DEFAULT 'candidate'
        CHECK (assertion_status IN ('candidate', 'accepted', 'rejected', 'review_required', 'disputed')),
    review_state TEXT NOT NULL DEFAULT 'review_required'
        CHECK (review_state IN ('unreviewed', 'review_required', 'reviewed', 'accepted', 'rejected')),
    storage_state TEXT NOT NULL DEFAULT 'private' CHECK (storage_state = 'private'),
    privacy_status TEXT NOT NULL DEFAULT 'pending' CHECK (privacy_status = 'pending'),
    publication_status TEXT NOT NULL DEFAULT 'not_eligible' CHECK (publication_status = 'not_eligible'),
    release_id TEXT REFERENCES uec.releases(release_id),
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (evidence_event_id, target_source_id, target_identifier_type, target_source_identifier, match_method),
    CHECK (release_id IS NULL)
);

CREATE INDEX graph_evidence_links_target_idx
    ON uec.graph_evidence_links (target_source_id, target_identifier_type, target_source_identifier);

CREATE TABLE uec.graph_lineage_events (
    lineage_event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id TEXT REFERENCES uec.sources(source_id),
    entity_kind TEXT NOT NULL CHECK (entity_kind IN ('facility', 'organization', 'evidence_event', 'crosswalk', 'relationship', 'claim')),
    entity_ref TEXT NOT NULL,
    event_type TEXT NOT NULL CHECK (event_type IN ('merge', 'split', 'supersede', 'reverse', 'correct')),
    prior_ref TEXT,
    successor_ref TEXT,
    reason TEXT NOT NULL,
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    review_state TEXT NOT NULL DEFAULT 'review_required'
        CHECK (review_state IN ('unreviewed', 'review_required', 'reviewed', 'accepted', 'rejected')),
    storage_state TEXT NOT NULL DEFAULT 'private' CHECK (storage_state = 'private'),
    privacy_status TEXT NOT NULL DEFAULT 'pending' CHECK (privacy_status = 'pending'),
    publication_status TEXT NOT NULL DEFAULT 'not_eligible' CHECK (publication_status = 'not_eligible'),
    release_id TEXT REFERENCES uec.releases(release_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (release_id IS NULL),
    CHECK (prior_ref IS NOT NULL OR successor_ref IS NOT NULL)
);

CREATE INDEX graph_lineage_entity_idx ON uec.graph_lineage_events (entity_kind, entity_ref, created_at DESC);

CREATE OR REPLACE FUNCTION uec.reject_private_graph_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'append-only private graph table %.% rejects %; add a new event instead',
        TG_TABLE_SCHEMA, TG_TABLE_NAME, TG_OP USING ERRCODE = '55006';
END;
$$;

CREATE TRIGGER graph_ingest_items_append_only BEFORE UPDATE OR DELETE ON uec.graph_ingest_items
    FOR EACH ROW EXECUTE FUNCTION uec.reject_private_graph_mutation();
CREATE TRIGGER graph_evidence_events_append_only BEFORE UPDATE OR DELETE ON uec.graph_evidence_events
    FOR EACH ROW EXECUTE FUNCTION uec.reject_private_graph_mutation();
CREATE TRIGGER graph_evidence_links_append_only BEFORE UPDATE OR DELETE ON uec.graph_evidence_links
    FOR EACH ROW EXECUTE FUNCTION uec.reject_private_graph_mutation();
CREATE TRIGGER graph_lineage_events_append_only BEFORE UPDATE OR DELETE ON uec.graph_lineage_events
    FOR EACH ROW EXECUTE FUNCTION uec.reject_private_graph_mutation();

COMMENT ON TABLE uec.graph_ingest_runs IS 'Private, resumable graph handoff runs; never a release or publication authorization.';
COMMENT ON TABLE uec.graph_evidence_events IS 'Source-local evidence events; they never become facility-master rows by import.';
COMMENT ON TABLE uec.graph_evidence_links IS 'Reviewable source-scoped evidence links, including uncertain candidates; no global identity is asserted.';
COMMENT ON TABLE uec.graph_lineage_events IS 'Append-only private merge/split/supersession/reversal history.';
