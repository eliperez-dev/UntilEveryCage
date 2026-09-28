-- Approved, offline administrative references used by the private preview.
ALTER TABLE real_preview.candidates
    ADD COLUMN IF NOT EXISTS municipality_code TEXT;

CREATE TABLE IF NOT EXISTS real_preview.local_admin_reference_points (
    country_code CHAR(2) NOT NULL,
    admin_code TEXT NOT NULL,
    admin_name TEXT NOT NULL,
    reference_latitude DOUBLE PRECISION NOT NULL CHECK (reference_latitude BETWEEN -90 AND 90),
    reference_longitude DOUBLE PRECISION NOT NULL CHECK (reference_longitude BETWEEN -180 AND 180),
    reference_precision TEXT NOT NULL CHECK (reference_precision = 'municipality_capital_locality'),
    reference_source_id TEXT NOT NULL,
    reference_source_url TEXT NOT NULL,
    source_dataset_date DATE NOT NULL,
    source_artifact_sha256 CHAR(64) NOT NULL CHECK (source_artifact_sha256 ~ '^[0-9a-f]{64}$'),
    normalized_reference_sha256 CHAR(64) NOT NULL CHECK (normalized_reference_sha256 ~ '^[0-9a-f]{64}$'),
    imported_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (country_code, admin_code, reference_source_id),
    CHECK (reference_latitude <> 0 OR reference_longitude <> 0)
);
CREATE TRIGGER real_preview_local_admin_reference_immutable
    BEFORE UPDATE OR DELETE ON real_preview.local_admin_reference_points
    FOR EACH ROW EXECUTE FUNCTION real_preview.reject_mutation();

COMMENT ON TABLE real_preview.local_admin_reference_points IS
    'Offline administrative locality reference points. These describe municipality capital localities, never facility locations.';
