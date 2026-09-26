-- Source classification is independent from location quality and publication.
-- Out-of-default-scope groups stay listable/searchable in the private preview,
-- while map handlers can fail closed on this explicit flag.
ALTER TABLE real_preview.candidates
    ADD COLUMN IF NOT EXISTS default_map_scope BOOLEAN NOT NULL DEFAULT true,
    ADD COLUMN IF NOT EXISTS map_scope_reason TEXT;

CREATE INDEX IF NOT EXISTS real_preview_candidate_scope_idx
    ON real_preview.candidates (source_id, default_map_scope, candidate_id);

COMMENT ON COLUMN real_preview.candidates.default_map_scope IS
    'Source classification only; false records remain list/search discoverable but are outside default map scope.';
COMMENT ON COLUMN real_preview.candidates.map_scope_reason IS
    'Safe source classification/filter label explaining default map scope; contains no raw source payload.';
