-- Taxonomy provenance for isolated preview candidate groups. These IDs belong
-- to real_preview and must never be represented as uec.observations.
-- `category` is the broad taxonomy display value; `activity_categories`
-- remains the source's normalized category list and may use a different key.
ALTER TABLE real_preview.candidates
    DROP CONSTRAINT IF EXISTS real_preview_activity_display_consistency;
ALTER TABLE real_preview.candidates
    ADD CONSTRAINT real_preview_candidates_taxonomy_lineage_unique
    UNIQUE (snapshot_sha256, source_id, candidate_id);
ALTER TABLE real_preview.observations
    ADD CONSTRAINT real_preview_observations_taxonomy_lineage_unique
    UNIQUE (snapshot_sha256, source_id, preview_id);

CREATE TABLE real_preview.taxonomy_crosswalks (
    source_id TEXT NOT NULL,
    taxonomy_version TEXT NOT NULL CHECK (taxonomy_version = 'uec-taxonomy-v1'),
    crosswalk_version TEXT NOT NULL CHECK (length(btrim(crosswalk_version)) > 0),
    ruleset_version TEXT NOT NULL CHECK (length(btrim(ruleset_version)) > 0),
    definition JSONB NOT NULL CHECK (jsonb_typeof(definition) = 'object'),
    definition_sha256 CHAR(64) NOT NULL CHECK (definition_sha256 ~ '^[0-9a-f]{64}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (source_id, crosswalk_version),
    UNIQUE (source_id, taxonomy_version, crosswalk_version, ruleset_version),
    CHECK (definition ?& ARRAY['source_id', 'taxonomy_version', 'crosswalk_version', 'ruleset_version', 'rules']),
    CHECK (definition->>'source_id' IS NOT DISTINCT FROM source_id),
    CHECK (definition->>'taxonomy_version' IS NOT DISTINCT FROM taxonomy_version),
    CHECK (definition->>'crosswalk_version' IS NOT DISTINCT FROM crosswalk_version),
    CHECK (definition->>'ruleset_version' IS NOT DISTINCT FROM ruleset_version),
    CHECK (jsonb_typeof(definition->'rules') = 'array')
);

CREATE TABLE real_preview.candidate_taxonomy_assignment_sets (
    assignment_set_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id UUID NOT NULL REFERENCES real_preview.candidates(candidate_id),
    representative_observation_id UUID NOT NULL REFERENCES real_preview.observations(preview_id),
    snapshot_sha256 CHAR(64) NOT NULL,
    source_id TEXT NOT NULL,
    taxonomy_version TEXT NOT NULL CHECK (taxonomy_version = 'uec-taxonomy-v1'),
    crosswalk_version TEXT NOT NULL,
    ruleset_version TEXT NOT NULL,
    display_category TEXT NOT NULL CHECK (display_category IN (
        'animal_keeping_and_production', 'slaughter', 'processing_and_preparation',
        'research_and_animal_use', 'other_regulated_premises', 'unclassified'
    )),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    FOREIGN KEY (snapshot_sha256, source_id, candidate_id)
        REFERENCES real_preview.candidates(snapshot_sha256, source_id, candidate_id),
    FOREIGN KEY (snapshot_sha256, source_id, representative_observation_id)
        REFERENCES real_preview.observations(snapshot_sha256, source_id, preview_id),
    FOREIGN KEY (source_id, taxonomy_version, crosswalk_version, ruleset_version)
        REFERENCES real_preview.taxonomy_crosswalks(source_id, taxonomy_version, crosswalk_version, ruleset_version),
    UNIQUE (candidate_id, taxonomy_version, crosswalk_version, ruleset_version)
);

CREATE TABLE real_preview.candidate_taxonomy_assignments (
    assignment_set_id UUID NOT NULL REFERENCES real_preview.candidate_taxonomy_assignment_sets(assignment_set_id),
    assignment_ordinal INTEGER NOT NULL CHECK (assignment_ordinal >= 0),
    primary_key TEXT NOT NULL CHECK (primary_key IN (
        'animal_keeping_and_production', 'slaughter', 'processing_and_preparation',
        'research_and_animal_use', 'other_regulated_premises', 'unclassified'
    )),
    leaf_key TEXT,
    leaf_label TEXT,
    source_code_reference TEXT,
    source_label_reference TEXT,
    source_code TEXT,
    source_label TEXT,
    mapping_method TEXT NOT NULL CHECK (mapping_method IN ('direct', 'derived', 'candidate')),
    mapping_status TEXT NOT NULL CHECK (mapping_status IN (
        'mapped', 'partial', 'unmapped', 'unclassified', 'conflicting', 'ambiguous'
    )),
    CHECK (leaf_key IS NOT NULL OR leaf_label IS NULL),
    CHECK (primary_key <> 'unclassified' OR leaf_key IS NULL),
    CHECK (primary_key <> 'unclassified' OR mapping_status NOT IN ('mapped', 'partial')),
    CHECK (mapping_status NOT IN ('unmapped', 'unclassified', 'conflicting', 'ambiguous') OR primary_key = 'unclassified'),
    CHECK (mapping_method <> 'candidate' OR (primary_key = 'unclassified' AND mapping_status = 'ambiguous')),
    CHECK (leaf_key IS NULL OR length(leaf_key) <= 200),
    CHECK (leaf_label IS NULL OR length(leaf_label) <= 500),
    CHECK (source_code_reference IS NULL OR length(source_code_reference) <= 500),
    CHECK (source_label_reference IS NULL OR length(source_label_reference) <= 500),
    CHECK (source_code IS NULL OR length(source_code) <= 1000),
    CHECK (source_label IS NULL OR length(source_label) <= 5000),
    PRIMARY KEY (assignment_set_id, assignment_ordinal)
);

CREATE UNIQUE INDEX candidate_taxonomy_assignment_natural_key
    ON real_preview.candidate_taxonomy_assignments (
        assignment_set_id, primary_key, COALESCE(leaf_key, ''), COALESCE(leaf_label, ''),
        COALESCE(source_code_reference, ''), COALESCE(source_label_reference, ''),
        COALESCE(source_code, ''), COALESCE(source_label, ''), mapping_method, mapping_status
    );

CREATE VIEW real_preview.candidate_taxonomy_assignments_lineage AS
SELECT a.assignment_set_id, a.assignment_ordinal,
       s.candidate_id, s.representative_observation_id, s.snapshot_sha256, s.source_id,
       s.taxonomy_version, s.crosswalk_version, s.ruleset_version, s.display_category,
       o.source_identifier,
       a.primary_key, a.leaf_key, a.leaf_label,
       a.source_code_reference, a.source_label_reference,
       a.source_code, a.source_label, a.mapping_method, a.mapping_status
  FROM real_preview.candidate_taxonomy_assignments AS a
  JOIN real_preview.candidate_taxonomy_assignment_sets AS s USING (assignment_set_id)
  JOIN real_preview.observations AS o ON o.preview_id=s.representative_observation_id;

CREATE INDEX candidate_taxonomy_assignment_sets_current_idx
    ON real_preview.candidate_taxonomy_assignment_sets (candidate_id, created_at DESC, assignment_set_id DESC);
CREATE INDEX candidate_taxonomy_primary_idx
    ON real_preview.candidate_taxonomy_assignments (primary_key, assignment_set_id);

CREATE TRIGGER preview_taxonomy_crosswalks_append_only
    BEFORE UPDATE OR DELETE ON real_preview.taxonomy_crosswalks
    FOR EACH ROW EXECUTE FUNCTION real_preview.reject_mutation();
CREATE TRIGGER preview_taxonomy_assignment_sets_append_only
    BEFORE UPDATE OR DELETE ON real_preview.candidate_taxonomy_assignment_sets
    FOR EACH ROW EXECUTE FUNCTION real_preview.reject_mutation();
CREATE TRIGGER preview_taxonomy_assignments_append_only
    BEFORE UPDATE OR DELETE ON real_preview.candidate_taxonomy_assignments
    FOR EACH ROW EXECUTE FUNCTION real_preview.reject_mutation();

COMMENT ON TABLE real_preview.candidate_taxonomy_assignment_sets IS
    'Append-only taxonomy projections for private preview candidates, retaining real_preview identity lineage separately from UEC observations.';
