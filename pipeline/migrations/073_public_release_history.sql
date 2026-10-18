-- Historical public eligibility is distinct from the single currently active
-- release.  A later activation must not turn a previously published release
-- into an arbitrary validated candidate.
CREATE TABLE uec.public_release_history (
    release_id TEXT PRIMARY KEY REFERENCES uec.releases(release_id),
    profile TEXT NOT NULL,
    published_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (profile IN ('official', 'secondary', 'community'))
);

CREATE INDEX public_release_history_profile_published_idx
    ON uec.public_release_history (profile, published_at DESC, release_id DESC);

CREATE TRIGGER public_release_history_append_only
    BEFORE UPDATE OR DELETE ON uec.public_release_history
    FOR EACH ROW EXECUTE FUNCTION uec.reject_evidence_mutation();
