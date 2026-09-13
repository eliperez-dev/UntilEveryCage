-- There is exactly one public release at a time. Promotion transactions may
-- demote the prior release first; this index is the final database invariant.
CREATE UNIQUE INDEX IF NOT EXISTS releases_only_one_promoted_idx
    ON uec.releases (status)
    WHERE status = 'promoted';
