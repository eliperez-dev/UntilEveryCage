-- Preserve the source-scoped candidate grouping used by the private preview.
CREATE TABLE real_preview.candidates (
    candidate_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    snapshot_sha256 CHAR(64) NOT NULL REFERENCES real_preview.imports(snapshot_sha256),
    source_id TEXT NOT NULL CHECK (source_id IN ('fr.dgal.section-i','fr.dgal.section-ii','it.853-2004','us.fsis')),
    source_group_key TEXT NOT NULL,
    representative_observation_id UUID NOT NULL REFERENCES real_preview.observations(preview_id),
    location_class TEXT NOT NULL CHECK (location_class IN ('numeric_source_coordinate','city_postal')),
    country_code CHAR(2),
    city TEXT,
    postal_code TEXT,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    coordinate_precision TEXT,
    observation_count BIGINT NOT NULL CHECK (observation_count > 0),
    CHECK ((latitude IS NULL) = (longitude IS NULL)),
    CHECK (latitude IS NULL OR (latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180)),
    CHECK (location_class <> 'numeric_source_coordinate' OR latitude IS NOT NULL),
    UNIQUE (snapshot_sha256, source_id, source_group_key)
);

CREATE INDEX real_preview_candidate_source_cursor_idx
    ON real_preview.candidates (source_id, candidate_id);
CREATE INDEX real_preview_candidate_map_idx
    ON real_preview.candidates (latitude, longitude, candidate_id)
    WHERE location_class = 'numeric_source_coordinate';

CREATE TRIGGER real_preview_candidates_immutable
    BEFORE UPDATE OR DELETE ON real_preview.candidates
    FOR EACH ROW EXECUTE FUNCTION real_preview.reject_mutation();

COMMENT ON TABLE real_preview.candidates IS 'Private source-scoped provisional groups derived from documented source identifiers; not cross-source identity merges or publication records.';
