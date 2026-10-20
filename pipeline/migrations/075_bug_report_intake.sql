-- Bug reports share restricted intake, limits, retention and operator review.
-- They never become facility/source records or public community claims.
ALTER TABLE uec.community_submissions
    DROP CONSTRAINT community_submissions_kind_check,
    ADD CONSTRAINT community_submissions_kind_check
        CHECK (kind IN ('facility', 'evidence', 'correction', 'duplicate', 'privacy_removal', 'bug')),
    ADD CONSTRAINT community_bug_reports_private_check
        CHECK (kind <> 'bug' OR (status <> 'published' AND linked_source_record_id IS NULL AND linked_release_id IS NULL));
