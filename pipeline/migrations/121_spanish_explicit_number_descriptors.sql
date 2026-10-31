-- Match explicit source house markers before labeled estate/building details.
-- Preserve source strings, range/suffix semantics and independent SQL checks.
DO $migration$
DECLARE definition TEXT; marker TEXT; addition TEXT;
BEGIN
    IF to_regprocedure('real_preview.spanish_street_matches(text,text,text)') IS NULL THEN RETURN; END IF;
    CREATE OR REPLACE FUNCTION real_preview.spanish_explicit_number_matches(source TEXT, road TEXT, house TEXT)
    RETURNS BOOLEAN LANGUAGE plpgsql IMMUTABLE AS $function$
    DECLARE pieces TEXT[]; part TEXT; m TEXT[]; key TEXT; i INTEGER;
        descriptors TEXT := '(?:p\.?\s*i\.?\y|pol\.?\y|pol[ií]gono\y|pol[ií]gon\y|(?:nave|nau|local|piso|planta|puerta|baixos|bajo|bajos|edificio|edifici|bloque)\y|bj\y|[0-9]+[ºª°]\s*(?:piso|planta)\y)';
        pattern TEXT := '^(.+?)\s+(?:n[º°o]\s*|n[uú]m(?:ero)?\.?\s*:?\s*)([0-9]+(?:[ -]?[a-z])?(?:\s*[-/]\s*[0-9]+[a-z]?)?)(\s+';
    BEGIN
        IF nullif(btrim(source),'') IS NULL OR length(source)>1200
           OR lower(source) ~ '\y(?:s\s*[/.-]\s*n|sin\s+n[uú]mero)\y' THEN RETURN false; END IF;
        SELECT array_agg(lower(btrim(v))) INTO pieces FROM regexp_split_to_table(
            translate(source,chr(160)||chr(8239)||chr(8199),'   '),'[,;]') v WHERE btrim(v)<>'';
        IF pieces IS NULL THEN RETURN false; END IF;
        FOR i IN 1..array_length(pieces,1)-1 LOOP
            pieces:=array_append(pieces,pieces[i]||' '||pieces[i+1]);
        END LOOP;
        FOREACH part IN ARRAY pieces LOOP
            m:=regexp_match(part,pattern||descriptors||'.*)?$');
            IF m IS NULL THEN CONTINUE; END IF;
            IF m[1] ~ '(?:n[º°o]|n[uú]m(?:ero)?\.?)\s*:?\s*[0-9]|[0-9]+[ºª°]\s*(?:piso|planta)\y' THEN CONTINUE; END IF;
            key:=real_preview.spanish_road_key(m[1]);
            IF NOT (split_part(key,' ',1)=ANY(ARRAY['street','avenue','road','path','promenade','square'])
                OR real_preview.spanish_road_keys_match(key,'street '||key)) THEN CONTINUE; END IF;
            IF m[1] ~ '^p\.?\s*i\y' THEN CONTINUE; END IF;
            IF coalesce(m[3],'') ~ '\y(?:calle|carrer|cl|avenida|avinguda|avda|av|carretera|ctra|camino|cami|paseo|passeig|plaza|placa)\y|c/' THEN CONTINUE; END IF;
            IF real_preview.spanish_road_keys_match(key,real_preview.spanish_road_key(road))
               AND nullif(real_preview.spanish_house_key(house),'') IS NOT NULL
               AND real_preview.spanish_house_key(m[2])=real_preview.spanish_house_key(house) THEN RETURN true; END IF;
        END LOOP;
        RETURN false;
    END
    $function$;
    definition:=pg_get_functiondef('real_preview.spanish_street_matches(text,text,text)'::regprocedure);
    IF position('spanish_explicit_number_matches' IN definition)=0 THEN
        marker:='        FOREACH part IN ARRAY parts LOOP';
        addition:=E'        IF real_preview.spanish_explicit_number_matches(source,road,house) THEN RETURN true; END IF;\n';
        IF length(definition)-length(replace(definition,marker,''))<>length(marker) THEN
            RAISE EXCEPTION 'Spanish explicit-number insertion marker is not unique'; END IF;
        EXECUTE replace(definition,marker,addition||marker);
    END IF;
    definition:=pg_get_functiondef('real_preview.guard_spanish_retained_replay()'::regprocedure);
    IF position('''spanish-address-format-v7''' IN definition)=0 THEN
        marker:='''spanish-address-format-v6''';
        IF length(definition)-length(replace(definition,marker,''))<>length(marker) THEN
            RAISE EXCEPTION 'Spanish explicit-number replay marker is not unique'; END IF;
        EXECUTE replace(definition,marker,'''spanish-address-format-v7''');
    END IF;
END;
$migration$;
