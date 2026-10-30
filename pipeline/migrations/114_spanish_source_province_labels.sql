-- Keep SQL aligned with the explicit AESAN province-field label crosswalk.
DO $migration$
DECLARE definition TEXT; marker TEXT := '            ELSE k END FROM folded';
BEGIN
    IF to_regprocedure('real_preview.spanish_province_key(text)') IS NULL THEN RETURN; END IF;
    definition := pg_get_functiondef('real_preview.spanish_province_key(text)'::regprocedure);
    IF position('WHEN k=''bilbao''' IN definition)=0 THEN
        IF length(definition)-length(replace(definition,marker,''))<>length(marker) THEN
            RAISE EXCEPTION 'Spanish province label marker is not unique';
        END IF;
        EXECUTE replace(definition,marker,
            '            WHEN k=''bilbao'' THEN ''bizkaia''' || E'\n' ||
            '            WHEN k=''palmademallorca'' THEN ''baleares''' || E'\n' || marker);
    END IF;
END
$migration$;
