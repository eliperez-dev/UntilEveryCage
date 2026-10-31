-- A missing road type is not a contradictory road type. Keep the exact name,
-- house, locality, province, postcode, uniqueness and confidence checks.
DO $migration$
DECLARE definition TEXT; marker TEXT; replacement TEXT; i INTEGER;
BEGIN
    IF to_regprocedure('real_preview.spanish_street_matches(text,text,text)') IS NULL THEN RETURN; END IF;

    CREATE OR REPLACE FUNCTION real_preview.spanish_road_keys_match(source_key TEXT, returned_key TEXT)
    RETURNS BOOLEAN LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $function$
        SELECT coalesce(nullif(source_key,'') IS NOT NULL AND (source_key=returned_key OR (
            split_part(returned_key,' ',1)=ANY(ARRAY['street','avenue','road','path','promenade','square'])
            AND source_key=substring(returned_key FROM position(' ' IN returned_key)+1)
            AND split_part(source_key,' ',1)<>ALL(ARRAY[
                'street','avenue','road','path','promenade','square',
                'cr','cm','ps','pz','tr','pj','pg','pol','poligono','poligon',
                'pasaje','travesia','ronda','rambla','urbanizacion','urb','plg',
                'lugar','lg','barrio','bo','poblado','pb','rua','estrada','ct',
                'glorieta','gta','rot','rotonda','prolongacion','prol','via','vial',
                'vr','partida','pra','praza','pza']))),false)
    $function$;

    definition := pg_get_functiondef('real_preview.spanish_street_matches(text,text,text)'::regprocedure);
    IF position('real_preview.spanish_road_keys_match' IN definition)=0 THEN
        FOREACH i IN ARRAY ARRAY[1,4] LOOP
            marker := format('real_preview.spanish_road_key(matched[%s])=wanted_road',i);
            replacement := format('real_preview.spanish_road_keys_match(real_preview.spanish_road_key(matched[%s]),wanted_road)',i);
            IF length(definition)-length(replace(definition,marker,''))<>length(marker) THEN
                RAISE EXCEPTION 'Spanish street comparator marker is not unique';
            END IF;
            definition := replace(definition,marker,replacement);
        END LOOP;
        EXECUTE definition;
    END IF;
    definition := pg_get_functiondef('real_preview.guard_spanish_retained_replay()'::regprocedure);
    marker := '''spanish-address-format-v3''';
    IF position('''spanish-address-format-v4''' IN definition)=0 THEN
        IF length(definition)-length(replace(definition,marker,''))<>length(marker) THEN
            RAISE EXCEPTION 'Spanish replay ruleset marker is not unique';
        END IF;
        EXECUTE replace(definition,marker,'''spanish-address-format-v4''');
    END IF;
END
$migration$;
