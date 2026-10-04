-- Restricted, account-free community intake. This is not a source adapter and
-- does not add source records, observations, release membership, or map rows.
CREATE TABLE uec.community_submissions (
    submission_id UUID PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('facility', 'evidence', 'correction', 'duplicate', 'privacy_removal')),
    status TEXT NOT NULL CHECK (status IN ('received', 'held', 'screened', 'rejected', 'restricted', 'removed', 'published')),
    claim JSONB NOT NULL,
    receipt_secret_sha256 CHAR(64) CHECK (receipt_secret_sha256 IS NULL OR receipt_secret_sha256 ~ '^[0-9a-f]{64}$'),
    receipt_expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    linked_source_record_id UUID,
    linked_release_id TEXT,
    CHECK ((linked_source_record_id IS NULL) = (linked_release_id IS NULL))
);
CREATE INDEX community_submissions_pending_idx ON uec.community_submissions(created_at)
    WHERE status IN ('received', 'held');
CREATE INDEX community_submissions_daily_idx ON uec.community_submissions(created_at);

-- Contact is separately retained and omitted from all queue/public views.
CREATE TABLE uec.community_submission_contacts (
    submission_id UUID PRIMARY KEY REFERENCES uec.community_submissions(submission_id) ON DELETE CASCADE,
    email TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Decisions carry no user payload or free-form operator note.
CREATE TABLE uec.community_submission_events (
    event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    submission_id UUID NOT NULL REFERENCES uec.community_submissions(submission_id) ON DELETE CASCADE,
    action TEXT NOT NULL CHECK (action IN ('received', 'hold', 'screen', 'reject', 'restrict', 'remove', 'link_community', 'expire')),
    reason_code TEXT NOT NULL CHECK (reason_code IN (
        'intake_received', 'retention_expired', 'privacy', 'abuse', 'duplicate',
        'out_of_scope', 'eligible', 'other', 'privacy_screened',
        'insufficient_information', 'duplicate_claim', 'abuse_or_targeting',
        'privacy_or_safety_concern', 'operator_review',
        'eligible_existing_community_record', 'removed_by_request'
    )),
    actor_role TEXT NOT NULL CHECK (actor_role IN ('system', 'operator')),
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    release_id TEXT,
    source_record_id UUID
);
CREATE INDEX community_submission_events_case_idx ON uec.community_submission_events(submission_id, occurred_at DESC);

CREATE FUNCTION uec.reject_community_event_update() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'community decision events are append-only; add a new event instead'
        USING ERRCODE = '55006';
END;
$$;
CREATE TRIGGER community_submission_events_append_only
    BEFORE UPDATE OR DELETE ON uec.community_submission_events
    FOR EACH ROW EXECUTE FUNCTION uec.reject_community_event_update();

COMMENT ON TABLE uec.community_submissions IS
    'Restricted untrusted contributor claims. Never a publication/source table; public reuse requires operator linkage to a live eligible community release projection.';
