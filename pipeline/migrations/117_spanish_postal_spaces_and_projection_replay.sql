-- Normalize postal separators without rewriting source evidence, and allow
-- projection replay directly from immutable stored Geoapify results.
DO $migration$
DECLARE definition TEXT; marker TEXT; replacement TEXT;
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
                'vr','partida','pra','praza','pza',
                'calle','carrer','cl','c','avenida','avinguda','avda','av','carretera','ctra',
                'camino','cami','paseo','passeig','plaza','placa','pl',
                'nave','nau','local','piso','planta','puerta','baixos','bajo','bajos',
                'edificio','edifici','bloque','parcela','parc','plot','km','kilometro','kilometros']))),false)
    $function$;

    CREATE OR REPLACE FUNCTION real_preview.spanish_house_key(value TEXT)
    RETURNS TEXT LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $function$
        WITH input AS (SELECT lower(btrim(translate(value,chr(160)||chr(8239)||chr(8199),'   '))) AS v)
        SELECT CASE WHEN v ~ '^[0-9]+([ -]?[a-z])?(\s*[-/]\s*[0-9]+[a-z]?)?$'
            THEN regexp_replace(regexp_replace(v,'\s+','','g'),'([0-9])-([a-z])$','\1\2')
            ELSE '' END FROM input
    $function$;

    definition := pg_get_functiondef('real_preview.spanish_street_matches(text,text,text)'::regprocedure);
    marker := 'regexp_split_to_table(source,';
    IF position(marker IN definition)>0 THEN
        IF length(definition)-length(replace(definition,marker,''))<>length(marker) THEN
            RAISE EXCEPTION 'Spanish address split marker is not unique';
        END IF;
        EXECUTE replace(definition,marker,'regexp_split_to_table(translate(source,chr(160)||chr(8239)||chr(8199),''   ''),');
    END IF;
    definition := pg_get_functiondef('real_preview.guard_spanish_retained_replay()'::regprocedure);
    marker := '''spanish-address-format-v4''';
    IF position('''spanish-address-format-v5''' IN definition)=0 THEN
        IF length(definition)-length(replace(definition,marker,''))<>length(marker) THEN
            RAISE EXCEPTION 'Spanish replay ruleset marker is not unique';
        END IF;
        EXECUTE replace(definition,marker,'''spanish-address-format-v5''');
    END IF;

    IF to_regprocedure('real_preview.project_spain_geoapify_result(uuid)') IS NULL THEN
        -- Reuse the existing complete source/geometry/uniqueness checks. The
        -- operator supplies only an ID; all fields come from the stored row.
        definition := pg_get_functiondef('real_preview.capture_spain_geoapify_private_display()'::regprocedure);
        FOREACH marker IN ARRAY ARRAY[
            'real_preview.capture_spain_geoapify_private_display()', 'RETURNS trigger',
            'DECLARE payload JSONB;', E'BEGIN\n        IF NEW.provider_id'
        ] LOOP
            IF length(definition)-length(replace(definition,marker,''))<>length(marker) THEN
                RAISE EXCEPTION 'Spanish projection extraction marker is not unique';
            END IF;
            replacement := CASE marker
                WHEN 'real_preview.capture_spain_geoapify_private_display()'
                    THEN 'real_preview.project_spain_geoapify_result(result_id UUID)'
                WHEN 'RETURNS trigger' THEN 'RETURNS uec.geocode_results'
                WHEN 'DECLARE payload JSONB;' THEN 'DECLARE NEW uec.geocode_results; payload JSONB;'
                ELSE E'BEGIN\n        SELECT * INTO NEW FROM uec.geocode_results WHERE geocode_result_id=result_id;\n        IF NEW.provider_id'
            END;
            definition := replace(definition,marker,replacement);
        END LOOP;
        EXECUTE definition;
    END IF;

    CREATE OR REPLACE FUNCTION real_preview.capture_spain_geoapify_private_display()
    RETURNS trigger LANGUAGE plpgsql AS $function$
    BEGIN
        PERFORM real_preview.project_spain_geoapify_result(NEW.geocode_result_id);
        RETURN NEW;
    END
    $function$;
END
$migration$;
