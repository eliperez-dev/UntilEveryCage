ALTER TABLE uec.releases
    ADD COLUMN IF NOT EXISTS profile TEXT NOT NULL DEFAULT 'official'
    CHECK (profile IN ('official', 'secondary', 'community'));

COMMENT ON COLUMN uec.releases.profile IS
    'Publication context, distinct from source origin and factual review status.';
