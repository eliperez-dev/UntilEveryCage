-- Spanish formatting recovery is local and append-only. Original responses,
-- provider request accounting, source records and public releases stay intact.
DO $migration$
DECLARE definition TEXT; marker TEXT;
BEGIN
    IF to_regprocedure('real_preview.locationiq_first_pass_address_matches(jsonb,text,text,text,text,text)') IS NULL
       OR to_regprocedure('real_preview.capture_locationiq_first_pass_private_display()') IS NULL THEN
        RETURN;
    END IF;

    CREATE OR REPLACE FUNCTION real_preview.spanish_province_key(value TEXT)
    RETURNS TEXT LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $function$
        WITH folded AS (SELECT replace(regexp_replace(
            real_preview.normalize_geocode_address(value),'^provincia de ',''),' ','') AS k)
        SELECT CASE
            WHEN k IN ('coruna','lacoruna','corunaa') THEN 'acoruna'
            WHEN k IN ('araba','arabaalava') THEN 'alava'
            WHEN k='vizcaya' THEN 'bizkaia'
            WHEN k='guipuzcoa' THEN 'gipuzkoa'
            WHEN k='girona' THEN 'gerona'
            WHEN k='lleida' THEN 'lerida'
            WHEN k IN ('illesbalears','islasbaleares') THEN 'baleares'
            WHEN k IN ('alicante','alacant','alicantealacant') THEN 'alacantalicante'
            WHEN k IN ('castellon','castello','castelloncastello') THEN 'castellocastellon'
            WHEN k='valenciavalencia' THEN 'valencia'
            WHEN k='ourense' THEN 'orense'
            WHEN k='riojala' THEN 'larioja'
            WHEN k='palmaslas' THEN 'laspalmas'
            WHEN k='navarra' THEN 'comunidadforaldenavarra'
            WHEN k='comunidaddemadrid' THEN 'madrid'
            WHEN k='principadodeasturias' THEN 'asturias'
            WHEN k='regiondemurcia' THEN 'murcia'
            ELSE k END FROM folded
    $function$;

    -- Membership checked against the retained IGN 2026 PROVINCIAS.csv.
    CREATE OR REPLACE FUNCTION real_preview.spanish_region_members(value TEXT)
    RETURNS TEXT[] LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $function$
        WITH folded AS (SELECT real_preview.spanish_province_key(value) AS k)
        SELECT CASE
            WHEN k=ANY(ARRAY['andalucia','andalusia','an']) THEN ARRAY['almeria','cadiz','cordoba','granada','huelva','jaen','malaga','sevilla']
            WHEN k=ANY(ARRAY['aragon','ar']) THEN ARRAY['huesca','teruel','zaragoza']
            WHEN k=ANY(ARRAY['canarias','canaryislands','cn']) THEN ARRAY['laspalmas','santacruzdetenerife']
            WHEN k=ANY(ARRAY['cantabria','cb']) THEN ARRAY['cantabria']
            WHEN k=ANY(ARRAY['castillalamancha','castilelamancha','cm']) THEN ARRAY['albacete','ciudadreal','cuenca','guadalajara','toledo']
            WHEN k=ANY(ARRAY['castillayleon','castileandleon','cl']) THEN ARRAY['avila','burgos','leon','palencia','salamanca','segovia','soria','valladolid','zamora']
            WHEN k=ANY(ARRAY['cataluna','catalunya','catalunacatalunya','catalonia','ct']) THEN ARRAY['barcelona','gerona','lerida','tarragona']
            WHEN k=ANY(ARRAY['ciudadautonomadeceuta','ceuta','ce']) THEN ARRAY['ceuta']
            WHEN k=ANY(ARRAY['ciudadautonomademelilla','melilla','ml']) THEN ARRAY['melilla']
            WHEN k=ANY(ARRAY['madrid','communityofmadrid','md']) THEN ARRAY['madrid']
            WHEN k=ANY(ARRAY['comunidadforaldenavarra','navarre','nc']) THEN ARRAY['comunidadforaldenavarra']
            WHEN k=ANY(ARRAY['comunitatvalenciana','comunidadvalenciana','valenciancommunity','vc']) THEN ARRAY['alacantalicante','castellocastellon','valencia']
            WHEN k=ANY(ARRAY['extremadura','ex']) THEN ARRAY['badajoz','caceres']
            WHEN k=ANY(ARRAY['galicia','ga']) THEN ARRAY['acoruna','lugo','orense','pontevedra']
            WHEN k=ANY(ARRAY['baleares','balearicislands','ib']) THEN ARRAY['baleares']
            WHEN k=ANY(ARRAY['larioja','ri']) THEN ARRAY['larioja']
            WHEN k=ANY(ARRAY['paisvasco','euskadi','paisvascoeuskadi','basquecountry','pv']) THEN ARRAY['alava','gipuzkoa','bizkaia']
            WHEN k=ANY(ARRAY['asturias','as']) THEN ARRAY['asturias']
            WHEN k=ANY(ARRAY['murcia','mc']) THEN ARRAY['murcia']
            ELSE NULL::TEXT[] END FROM folded
    $function$;

    CREATE OR REPLACE FUNCTION real_preview.spanish_admin_matches(address JSONB, region TEXT)
    RETURNS BOOLEAN LANGUAGE plpgsql IMMUTABLE AS $function$
    DECLARE wanted TEXT[]; members TEXT[]; field TEXT; has_state BOOLEAN := false;
    BEGIN
        IF nullif(btrim(region),'') IS NULL THEN RETURN true; END IF;
        wanted := coalesce(real_preview.spanish_region_members(region),
                           ARRAY[real_preview.spanish_province_key(region)]);
        FOREACH field IN ARRAY ARRAY['state','state_code'] LOOP
            members := real_preview.spanish_region_members(address->>field);
            IF members IS NOT NULL THEN
                IF NOT wanted && members THEN RETURN false; END IF;
                has_state := true;
            END IF;
        END LOOP;
        IF nullif(address->>'province','') IS NOT NULL THEN
            RETURN real_preview.spanish_province_key(address->>'province')=ANY(wanted);
        END IF;
        FOREACH field IN ARRAY ARRAY['state','state_code','county','state_district'] LOOP
            IF real_preview.spanish_province_key(address->>field)=ANY(wanted) THEN RETURN true; END IF;
        END LOOP;
        RETURN has_state;
    END
    $function$;

    CREATE OR REPLACE FUNCTION real_preview.spanish_road_key(value TEXT)
    RETURNS TEXT LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $function$
        SELECT regexp_replace(regexp_replace(regexp_replace(regexp_replace(regexp_replace(regexp_replace(
            real_preview.normalize_geocode_address(value),
            '^(calle|carrer|cl|c) ','street '),
            '^(avenida|avinguda|avda|av) ','avenue '),
            '^(carretera|ctra) ','road '),
            '^(camino|cami) ','path '),
            '^(paseo|passeig|pg) ','promenade '),
            '^(plaza|placa|pl) ','square ')
    $function$;

    CREATE OR REPLACE FUNCTION real_preview.spanish_house_key(value TEXT)
    RETURNS TEXT LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $function$
        SELECT CASE WHEN lower(btrim(value)) ~ '^[0-9]+([ -]?[a-z])?(\s*[-/]\s*[0-9]+[a-z]?)?$'
            THEN regexp_replace(regexp_replace(lower(btrim(value)),'\s+','','g'),'([0-9])-([a-z])$','\1\2')
            ELSE '' END
    $function$;

    CREATE OR REPLACE FUNCTION real_preview.spanish_street_matches(source TEXT, road TEXT, house TEXT)
    RETURNS BOOLEAN LANGUAGE plpgsql IMMUTABLE AS $function$
    DECLARE parts TEXT[]; part TEXT; normalized TEXT; matched TEXT[]; i INTEGER;
        wanted_road TEXT := real_preview.spanish_road_key(road);
        wanted_house TEXT := real_preview.spanish_house_key(house);
        house_pattern TEXT := '[0-9]+([ -]?[a-z])?(\s*[-/]\s*[0-9]+[a-z]?)?';
    BEGIN
        IF nullif(wanted_road,'') IS NULL OR nullif(wanted_house,'') IS NULL
           OR nullif(btrim(source),'') IS NULL OR length(source)>1200 THEN RETURN false; END IF;
        SELECT array_agg(lower(btrim(fragment))) INTO parts
            FROM regexp_split_to_table(source,'[,;]') fragment WHERE btrim(fragment)<>'';
        IF parts IS NULL THEN RETURN false; END IF;
        FOR i IN 1..array_length(parts,1)-1 LOOP
            parts := array_append(parts,parts[i]||' '||parts[i+1]);
        END LOOP;
        FOREACH part IN ARRAY parts LOOP
            -- Only drop a labeled sub-building unit, not a second street.
            normalized := regexp_replace(part,
                '\s+(nave|nau|local|piso|planta|puerta|baixos|bajo|bajos|edificio|edifici|bloque)\y(?!.*\y(calle|carrer|avenida|avinguda|carretera)\y).*$', '');
            matched := regexp_match(normalized,
                '^(.+?)\s+(?:n[úu]m(?:ero)?\.?\s*|n[ºo°]\s*)?('||house_pattern||')$');
            IF matched IS NOT NULL THEN
                IF real_preview.spanish_road_key(matched[1])=wanted_road
                   AND real_preview.spanish_house_key(matched[2])=wanted_house THEN RETURN true; END IF;
            ELSE
                matched := regexp_match(normalized,'^('||house_pattern||')\s+(.+)$');
                IF matched IS NOT NULL AND real_preview.spanish_house_key(matched[1])=wanted_house
                   AND real_preview.spanish_road_key(matched[4])=wanted_road THEN RETURN true; END IF;
            END IF;
        END LOOP;
        RETURN false;
    END
    $function$;

    CREATE OR REPLACE FUNCTION real_preview.spanish_locality_key(value TEXT)
    RETURNS TEXT LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $function$
        SELECT real_preview.normalize_geocode_address(regexp_replace(btrim(value),
            '(?i)^(.+?)(?:,\s*|\s*\(\s*)(el|la|los|las|els|les|l'')\s*\)?$', '\2 \1'))
    $function$;

    -- Reuse the existing coordinate/type/country checks, replacing only the
    -- Spanish formatting comparisons. GB/NZ continue through their old branch.
    definition := pg_get_functiondef('real_preview.locationiq_first_pass_address_matches(jsonb,text,text,text,text,text)'::regprocedure);
    marker := '        IF viable_fragments <> 1 THEN RETURN false; END IF;';
    IF length(definition)-length(replace(definition,marker,'')) <> length(marker) THEN
        RAISE EXCEPTION 'Spanish street guard marker is not unique';
    END IF;
    definition := replace(definition,marker,$guard$
        IF country_code='ES' THEN
            IF NOT real_preview.spanish_street_matches(source_address,result_address->>'road',result_address->>'house_number')
            THEN RETURN false; END IF;
        ELSIF viable_fragments <> 1 THEN RETURN false; END IF;$guard$);
    marker := '        IF NOT result_locality_match THEN RETURN false; END IF;';
    IF length(definition)-length(replace(definition,marker,'')) <> length(marker) THEN
        RAISE EXCEPTION 'Spanish locality guard marker is not unique';
    END IF;
    definition := replace(definition,marker,$guard$
        IF country_code='ES' THEN
            SELECT coalesce(bool_or(real_preview.spanish_locality_key(source_locality)
                =real_preview.spanish_locality_key(result_address->>field)),false)
                INTO result_locality_match FROM unnest(ARRAY['city','town','municipality','village','suburb']) field
                WHERE nullif(result_address->>field,'') IS NOT NULL;
        END IF;
        IF NOT result_locality_match THEN RETURN false; END IF;$guard$);
    marker := '        RETURN result_postcode_match AND result_region_match;';
    IF length(definition)-length(replace(definition,marker,'')) <> length(marker) THEN
        RAISE EXCEPTION 'Spanish region guard marker is not unique';
    END IF;
    EXECUTE replace(definition,marker,$guard$
        IF country_code='ES' THEN result_region_match := real_preview.spanish_admin_matches(result_address,source_region); END IF;
        RETURN result_postcode_match AND result_region_match;$guard$);

    CREATE OR REPLACE FUNCTION real_preview.guard_spanish_retained_replay()
    RETURNS trigger LANGUAGE plpgsql AS $function$
    BEGIN
        IF NEW.match_method IS DISTINCT FROM 'locationiq_spanish_replay_v1' THEN RETURN NEW; END IF;
        IF NEW.provider_id<>'locationiq' OR NEW.status<>'accepted'
           OR NEW.precision<>'locationiq_address_point' OR NEW.result IS NULL
           OR NEW.retryable OR NEW.response->>'_uec_ruleset_version' IS DISTINCT FROM 'spanish-address-format-v2'
           OR coalesce(NEW.response->>'_uec_selected_result_index','') !~ '^[01]$'
           OR NOT EXISTS (SELECT 1 FROM uec.geocode_results parent
               WHERE parent.geocode_result_id::TEXT=NEW.response->>'_uec_parent_geocode_result_id'
                 AND parent.provider_id='locationiq' AND parent.status='review_required'
                 AND parent.match_method='locationiq_forward'
                 AND parent.source_record_id=NEW.source_record_id AND parent.query=NEW.query
                 AND parent.attempt_number=NEW.attempt_number AND parent.queried_at=NEW.queried_at
                 AND parent.response->'results'=NEW.response->'results'
                 AND EXISTS (SELECT 1 FROM uec.geocode_jobs job
                     JOIN real_preview.geocode_targets target USING(job_id)
                     WHERE job.source_record_id=parent.source_record_id AND job.query=parent.query
                       AND job.provider_id=parent.provider_id
                       AND target.source_id IN ('es.locations','es.cat.feed-sandach')))
        THEN RAISE EXCEPTION 'Spanish retained replay lacks unchanged parent evidence' USING ERRCODE='23514'; END IF;
        RETURN NEW;
    END
    $function$;
    CREATE TRIGGER geocode_results_spanish_retained_guard BEFORE INSERT ON uec.geocode_results
        FOR EACH ROW EXECUTE FUNCTION real_preview.guard_spanish_retained_replay();

    definition := pg_get_functiondef('real_preview.capture_locationiq_first_pass_private_display()'::regprocedure);
    marker := 'NEW.match_method <> ''locationiq_forward''';
    IF length(definition)-length(replace(definition,marker,'')) <> length(marker) THEN
        RAISE EXCEPTION 'Spanish retained replay capture marker is not unique';
    END IF;
    EXECUTE replace(definition,marker,'NEW.match_method NOT IN (''locationiq_forward'',''locationiq_spanish_replay_v1'')');
END
$migration$;
