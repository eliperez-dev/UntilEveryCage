-- Nominatim place/house represents an address node, not a locality centroid.
-- Preserve all other component, country and uniqueness checks in migration102.
CREATE OR REPLACE FUNCTION real_preview.locationiq_new_zealand_address_matches(
    item JSONB, source_address TEXT, postcode TEXT, town TEXT)
RETURNS BOOLEAN LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE
    address JSONB := item->'address';
    latitude DOUBLE PRECISION;
    longitude DOUBLE PRECISION;
    road TEXT;
    house TEXT;
    result_locality_match BOOLEAN;
BEGIN
    IF jsonb_typeof(item) IS DISTINCT FROM 'object'
       OR jsonb_typeof(address) IS DISTINCT FROM 'object'
       OR jsonb_typeof(item->'lat') IS DISTINCT FROM 'string'
       OR jsonb_typeof(item->'lon') IS DISTINCT FROM 'string'
       OR lower(coalesce(address->>'country_code','')) <> 'nz'
       OR nullif(trim(source_address),'') IS NULL
       OR nullif(trim(town),'') IS NULL
       OR nullif(trim(address->>'road'),'') IS NULL
       OR nullif(trim(address->>'house_number'),'') IS NULL
       OR (item->>'class' IN ('highway','boundary','place','landuse')
           AND NOT (item->>'class'='place' AND item->>'type'='house'
                    AND COALESCE(item->>'addresstype','') IN ('','house','building')))
       OR item->>'type'='houses' OR item->>'addresstype'='houses'
       OR item->>'addresstype' IN ('road','city','town','village','municipality','postcode')
       OR item->>'type' IN ('road','city','town','village','municipality','postcode')
       OR (nullif(trim(postcode),'') IS NOT NULL
           AND coalesce(address->>'postcode','') <> trim(postcode))
    THEN RETURN false; END IF;
    BEGIN
        latitude := (item->>'lat')::DOUBLE PRECISION;
        longitude := (item->>'lon')::DOUBLE PRECISION;
    EXCEPTION WHEN invalid_text_representation OR numeric_value_out_of_range THEN
        RETURN false;
    END;
    -- Continental North and South Islands only; exclude offshore islands.
    IF NOT (latitude BETWEEN -47.5 AND -34.0 AND longitude BETWEEN 166 AND 179.9) THEN
        RETURN false;
    END IF;
    road := real_preview.normalize_new_zealand_geocode_text(address->>'road');
    house := real_preview.normalize_new_zealand_geocode_text(address->>'house_number');
    result_locality_match :=
        real_preview.normalize_new_zealand_geocode_text(town) IN (
            real_preview.normalize_new_zealand_geocode_text(address->>'city'),
            real_preview.normalize_new_zealand_geocode_text(address->>'town'),
            real_preview.normalize_new_zealand_geocode_text(address->>'municipality'),
            real_preview.normalize_new_zealand_geocode_text(address->>'village'),
            real_preview.normalize_new_zealand_geocode_text(address->>'suburb'));
    IF real_preview.normalize_new_zealand_geocode_text(source_address)
           NOT IN (road || ' ' || house,house || ' ' || road)
       OR NOT result_locality_match
    THEN RETURN false; END IF;
    RETURN true;
END;
$$;
