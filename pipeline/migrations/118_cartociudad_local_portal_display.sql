-- Local CartoCiudad portal joins are address geocodes, never source facility
-- coordinates. Original source rows, external quotas and releases are unchanged.
CREATE OR REPLACE FUNCTION real_preview.capture_cartociudad_local_portal()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE selected JSONB; archive JSONB; source_query JSONB; native_srid INTEGER;
        expected GEOMETRY; target RECORD; geometry_source TEXT;
BEGIN
    IF NEW.provider_id<>'cartociudad_local' THEN RETURN NEW; END IF;
    IF NEW.status IS DISTINCT FROM 'accepted' OR NEW.match_method IS DISTINCT FROM 'cartociudad_local_portal_v1'
       OR NEW.precision IS DISTINCT FROM 'government_reference_address_point' OR NEW.result IS NULL
       OR NEW.response->>'ruleset' IS DISTINCT FROM 'cartociudad-local-portal-v1'
       OR NEW.response->>'unique_reference_count' IS DISTINCT FROM '1' THEN RETURN NEW; END IF;
    selected := NEW.response->'selected'; archive := NEW.response->'archive';
    IF selected->>'point_kind' IS DISTINCT FROM 'portal'
       OR jsonb_typeof(selected->'reference_id') IS DISTINCT FROM 'array' THEN RETURN NEW; END IF;
    IF jsonb_array_length(selected->'reference_id')<>2
       OR selected->'reference_id'->>0 IS DISTINCT FROM 'ES.SCNE.CARTOCIUDAD'
       OR nullif(selected->'reference_id'->>1,'') IS NULL
       OR coalesce(archive->>'archive_sha256','') !~ '^[a-f0-9]{64}$'
       OR coalesce(archive->>'source_url','') !~ '^https://centrodedescargas[.]cnig[.]es/CentroDescargas/detalleArchivo[?]sec=[0-9]+$'
       OR archive->>'facility_addresses_sent' IS DISTINCT FROM 'false' THEN RETURN NEW; END IF;
    IF selected->>'crs'='EPSG:4258' THEN native_srid:=4258;
    ELSIF selected->>'crs'='EPSG:8081' THEN native_srid:=8081;
    ELSE RETURN NEW; END IF;
    IF jsonb_typeof(selected->'longitude') IS DISTINCT FROM 'number' OR jsonb_typeof(selected->'latitude') IS DISTINCT FROM 'number'
       OR (selected->>'longitude')::double precision NOT BETWEEN -19 AND 5
       OR (selected->>'latitude')::double precision NOT BETWEEN 27 AND 44.5
       OR coalesce(real_preview.spanish_house_key(selected->>'house'),'') !~ '^[1-9][0-9]*'
       OR nullif(selected->>'provider','') IS NULL OR nullif(selected->>'source_date','') IS NULL
    THEN RETURN NEW; END IF;
    expected := ST_Transform(ST_SetSRID(ST_MakePoint((selected->>'longitude')::double precision,
        (selected->>'latitude')::double precision),native_srid),4326);
    IF NOT ST_Equals(NEW.result::geometry,expected) THEN RETURN NEW; END IF;
    source_query := NEW.query::jsonb;
    IF source_query->>'schema_version' IS DISTINCT FROM 'uec-address-query-v1' OR source_query->>'country_code' IS DISTINCT FROM 'ES'
       OR source_query->>'address' ~* '\m(s\s*[/.-]\s*n|sin\s+n[uú]mero|km|kil[oó]metros?)\M'
       OR NOT real_preview.spanish_street_matches(source_query->>'address',selected->>'street',selected->>'house')
       OR real_preview.spanish_locality_key(source_query->>'locality') IS DISTINCT FROM
          real_preview.spanish_locality_key(selected->>'municipality')
       OR (nullif(source_query->>'postcode','') IS NOT NULL AND source_query->>'postcode' IS DISTINCT FROM selected->>'postcode')
    THEN RETURN NEW; END IF;
    geometry_source := 'CartoCiudad CC-BY 4.0 scne.es; local numbered-address match; archive_sha256='||
        (archive->>'archive_sha256');
    FOR target IN
        SELECT DISTINCT c.candidate_id FROM uec.geocode_jobs j
        JOIN real_preview.geocode_targets t USING(job_id)
        JOIN real_preview.candidates c USING(candidate_id,snapshot_sha256,source_id)
        JOIN real_preview.candidate_private_location_evidence l USING(candidate_id,snapshot_sha256,source_id)
        JOIN LATERAL(SELECT municipality,province FROM real_preview.spain_verified_locality_evidence v
            WHERE v.candidate_id=c.candidate_id AND v.snapshot_sha256=c.snapshot_sha256 AND v.source_id=c.source_id
            ORDER BY retrieved_at DESC,evidence_event_id DESC LIMIT 1) town ON true
        WHERE j.provider_id=NEW.provider_id AND j.query=NEW.query AND j.source_record_id=NEW.source_record_id
          AND c.source_id='es.locations' AND c.country_code='ES' AND c.default_map_scope
          AND c.latitude IS NULL AND c.longitude IS NULL
          AND c.snapshot_sha256=(SELECT snapshot_sha256 FROM real_preview.source_preview_runs
              WHERE source_id=c.source_id ORDER BY created_at DESC,run_id DESC LIMIT 1)
          AND source_query->>'address'=l.location_evidence->>'address' AND l.location_evidence->>'country_code'='ES'
          AND real_preview.spanish_locality_key(source_query->>'locality')=real_preview.spanish_locality_key(town.municipality)
          AND real_preview.spanish_province_key(town.province)=real_preview.spanish_province_key(selected->>'province')
          AND real_preview.spanish_province_key(town.province)=real_preview.spanish_province_key(archive->>'province')
          AND NOT EXISTS(SELECT 1 FROM real_preview.enrichment_state_events e
              WHERE e.candidate_id=c.candidate_id AND e.state_code='restricted')
          AND NOT EXISTS(SELECT 1 FROM real_preview.geocode_targets linked
              JOIN uec.geocode_jobs job USING(job_id) JOIN uec.public_access_restricted r USING(source_record_id)
              WHERE linked.source_id=c.source_id AND linked.source_record_key=c.source_group_key)
    LOOP
        INSERT INTO real_preview.geocode_display_evidence(candidate_id,geocode_result_id,
            display_latitude,display_longitude,display_precision,display_geometry_source,
            coordinate_review_status,match_confidence,match_confidence_band)
        VALUES(target.candidate_id,NEW.geocode_result_id,ST_Y(expected),ST_X(expected),
            'provider_address_point_high_confidence',geometry_source,
            'automated_high_confidence_private_display',NULL,'high_heuristic') ON CONFLICT DO NOTHING;
    END LOOP;
    RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS geocode_results_cartociudad_local_portal ON uec.geocode_results;
CREATE TRIGGER geocode_results_cartociudad_local_portal AFTER INSERT ON uec.geocode_results
FOR EACH ROW EXECUTE FUNCTION real_preview.capture_cartociudad_local_portal();

DO $migration$
DECLARE definition TEXT; marker TEXT; addition TEXT;
BEGIN
    definition:=pg_get_functiondef('real_preview.reject_mutation()'::regprocedure);
    marker:='    RAISE EXCEPTION ''real preview evidence is append-only'';';
    addition:=$guard$
    IF TG_TABLE_SCHEMA='real_preview' AND TG_TABLE_NAME='candidates' AND TG_OP='UPDATE'
       AND (to_jsonb(OLD)-ARRAY['display_latitude','display_longitude','display_geometry_source',
           'coordinate_method','coordinate_provider','coordinate_confidence','coordinate_confidence_band'])
         = (to_jsonb(NEW)-ARRAY['display_latitude','display_longitude','display_geometry_source',
           'coordinate_method','coordinate_provider','coordinate_confidence','coordinate_confidence_band'])
       AND NEW.coordinate_method='cartociudad_local_portal_v1' AND NEW.coordinate_provider='CartoCiudad'
       AND NEW.coordinate_confidence IS NULL AND NEW.coordinate_confidence_band='high'
       AND EXISTS(SELECT 1 FROM real_preview.geocode_display_evidence e
           JOIN uec.geocode_results r USING(geocode_result_id) WHERE e.candidate_id=NEW.candidate_id
           AND r.provider_id='cartociudad_local' AND r.status='accepted'
           AND r.match_method='cartociudad_local_portal_v1'
           AND e.display_latitude=NEW.display_latitude AND e.display_longitude=NEW.display_longitude
           AND e.display_geometry_source=NEW.display_geometry_source)
    THEN RETURN NEW; END IF;
    $guard$;
    IF position('NEW.coordinate_method=''cartociudad_local_portal_v1''' IN definition)=0 THEN
        IF length(definition)-length(replace(definition,marker,''))<>length(marker) THEN
            RAISE EXCEPTION 'candidate guard marker is not unique'; END IF;
        EXECUTE replace(definition,marker,addition||E'\n'||marker);
    END IF;
    definition:=pg_get_functiondef('real_preview.sync_geoapify_private_display()'::regprocedure);
    marker:='BEGIN';
    addition:=$sync$
    IF EXISTS(SELECT 1 FROM uec.geocode_results r WHERE r.geocode_result_id=NEW.geocode_result_id
              AND r.provider_id='cartociudad_local' AND r.match_method='cartociudad_local_portal_v1') THEN
        UPDATE real_preview.candidates SET display_latitude=NEW.display_latitude,
            display_longitude=NEW.display_longitude,display_geometry_source=NEW.display_geometry_source,
            coordinate_method='cartociudad_local_portal_v1',coordinate_provider='CartoCiudad',
            coordinate_confidence=NULL,coordinate_confidence_band='high'
        WHERE candidate_id=NEW.candidate_id;
        RETURN NEW;
    END IF;
    $sync$;
    IF position('coordinate_provider=''CartoCiudad''' IN definition)=0 THEN
        IF length(definition)-length(replace(definition,marker,''))<>length(marker) THEN
            RAISE EXCEPTION 'display sync marker is not unique'; END IF;
        EXECUTE replace(definition,marker,marker||E'\n'||addition);
    END IF;
END;
$migration$;
