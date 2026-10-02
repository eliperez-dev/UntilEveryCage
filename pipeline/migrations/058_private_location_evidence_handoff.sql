-- Preserve source-owned facility location inputs in the private preview store.
-- This table is intentionally separate from map/API candidate projections.
CREATE TABLE real_preview.candidate_private_location_evidence (
    candidate_id UUID PRIMARY KEY REFERENCES real_preview.candidates(candidate_id),
    snapshot_sha256 CHAR(64) NOT NULL,
    source_id TEXT NOT NULL,
    location_evidence JSONB NOT NULL CHECK (jsonb_typeof(location_evidence) = 'object'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    FOREIGN KEY (snapshot_sha256, source_id, candidate_id)
        REFERENCES real_preview.candidates(snapshot_sha256, source_id, candidate_id),
    CHECK (location_evidence - ARRAY[
        'address','city','postal_code','region','country_code','coordinates',
        'municipality_code','comarca_code','department_number','region_code'
    ] = '{}'::jsonb),
    CHECK (NOT (location_evidence ? 'coordinates') OR
        (jsonb_typeof(location_evidence->'coordinates') = 'object' AND
         (location_evidence->'coordinates') - ARRAY['latitude','longitude','precision'] = '{}'::jsonb))
);

CREATE TRIGGER candidate_private_location_evidence_immutable
    BEFORE UPDATE OR DELETE ON real_preview.candidate_private_location_evidence
    FOR EACH ROW EXECUTE FUNCTION real_preview.reject_mutation();

COMMENT ON TABLE real_preview.candidate_private_location_evidence IS
    'Allow-listed facility address/locality/source-coordinate evidence retained for private enrichment; excluded from public release and map read models.';
