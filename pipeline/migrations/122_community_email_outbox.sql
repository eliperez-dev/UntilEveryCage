-- Restricted delivery queue. Only the community role may access it.
ALTER TABLE uec.community_submission_contacts
    ADD COLUMN email_updates BOOLEAN NOT NULL DEFAULT false;

CREATE TABLE uec.community_email_outbox (
    id UUID PRIMARY KEY,
    submission_id UUID NOT NULL REFERENCES uec.community_submissions ON DELETE CASCADE,
    contact_submission_id UUID REFERENCES uec.community_submission_contacts ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('reviewer_alert', 'status_update', 'reply')),
    content TEXT CHECK (octet_length(content) <= 2000),
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts BETWEEN 0 AND 5),
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL DEFAULT now() + interval '24 hours',
    finished_at TIMESTAMPTZ,
    CHECK ((kind = 'reviewer_alert' AND contact_submission_id IS NULL)
        OR (kind <> 'reviewer_alert' AND contact_submission_id IS NOT NULL
            AND contact_submission_id = submission_id))
);

CREATE INDEX community_email_outbox_pending_idx
    ON uec.community_email_outbox (next_attempt_at) WHERE finished_at IS NULL;
