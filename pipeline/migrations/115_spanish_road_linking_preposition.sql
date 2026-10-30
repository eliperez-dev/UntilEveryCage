-- Match the optional linking preposition after an explicit Spanish road type.
-- House numbers, articles, locality and province checks remain unchanged.
DO $migration$
DECLARE definition TEXT; marker TEXT := '''spanish-address-format-v2''';
BEGIN
    IF to_regprocedure('real_preview.spanish_road_key(text)') IS NULL THEN RETURN; END IF;

    CREATE OR REPLACE FUNCTION real_preview.spanish_road_key(value TEXT)
    RETURNS TEXT LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $function$
        SELECT regexp_replace(
            regexp_replace(regexp_replace(regexp_replace(regexp_replace(regexp_replace(regexp_replace(
                real_preview.normalize_geocode_address(value),
                '^(calle|carrer|cl|c) ','street '),
                '^(avenida|avinguda|avda|av) ','avenue '),
                '^(carretera|ctra) ','road '),
                '^(camino|cami) ','path '),
                '^(paseo|passeig|pg) ','promenade '),
                '^(plaza|placa|pl) ','square '),
            '^(street|avenue|road|path|promenade|square) de ','\1 ')
    $function$;

    -- Existing v2 results remain immutable. New evaluations identify v3 so
    -- their deterministic IDs and recorded rule version reflect this change.
    definition := pg_get_functiondef('real_preview.guard_spanish_retained_replay()'::regprocedure);
    IF position('''spanish-address-format-v3''' IN definition)=0 THEN
        IF length(definition)-length(replace(definition,marker,''))<>length(marker) THEN
            RAISE EXCEPTION 'Spanish replay ruleset marker is not unique';
        END IF;
        EXECUTE replace(definition,marker,'''spanish-address-format-v3''');
    END IF;
END
$migration$;
