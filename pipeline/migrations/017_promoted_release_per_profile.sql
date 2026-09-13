-- Official, secondary, and community releases are independent public profiles.
DROP INDEX IF EXISTS uec.releases_only_one_promoted_idx;
CREATE UNIQUE INDEX IF NOT EXISTS releases_one_promoted_per_profile_idx
    ON uec.releases (profile)
    WHERE status = 'promoted';
