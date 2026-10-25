-- Fix operator precedence in the Spain-only display bridge added by 090.
-- Resolve and replace only the private ES function; the historical shared
-- country handler and its trigger remain untouched.
DO $migration$
DECLARE
    definition TEXT;
BEGIN
    IF to_regnamespace('real_preview') IS NULL
       OR to_regprocedure('real_preview.capture_spain_geoapify_private_display()') IS NULL THEN
        RETURN;
    END IF;

    SELECT pg_get_functiondef('real_preview.capture_spain_geoapify_private_display()'::regprocedure)
      INTO definition;

    definition := replace(
        definition,
        $old$THEN properties->>'housenumber' || ' ' || properties->>'street' END$old$,
        $new$THEN (properties->>'housenumber') || ' ' || (properties->>'street') END$new$);
    definition := replace(
        definition,
        $old$THEN feature->'properties'->>'housenumber' || ' ' || feature->'properties'->>'street' END$old$,
        $new$THEN (feature->'properties'->>'housenumber') || ' ' || (feature->'properties'->>'street') END$new$);

    IF position($old$THEN properties->>'housenumber' || ' ' || properties->>'street' END$old$ IN definition) > 0
       OR position($old$THEN feature->'properties'->>'housenumber' || ' ' || feature->'properties'->>'street' END$old$ IN definition) > 0 THEN
        RAISE EXCEPTION 'Spain address-expression correction did not apply';
    END IF;

    EXECUTE definition;
END
$migration$;
