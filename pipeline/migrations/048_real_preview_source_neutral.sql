-- Preview eligibility is a separate private policy; source registration and
-- preview storage must not encode a frozen source list.
ALTER TABLE real_preview.source_manifests DROP CONSTRAINT IF EXISTS source_manifests_source_id_check;
ALTER TABLE real_preview.observations DROP CONSTRAINT IF EXISTS observations_source_id_check;
ALTER TABLE real_preview.candidates DROP CONSTRAINT IF EXISTS candidates_source_id_check;
ALTER TABLE real_preview.candidates DROP CONSTRAINT IF EXISTS candidates_location_class_check;
ALTER TABLE real_preview.observations DROP CONSTRAINT IF EXISTS observations_location_class_check;

ALTER TABLE real_preview.candidates
    ADD COLUMN IF NOT EXISTS display_latitude DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS display_longitude DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS display_geometry_source TEXT,
    ADD CONSTRAINT real_preview_candidates_display_pair
        CHECK ((display_latitude IS NULL) = (display_longitude IS NULL)),
    ADD CONSTRAINT real_preview_candidates_display_source_pair
        CHECK ((display_latitude IS NULL) = (display_geometry_source IS NULL)),
    ADD CONSTRAINT real_preview_candidates_display_range
        CHECK (display_latitude IS NULL OR (display_latitude BETWEEN -90 AND 90 AND display_longitude BETWEEN -180 AND 180 AND (display_latitude <> 0 OR display_longitude <> 0)));
CREATE INDEX IF NOT EXISTS real_preview_candidate_display_map_idx
    ON real_preview.candidates (display_latitude, display_longitude, candidate_id)
    WHERE display_latitude IS NOT NULL AND display_longitude IS NOT NULL;

CREATE TABLE IF NOT EXISTS real_preview.source_preview_runs (
    run_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    snapshot_sha256 CHAR(64) NOT NULL REFERENCES real_preview.imports(snapshot_sha256),
    source_url TEXT NOT NULL,
    retrieved_at TIMESTAMPTZ NOT NULL,
    source_artifact_sha256 CHAR(64) NOT NULL,
    normalized_sha256 CHAR(64) NOT NULL,
    adapter_version TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    input_count BIGINT NOT NULL CHECK (input_count >= 0),
    accepted_count BIGINT NOT NULL CHECK (accepted_count >= 0),
    quarantined_count BIGINT NOT NULL CHECK (quarantined_count >= 0),
    out_of_scope_count BIGINT NOT NULL CHECK (out_of_scope_count >= 0),
    imported_observation_count BIGINT NOT NULL CHECK (imported_observation_count >= 0),
    facility_count BIGINT NOT NULL CHECK (facility_count >= 0),
    numeric_coordinate_count BIGINT NOT NULL CHECK (numeric_coordinate_count >= 0),
    coarse_placeable_count BIGINT NOT NULL CHECK (coarse_placeable_count >= 0),
    unmapped_count BIGINT NOT NULL CHECK (unmapped_count >= 0),
    api_listable_count BIGINT NOT NULL CHECK (api_listable_count >= 0),
    map_visible_count BIGINT NOT NULL CHECK (map_visible_count >= 0),
    idempotent_replay BOOLEAN NOT NULL,
    public_rows BIGINT NOT NULL CHECK (public_rows = 0),
    runtime_details JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE OR REPLACE FUNCTION real_preview.reject_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'real preview evidence is append-only';
END;
$$;
CREATE INDEX IF NOT EXISTS real_preview_source_preview_latest_idx
    ON real_preview.source_preview_runs (source_id, created_at DESC, run_id);
CREATE TRIGGER real_preview_source_preview_runs_immutable
    BEFORE UPDATE OR DELETE ON real_preview.source_preview_runs
    FOR EACH ROW EXECUTE FUNCTION real_preview.reject_mutation();
