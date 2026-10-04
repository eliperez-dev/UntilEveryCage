-- Preserve the identity of a source artifact when retention rules or historic
-- workspace state mean the bytes are no longer available. A retained artifact
-- remains the default and still requires its locator and exact byte size.
ALTER TABLE uec.raw_artifacts
    ALTER COLUMN storage_key DROP NOT NULL,
    ALTER COLUMN byte_size DROP NOT NULL;

ALTER TABLE uec.raw_artifacts
    ADD COLUMN retention_status TEXT NOT NULL DEFAULT 'retained'
        CHECK (retention_status IN ('retained', 'not_retained')),
    ADD CONSTRAINT raw_artifacts_retention_contract CHECK (
        (retention_status = 'retained' AND storage_key IS NOT NULL AND byte_size IS NOT NULL)
        OR
        (retention_status = 'not_retained' AND storage_key IS NULL AND byte_size IS NULL)
    );

COMMENT ON COLUMN uec.raw_artifacts.retention_status IS
    'Whether the original source bytes are retained. not_retained preserves recorded source identity metadata only; its checksum is not independently reverified while bytes are unavailable.';
