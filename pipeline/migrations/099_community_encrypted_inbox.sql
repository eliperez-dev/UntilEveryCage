-- Restricted ciphertext relay. No source, release, map or legacy intake writes.
-- Client encryption/signature verification is separate; these tables do not
-- establish that arbitrary submitted armor contains a valid encrypted message.
CREATE TABLE uec.community_secure_inboxes (
    case_id UUID PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('facility','evidence','correction','duplicate','privacy_removal','bug')),
    protocol TEXT NOT NULL CHECK (protocol='uec-openpgp-inbox-v1'),
    access_secret_sha256 CHAR(64) CHECK (access_secret_sha256 IS NULL OR access_secret_sha256 ~ '^[0-9a-f]{64}$'),
    contributor_public_key TEXT NOT NULL CHECK (octet_length(contributor_public_key)<=16384),
    contributor_fingerprint TEXT NOT NULL,
    reviewer_public_key TEXT NOT NULL CHECK (octet_length(reviewer_public_key)<=16384),
    reviewer_fingerprint TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'received'
        CHECK (status IN ('received','in_review','needs_information','closed','removed')),
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (expires_at>created_at),
    CHECK (status='removed' OR (
        access_secret_sha256 IS NOT NULL
        AND contributor_fingerprint ~ '^([0-9a-f]{40}|[0-9a-f]{64})$'
        AND reviewer_fingerprint ~ '^([0-9a-f]{40}|[0-9a-f]{64})$'
        AND contributor_fingerprint<>reviewer_fingerprint
        AND contributor_public_key LIKE '-----BEGIN PGP PUBLIC KEY BLOCK-----%'
        AND reviewer_public_key LIKE '-----BEGIN PGP PUBLIC KEY BLOCK-----%'
        AND position('PRIVATE KEY' IN contributor_public_key)=0
        AND position('PRIVATE KEY' IN reviewer_public_key)=0
    ))
);
CREATE INDEX community_secure_inboxes_expiry_idx ON uec.community_secure_inboxes(expires_at);
CREATE INDEX community_secure_inboxes_daily_idx ON uec.community_secure_inboxes(created_at);
CREATE INDEX community_secure_inboxes_pending_idx ON uec.community_secure_inboxes(created_at)
    WHERE status IN ('received','in_review','needs_information');

CREATE TABLE uec.community_secure_messages (
    case_id UUID NOT NULL REFERENCES uec.community_secure_inboxes(case_id) ON DELETE CASCADE,
    message_id UUID NOT NULL,
    ordinal INTEGER NOT NULL CHECK (ordinal BETWEEN 1 AND 32),
    author TEXT NOT NULL CHECK (author IN ('contributor','reviewer')),
    ciphertext TEXT NOT NULL CHECK (octet_length(ciphertext) BETWEEN 64 AND 98304
        AND ciphertext LIKE '-----BEGIN PGP MESSAGE-----%'
        AND position('PRIVATE KEY' IN ciphertext)=0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (case_id,message_id),
    UNIQUE(case_id,ordinal)
);

CREATE TABLE uec.community_secure_events (
    event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id UUID NOT NULL REFERENCES uec.community_secure_inboxes(case_id) ON DELETE CASCADE,
    action TEXT NOT NULL CHECK (action IN ('received','message_added','status_changed','revoked','expired')),
    actor_role TEXT NOT NULL CHECK (actor_role IN ('contributor','reviewer','system')),
    status TEXT CHECK (status IN ('received','in_review','needs_information','closed','removed')),
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX community_secure_events_case_idx ON uec.community_secure_events(case_id,occurred_at);

-- Ordinary corrections add messages/events. DELETE remains possible for
-- authorized removal/expiry; append-only rules must not prevent erasure.
CREATE FUNCTION uec.reject_secure_inbox_evidence_update() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'encrypted inbox evidence cannot be updated' USING ERRCODE='55006';
END;
$$;
CREATE TRIGGER community_secure_messages_no_update BEFORE UPDATE ON uec.community_secure_messages
    FOR EACH ROW EXECUTE FUNCTION uec.reject_secure_inbox_evidence_update();
CREATE TRIGGER community_secure_events_no_update BEFORE UPDATE ON uec.community_secure_events
    FOR EACH ROW EXECUTE FUNCTION uec.reject_secure_inbox_evidence_update();

COMMENT ON TABLE uec.community_secure_inboxes IS
    'Experimental restricted inbox metadata and public keys. No private key or recovery secret belongs here. Not a curated facility or publication decision.';
COMMENT ON TABLE uec.community_secure_messages IS
    'Opaque client-generated OpenPGP messages. Sender role is relay authorization metadata, not a verified cryptographic signature. Clients must verify signatures, keys and case context.';
