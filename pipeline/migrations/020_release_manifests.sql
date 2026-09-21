-- Safe, immutable release-verification summaries. Never store raw artifacts,
-- credentials, addresses, coordinates, or suppression payloads here.
CREATE TABLE uec.release_manifests (
    release_id TEXT PRIMARY KEY REFERENCES uec.releases(release_id),
    manifest JSONB NOT NULL,
    manifest_sha256 CHAR(64) NOT NULL CHECK (manifest_sha256 ~ '^[0-9a-f]{64}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TRIGGER release_manifests_append_only
    BEFORE UPDATE OR DELETE ON uec.release_manifests
    FOR EACH ROW EXECUTE FUNCTION uec.reject_evidence_mutation();
