-- Versioned, append-only activity mappings. Original source observations and
-- their compatibility classification_category remain untouched.
ALTER TABLE uec.source_records
    ADD CONSTRAINT source_records_taxonomy_lineage_unique
    UNIQUE (source_record_id, source_id, artifact_id);

ALTER TABLE uec.observations
    ADD CONSTRAINT observations_taxonomy_lineage_unique
    UNIQUE (observation_id, source_record_id);

CREATE TABLE uec.taxonomy_crosswalks (
    source_id TEXT NOT NULL REFERENCES uec.sources(source_id),
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

CREATE TABLE uec.observation_taxonomy_assignment_sets (
    assignment_set_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    observation_id UUID NOT NULL,
    source_record_id UUID NOT NULL,
    source_id TEXT NOT NULL,
    artifact_id UUID NOT NULL,
    taxonomy_version TEXT NOT NULL CHECK (taxonomy_version = 'uec-taxonomy-v1'),
    crosswalk_version TEXT NOT NULL CHECK (length(btrim(crosswalk_version)) > 0),
    ruleset_version TEXT NOT NULL CHECK (length(btrim(ruleset_version)) > 0),
    display_category TEXT NOT NULL CHECK (display_category IN (
        'animal_keeping_and_production', 'slaughter', 'processing_and_preparation',
        'research_and_animal_use', 'other_regulated_premises', 'unclassified'
    )),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    FOREIGN KEY (observation_id, source_record_id)
        REFERENCES uec.observations(observation_id, source_record_id),
    FOREIGN KEY (source_record_id, source_id, artifact_id)
        REFERENCES uec.source_records(source_record_id, source_id, artifact_id),
    FOREIGN KEY (source_id, taxonomy_version, crosswalk_version, ruleset_version)
        REFERENCES uec.taxonomy_crosswalks(source_id, taxonomy_version, crosswalk_version, ruleset_version),
    UNIQUE (observation_id, taxonomy_version, crosswalk_version, ruleset_version)
);

CREATE TABLE uec.observation_taxonomy_assignments (
    assignment_set_id UUID NOT NULL REFERENCES uec.observation_taxonomy_assignment_sets(assignment_set_id),
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

-- Avoid NULL's default distinctness so exact duplicate assignment rows are rejected.
CREATE UNIQUE INDEX observation_taxonomy_assignment_natural_key
    ON uec.observation_taxonomy_assignments (
        assignment_set_id, primary_key, COALESCE(leaf_key, ''), COALESCE(leaf_label, ''),
        COALESCE(source_code_reference, ''), COALESCE(source_label_reference, ''),
        COALESCE(source_code, ''), COALESCE(source_label, ''), mapping_method, mapping_status
    );

CREATE INDEX observation_taxonomy_sets_current_idx
    ON uec.observation_taxonomy_assignment_sets (observation_id, created_at DESC, assignment_set_id DESC);
CREATE INDEX observation_taxonomy_primary_idx
    ON uec.observation_taxonomy_assignments (primary_key, assignment_set_id);

CREATE VIEW uec.observation_taxonomy_assignments_lineage AS
SELECT a.assignment_set_id, a.assignment_ordinal,
       s.observation_id, s.source_record_id, s.source_id, s.artifact_id,
       s.taxonomy_version, s.crosswalk_version, s.ruleset_version,
       s.display_category,
       a.primary_key, a.leaf_key, a.leaf_label,
       a.source_code_reference, a.source_label_reference,
       a.source_code, a.source_label, a.mapping_method, a.mapping_status
  FROM uec.observation_taxonomy_assignments AS a
  JOIN uec.observation_taxonomy_assignment_sets AS s USING (assignment_set_id);

CREATE TRIGGER taxonomy_crosswalks_append_only
    BEFORE UPDATE OR DELETE ON uec.taxonomy_crosswalks
    FOR EACH ROW EXECUTE FUNCTION uec.reject_evidence_mutation();
CREATE TRIGGER taxonomy_assignment_sets_append_only
    BEFORE UPDATE OR DELETE ON uec.observation_taxonomy_assignment_sets
    FOR EACH ROW EXECUTE FUNCTION uec.reject_evidence_mutation();
CREATE TRIGGER taxonomy_assignments_append_only
    BEFORE UPDATE OR DELETE ON uec.observation_taxonomy_assignments
    FOR EACH ROW EXECUTE FUNCTION uec.reject_evidence_mutation();

COMMENT ON TABLE uec.taxonomy_crosswalks IS
    'Immutable, source-specific crosswalk document with required taxonomy, crosswalk, ruleset versions and canonical-document hash.';
COMMENT ON TABLE uec.observation_taxonomy_assignment_sets IS
    'Append-only per-observation taxonomy projection; the unique observation/version tuple makes reprojection idempotent.';
COMMENT ON TABLE uec.observation_taxonomy_assignments IS
    'Normalized primary and optional leaf assignments, retaining source value references and mapping method/status.';
COMMENT ON COLUMN uec.observation_taxonomy_assignment_sets.display_category IS
    'Deterministic scalar compatibility category; all primary and leaf assignments remain in child rows.';
