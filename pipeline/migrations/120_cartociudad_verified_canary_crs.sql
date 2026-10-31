-- The downloaded Canary GeoPackages declare REGCAN95 geographic 2D EPSG:4081.
-- Keep source CRS explicit and transform it; never reinterpret it as EPSG:4326.
DO $migration$
DECLARE definition TEXT; marker TEXT; addition TEXT;
BEGIN
    IF to_regprocedure('real_preview.capture_cartociudad_local_portal()') IS NULL THEN RETURN; END IF;
    definition:=pg_get_functiondef('real_preview.capture_cartociudad_local_portal()'::regprocedure);
    IF position('''EPSG:8081''' IN definition)>0 THEN
        definition:=replace(replace(definition,'''EPSG:8081''','''EPSG:4081'''),
                            'native_srid:=8081','native_srid:=4081');
    END IF;
    marker:='    expected := ST_Transform';
    addition:=$guard$
    IF (native_srid=4081 AND (
            real_preview.spanish_province_key(selected->>'province') NOT IN ('laspalmas','santacruzdetenerife')
            OR (selected->>'longitude')::double precision NOT BETWEEN -19 AND -13
            OR (selected->>'latitude')::double precision NOT BETWEEN 27 AND 30))
       OR (native_srid=4258 AND real_preview.spanish_province_key(selected->>'province')
           IN ('laspalmas','santacruzdetenerife')) THEN RETURN NEW; END IF;
    $guard$;
    IF position('native_srid=4081 AND' IN definition)=0 THEN
        IF length(definition)-length(replace(definition,marker,''))<>length(marker) THEN
            RAISE EXCEPTION 'CartoCiudad CRS guard marker is not unique'; END IF;
        definition:=replace(definition,marker,addition||E'\n'||marker);
    END IF;
    EXECUTE definition;
END;
$migration$;
