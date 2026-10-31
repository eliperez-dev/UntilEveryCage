-- Python now uses the existing SQL province keys for both orders of the
-- Alicante/Alacant and Castellon/Castello labels. No requests or rows replayed.
DO $migration$
DECLARE definition TEXT; marker TEXT := '''spanish-address-format-v5''';
BEGIN
    IF to_regprocedure('real_preview.guard_spanish_retained_replay()') IS NULL THEN RETURN; END IF;
    definition := pg_get_functiondef('real_preview.guard_spanish_retained_replay()'::regprocedure);
    IF position('''spanish-address-format-v6''' IN definition)=0 THEN
        IF length(definition)-length(replace(definition,marker,''))<>length(marker) THEN
            RAISE EXCEPTION 'Spanish replay ruleset marker is not unique'; END IF;
        EXECUTE replace(definition,marker,'''spanish-address-format-v6''');
    END IF;
END;
$migration$;
