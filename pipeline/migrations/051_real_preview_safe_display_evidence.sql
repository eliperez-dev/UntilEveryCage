-- Optional source-facing display fields for the authenticated local preview.
-- Values are selected by the importer from its allowlisted normalized fields;
-- this is not a public projection or publication approval.
ALTER TABLE real_preview.candidates
    ADD COLUMN display_name TEXT,
    ADD COLUMN activity_label TEXT,
    ADD COLUMN activity_source TEXT,
    ADD COLUMN evidence_summary TEXT,
    ADD COLUMN source_record_url TEXT,
    ADD COLUMN source_name TEXT,
    ADD COLUMN observed_at TIMESTAMPTZ;

ALTER TABLE real_preview.candidates
    ADD CONSTRAINT real_preview_safe_display_lengths
        CHECK ((display_name IS NULL OR length(display_name) <= 200)
           AND (activity_label IS NULL OR length(activity_label) <= 240)
           AND (activity_source IS NULL OR length(activity_source) <= 80)
           AND (evidence_summary IS NULL OR length(evidence_summary) <= 500)
           AND (source_record_url IS NULL OR length(source_record_url) <= 2048)
           AND (source_name IS NULL OR length(source_name) <= 160)),
    ADD CONSTRAINT real_preview_https_record_url
        CHECK (source_record_url IS NULL OR
               (source_record_url ~ '^https://[^/?#@]+(/[^?#]*)?$'
                AND source_record_url !~ '[[:cntrl:]]'));

COMMENT ON COLUMN real_preview.candidates.display_name IS
    'Optional normalized display label; importer emits only when the source privacy gate explicitly permits display.';
COMMENT ON COLUMN real_preview.candidates.activity_label IS
    'Optional short allowlisted source activity label; not a project classification or factual review.';
COMMENT ON COLUMN real_preview.candidates.activity_source IS
    'Origin label for activity_label; currently source when copied from normalized source fields.';
COMMENT ON COLUMN real_preview.candidates.evidence_summary IS
    'Optional sanitized normalized summary; absent when no explicitly allowlisted summary exists.';
COMMENT ON COLUMN real_preview.candidates.source_record_url IS
    'Optional HTTPS-only source-record link; no credentials, query, or fragment.';
COMMENT ON COLUMN real_preview.candidates.source_name IS
    'Maintained display label for the allowlisted source_id.';
