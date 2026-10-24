-- Placeholder or malformed Italian VAT-shaped identifiers are not public
-- business identifiers. This does not mutate source identifiers or edges;
-- it only gates new/public organization qualification.
CREATE FUNCTION uec.is_valid_italian_vat_identifier(
    source_id TEXT, identifier_type TEXT, source_identifier TEXT
) RETURNS BOOLEAN
LANGUAGE sql IMMUTABLE PARALLEL SAFE
SET search_path=pg_catalog,uec AS $$
    WITH normalized AS (
        SELECT regexp_replace(
                 regexp_replace(upper(coalesce(source_identifier,'')), '[[:space:]]', '', 'g'),
                 '^IT', ''
               ) AS vat
    )
    SELECT CASE
      WHEN lower(coalesce(source_id,'')) LIKE 'it.%'
       AND lower(coalesce(identifier_type,'')) IN (
           'italian_vat','it.tax-authority.vat','vat','vat_number','p_iva'
       )
      THEN vat ~ '^[0-9]{11}$'
       AND vat <> repeat(substr(vat,1,1),11)
      ELSE true
    END
    FROM normalized
$$;
REVOKE ALL ON FUNCTION uec.is_valid_italian_vat_identifier(TEXT,TEXT,TEXT) FROM PUBLIC;
COMMENT ON FUNCTION uec.is_valid_italian_vat_identifier(TEXT,TEXT,TEXT) IS
    'Public qualification guard only: Italian VAT types are whitespace/optional-IT normalized and must be 11 digits, not a repeated-digit placeholder. Does not alter private IDs or edges.';

-- Existing v3 builds predate the private VAT qualification guard. Retire them
-- and advance generation so they cannot be served or packaged before a new
-- filtered build runs. Native identifiers remain private to the build query.
UPDATE uec.graph_public_projection_builds SET active=false WHERE active;
UPDATE uec.graph_projection_generation
   SET generation=generation+1
 WHERE singleton=true;

DO $$
DECLARE role_row RECORD;
BEGIN
    FOR role_row IN SELECT rolname FROM pg_roles WHERE left(rolname,17)='uec_graph_writer_' LOOP
        EXECUTE format(
            'GRANT EXECUTE ON FUNCTION uec.is_valid_italian_vat_identifier(text,text,text) TO %I',
            role_row.rolname
        );
    END LOOP;
END
$$;
