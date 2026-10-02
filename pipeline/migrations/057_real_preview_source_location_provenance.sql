-- Preserve normalized facility-location evidence in the private preview.
-- Address text is retained only for source-owned facility addresses and is
-- never included in map tiles or public/release projections.
ALTER TABLE real_preview.candidates
    ADD COLUMN facility_address TEXT,
    ADD COLUMN coordinate_method TEXT,
    ADD COLUMN coordinate_provider TEXT,
    ADD COLUMN coordinate_confidence DOUBLE PRECISION,
    ADD COLUMN coordinate_confidence_band TEXT;

ALTER TABLE real_preview.candidates
    ADD CONSTRAINT real_preview_location_provenance_lengths
        CHECK ((facility_address IS NULL OR length(facility_address) <= 500)
           AND (coordinate_method IS NULL OR length(coordinate_method) <= 80)
           AND (coordinate_provider IS NULL OR length(coordinate_provider) <= 160)
           AND (coordinate_confidence IS NULL OR coordinate_confidence BETWEEN 0 AND 1)
           AND (coordinate_confidence_band IS NULL OR coordinate_confidence_band IN ('high','medium','low')));

COMMENT ON COLUMN real_preview.candidates.facility_address IS
    'Allowlisted source-owned facility-location address for private later enrichment; excluded from map projection and publication.';
COMMENT ON COLUMN real_preview.candidates.coordinate_method IS
    'Location acquisition method, such as source_coordinate or address_geocode.';
COMMENT ON COLUMN real_preview.candidates.coordinate_provider IS
    'Source or geocoding provider supplying the candidate location.';
COMMENT ON COLUMN real_preview.candidates.coordinate_confidence IS
    'Optional provider-supplied or explicitly calibrated confidence score; NULL when not supplied.';
COMMENT ON COLUMN real_preview.candidates.coordinate_confidence_band IS
    'Qualitative confidence band with method/provider provenance; does not imply positional precision.';
