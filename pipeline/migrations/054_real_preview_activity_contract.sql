-- Add an additive multi-activity contract to the private preview. Detailed
-- source values remain in the hash-checked handoff and are linked by each
-- representative observation; these bounded fields are the candidate view.
ALTER TABLE real_preview.candidates
    ADD COLUMN category TEXT,
    ADD COLUMN activity_categories TEXT[] NOT NULL DEFAULT '{}',
    ADD COLUMN source_activity_codes TEXT[] NOT NULL DEFAULT '{}',
    ADD COLUMN source_activity_labels TEXT[] NOT NULL DEFAULT '{}',
    ADD COLUMN activity_mapping_status TEXT NOT NULL DEFAULT 'unclassified',
    ADD COLUMN classification_ruleset_version TEXT,
    ADD CONSTRAINT real_preview_activity_contract_bounds
        CHECK (category IS NULL OR length(category) <= 80),
    ADD CONSTRAINT real_preview_activity_mapping_status
        CHECK (activity_mapping_status IN ('mapped','partial','unmapped','unclassified','conflicting','ambiguous')),
    ADD CONSTRAINT real_preview_activity_array_bounds
        CHECK (cardinality(activity_categories) <= 32
           AND cardinality(source_activity_codes) <= 64
           AND cardinality(source_activity_labels) <= 64
           AND length(array_to_string(activity_categories, '')) <= 2560
           AND length(array_to_string(source_activity_codes, '')) <= 7680
           AND length(array_to_string(source_activity_labels, '')) <= 12800),
    ADD CONSTRAINT real_preview_activity_display_consistency
        CHECK (category IS NULL OR category = ANY(activity_categories));

COMMENT ON COLUMN real_preview.candidates.category IS
    'Deterministic single display category; null for unknown, unsupported, or conflicting classifications.';
COMMENT ON COLUMN real_preview.candidates.activity_categories IS
    'All normalized activity categories for this source observation; additive and backward compatible with activity_label.';
COMMENT ON COLUMN real_preview.candidates.source_activity_codes IS
    'Source classification codes copied from normalized evidence; full source rows remain in the hash-checked private handoff.';
COMMENT ON COLUMN real_preview.candidates.source_activity_labels IS
    'Source activity/classification labels copied from normalized evidence; full source rows remain in the hash-checked private handoff.';
COMMENT ON COLUMN real_preview.candidates.activity_mapping_status IS
    'Whether classification mapping is mapped, partial, unmapped, unclassified, conflicting, or ambiguous.';
COMMENT ON COLUMN real_preview.candidates.classification_ruleset_version IS
    'Ruleset version used for normalized classification, when supplied by the source adapter.';
