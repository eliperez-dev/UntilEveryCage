-- Release-built, allowlisted detail is deliberately separate from raw evidence.
-- It is used only after the existing live release/review/suppression gates.
ALTER TABLE uec.public_discovery_read_model_rows
    ADD COLUMN public_detail JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN public_search_text TEXT NOT NULL DEFAULT '';

CREATE INDEX public_discovery_read_model_search_idx
    ON uec.public_discovery_read_model_rows USING GIN (public_search_text gin_trgm_ops);

CREATE OR REPLACE FUNCTION uec.public_discovery_detail_from_observation(observation JSONB)
RETURNS JSONB LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE
    names JSONB := '[]'::jsonb;
    volumes JSONB := '[]'::jsonb;
    detail JSONB;
    value JSONB;
BEGIN
    -- The observation is normalized input, but never returned wholesale.  Keep
    -- only the explicitly documented source-native fields; addresses, contacts,
    -- source_values, and every unknown key remain private.
    IF jsonb_typeof(observation->'alternate_names') = 'array' THEN
        names := observation->'alternate_names';
    ELSIF jsonb_typeof(observation->'dba_names') = 'array' THEN
        names := observation->'dba_names';
    ELSIF jsonb_typeof(observation->'dba_names') = 'string' AND btrim(observation->>'dba_names') <> '' THEN
        names := jsonb_build_array(observation->>'dba_names');
    ELSIF jsonb_typeof(observation->'dbas') = 'array' THEN
        names := observation->'dbas';
    END IF;
    IF jsonb_typeof(observation->'source_volume_categories') = 'array' THEN
        volumes := observation->'source_volume_categories';
    ELSIF jsonb_typeof(observation->'activity_volume_codes') = 'object' THEN
        SELECT COALESCE(jsonb_agg(jsonb_build_object('code', code,
            'provenance', jsonb_build_object('source_field', 'activity_volume_codes', 'method', 'source_native')) ORDER BY code), '[]'::jsonb)
          INTO volumes FROM jsonb_object_keys(observation->'activity_volume_codes') AS code;
    ELSIF jsonb_typeof(observation->'processing_volume_category') = 'string' THEN
        volumes := jsonb_build_array(jsonb_build_object('code', observation->>'processing_volume_category',
            'provenance', jsonb_build_object('source_field', 'processing_volume_category', 'method', 'source_native')));
    END IF;
    detail := jsonb_strip_nulls(jsonb_build_object(
        'alternate_names', names,
        'species_slaughtered', CASE WHEN jsonb_typeof(observation->'species_slaughtered')='object' THEN observation->'species_slaughtered' END,
        'processing_activities', CASE WHEN jsonb_typeof(observation->'processing_activities')='object' THEN observation->'processing_activities' END,
        'source_volume_categories', volumes,
        'establishment_id', observation->>'establishment_id',
        'establishment_number', observation->>'establishment_number',
        'grant_date', observation->>'grant_date',
        'native_activity_code', COALESCE(observation->>'activity_code', observation->>'source_activity_code'),
        'native_activity_label', COALESCE(observation->>'activity_label', observation->>'source_activity_label')
    ));
    -- Do not publish empty optional fields; an absent value means unknown.
    IF names = '[]'::jsonb THEN detail := detail - 'alternate_names'; END IF;
    IF volumes = '[]'::jsonb THEN detail := detail - 'source_volume_categories'; END IF;
    RETURN detail;
END;
$$;

COMMENT ON COLUMN uec.public_discovery_read_model_rows.public_detail IS
    'Release-built allowlisted native detail; excludes raw fields, contacts, and street addresses.';
COMMENT ON COLUMN uec.public_discovery_read_model_rows.public_search_text IS
    'Release-built allowlisted literal search text; existing immutable model rows retain an empty value and use the safe query fallback.';
