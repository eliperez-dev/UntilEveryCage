-- Isolated local real-data preview. These rows never join release membership.
CREATE SCHEMA IF NOT EXISTS real_preview;

CREATE TABLE real_preview.imports (
    snapshot_sha256 CHAR(64) PRIMARY KEY,
    observation_count BIGINT NOT NULL CHECK (observation_count >= 0),
    imported_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE real_preview.source_manifests (
    snapshot_sha256 CHAR(64) NOT NULL REFERENCES real_preview.imports(snapshot_sha256),
    source_id TEXT NOT NULL CHECK (source_id IN ('fr.dgal.section-i','fr.dgal.section-ii','it.853-2004','us.fsis')),
    source_artifact_sha256 CHAR(64) NOT NULL CHECK (source_artifact_sha256 ~ '^[0-9a-f]{64}$'),
    normalized_sha256 CHAR(64) NOT NULL CHECK (normalized_sha256 ~ '^[0-9a-f]{64}$'),
    normalized_rows BIGINT NOT NULL CHECK (normalized_rows >= 0),
    source_url TEXT NOT NULL,
    retrieved_at TIMESTAMPTZ NOT NULL,
    code_version TEXT NOT NULL,
    config_version TEXT NOT NULL,
    PRIMARY KEY (snapshot_sha256, source_id)
);

CREATE TABLE real_preview.observations (
    preview_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    snapshot_sha256 CHAR(64) NOT NULL REFERENCES real_preview.imports(snapshot_sha256),
    source_id TEXT NOT NULL CHECK (source_id IN ('fr.dgal.section-i','fr.dgal.section-ii','it.853-2004','us.fsis')),
    source_identifier TEXT NOT NULL,
    location_class TEXT NOT NULL CHECK (location_class IN ('numeric_source_coordinate','city_postal','unmapped_private_observation')),
    facility_candidate BOOLEAN NOT NULL DEFAULT false,
    country_code CHAR(2),
    city TEXT,
    postal_code TEXT,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    coordinate_precision TEXT,
    source_observed_at TIMESTAMPTZ,
    CHECK ((latitude IS NULL) = (longitude IS NULL)),
    CHECK (latitude IS NULL OR (latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180)),
    CHECK (location_class <> 'numeric_source_coordinate' OR latitude IS NOT NULL),
    UNIQUE (snapshot_sha256, source_id, source_identifier)
);

CREATE INDEX real_preview_map_idx ON real_preview.observations (latitude, longitude, preview_id)
    WHERE location_class = 'numeric_source_coordinate';
CREATE INDEX real_preview_source_cursor_idx ON real_preview.observations (source_id, preview_id)
    WHERE facility_candidate AND location_class <> 'unmapped_private_observation';

CREATE OR REPLACE FUNCTION real_preview.reject_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'real preview evidence is append-only';
END;
$$;
CREATE TRIGGER real_preview_observations_immutable
    BEFORE UPDATE OR DELETE ON real_preview.observations
    FOR EACH ROW EXECUTE FUNCTION real_preview.reject_mutation();
CREATE TRIGGER real_preview_imports_immutable
    BEFORE UPDATE OR DELETE ON real_preview.imports
    FOR EACH ROW EXECUTE FUNCTION real_preview.reject_mutation();
CREATE TRIGGER real_preview_source_manifests_immutable
    BEFORE UPDATE OR DELETE ON real_preview.source_manifests
    FOR EACH ROW EXECUTE FUNCTION real_preview.reject_mutation();

COMMENT ON SCHEMA real_preview IS 'Private loopback-only development preview; never a release or publication projection.';
COMMENT ON TABLE real_preview.observations IS 'Source-scoped minimum fields for the authenticated local real-data preview; raw source payloads are not stored.';
