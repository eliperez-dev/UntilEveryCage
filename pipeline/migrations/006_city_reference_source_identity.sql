ALTER TABLE uec.city_reference_points
    ADD COLUMN IF NOT EXISTS source_reference_id TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS city_reference_points_source_identity
    ON uec.city_reference_points (reference_source, source_reference_id)
    WHERE source_reference_id IS NOT NULL;
