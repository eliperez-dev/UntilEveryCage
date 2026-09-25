-- Local reference-derived display points are append-only and remain coarse.
CREATE TABLE real_preview.local_reference_display_evidence (
    evidence_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id UUID NOT NULL REFERENCES real_preview.candidates(candidate_id),
    snapshot_sha256 CHAR(64) NOT NULL,
    source_id TEXT NOT NULL,
    reference_latitude DOUBLE PRECISION NOT NULL CHECK (reference_latitude BETWEEN -90 AND 90),
    reference_longitude DOUBLE PRECISION NOT NULL CHECK (reference_longitude BETWEEN -180 AND 180),
    display_precision TEXT NOT NULL CHECK (display_precision = 'locality_reference_coarse'),
    display_geometry_source TEXT NOT NULL,
    reference_source_id TEXT NOT NULL,
    reference_source TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (reference_latitude <> 0 OR reference_longitude <> 0),
    UNIQUE (candidate_id, reference_source_id),
    FOREIGN KEY (snapshot_sha256) REFERENCES real_preview.imports(snapshot_sha256)
);
CREATE INDEX real_preview_local_reference_display_latest_idx
    ON real_preview.local_reference_display_evidence(candidate_id, created_at DESC, evidence_id DESC);
CREATE TRIGGER real_preview_local_reference_display_immutable
    BEFORE UPDATE OR DELETE ON real_preview.local_reference_display_evidence
    FOR EACH ROW EXECUTE FUNCTION real_preview.reject_mutation();

-- The candidate columns are a compatibility cache for the private preview
-- API. Permit only a value copied from its immutable local evidence row.
CREATE OR REPLACE FUNCTION real_preview.reject_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_TABLE_SCHEMA = 'real_preview' AND TG_TABLE_NAME = 'candidates'
       AND TG_OP = 'UPDATE'
       AND (to_jsonb(OLD) - ARRAY['display_latitude','display_longitude','display_geometry_source'])
           = (to_jsonb(NEW) - ARRAY['display_latitude','display_longitude','display_geometry_source'])
       AND EXISTS (
           SELECT 1 FROM real_preview.local_reference_display_evidence evidence
           WHERE evidence.candidate_id = NEW.candidate_id
             AND evidence.reference_latitude = NEW.display_latitude
             AND evidence.reference_longitude = NEW.display_longitude
             AND evidence.display_geometry_source = NEW.display_geometry_source
       ) THEN
        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'real preview evidence is append-only';
END;
$$;

CREATE FUNCTION real_preview.sync_local_reference_display()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    UPDATE real_preview.candidates
       SET display_latitude = NEW.reference_latitude,
           display_longitude = NEW.reference_longitude,
           display_geometry_source = NEW.display_geometry_source
     WHERE candidate_id = NEW.candidate_id;
    RETURN NEW;
END;
$$;
CREATE TRIGGER real_preview_local_reference_display_sync
    AFTER INSERT ON real_preview.local_reference_display_evidence
    FOR EACH ROW EXECUTE FUNCTION real_preview.sync_local_reference_display();

CREATE OR REPLACE VIEW real_preview.candidate_display AS
SELECT candidate.candidate_id, candidate.snapshot_sha256, candidate.source_id,
       candidate.location_class, candidate.country_code, candidate.city,
       candidate.postal_code, candidate.latitude, candidate.longitude,
       candidate.coordinate_precision,
       COALESCE(reference.reference_latitude, candidate.display_latitude) AS display_latitude,
       COALESCE(reference.reference_longitude, candidate.display_longitude) AS display_longitude,
       COALESCE(reference.display_geometry_source, candidate.display_geometry_source) AS display_geometry_source
FROM real_preview.candidates candidate
LEFT JOIN LATERAL (
    SELECT reference_latitude, reference_longitude, display_geometry_source
    FROM real_preview.local_reference_display_evidence
    WHERE candidate_id = candidate.candidate_id
    ORDER BY created_at DESC, evidence_id DESC LIMIT 1
) reference ON true;

COMMENT ON TABLE real_preview.local_reference_display_evidence IS
    'Private, approximate display geometry derived from a source-owned local reference dataset; not a facility point or publication authorization.';
