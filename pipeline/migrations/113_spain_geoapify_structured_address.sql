-- Match Geoapify against retained source components, not a formatted address
-- line. Reuse the independently checked Spanish street/locality rules.
DO $migration$
DECLARE definition TEXT;
    marker TEXT := 'AND profile.profile_id <> ''geoapify-de-bltu''';
BEGIN
    IF to_regprocedure('real_preview.locationiq_first_pass_address_matches(jsonb,text,text,text,text,text)') IS NULL
       OR to_regprocedure('real_preview.spanish_street_matches(text,text,text)') IS NULL THEN
        RETURN;
    END IF;

    CREATE OR REPLACE FUNCTION real_preview.spanish_geoapify_address_matches(
        feature JSONB, source_address TEXT, source_locality TEXT,
        source_postcode TEXT, source_region TEXT)
    RETURNS BOOLEAN LANGUAGE plpgsql IMMUTABLE AS $function$
    DECLARE properties JSONB := feature->'properties'; confidence DOUBLE PRECISION;
        coordinates JSONB := feature#>'{geometry,coordinates}'; item JSONB;
    BEGIN
        IF jsonb_typeof(properties) IS DISTINCT FROM 'object'
           OR feature#>>'{geometry,type}' IS DISTINCT FROM 'Point'
           OR jsonb_typeof(coordinates) IS DISTINCT FROM 'array'
        THEN RETURN false; END IF;
        IF jsonb_array_length(coordinates) <> 2
           OR jsonb_typeof(coordinates->0) IS DISTINCT FROM 'number'
           OR jsonb_typeof(coordinates->1) IS DISTINCT FROM 'number'
           OR coalesce(properties->>'result_type','') NOT IN ('building','amenity')
           OR jsonb_typeof(properties#>'{rank,confidence}') IS DISTINCT FROM 'number'
        THEN RETURN false; END IF;
        confidence := (properties#>>'{rank,confidence}')::DOUBLE PRECISION;
        IF NOT confidence BETWEEN .90 AND 1 THEN RETURN false; END IF;
        item := jsonb_build_object(
            'lat',coordinates->>1,'lon',coordinates->>0,
            'class','building','type','house','addresstype','building',
            'address',(properties-ARRAY['address_line1','rank','result_type']) ||
                jsonb_build_object('road',properties->'street','house_number',properties->'housenumber'));
        RETURN coalesce(real_preview.locationiq_first_pass_address_matches(
            item,source_address,source_locality,source_postcode,source_region,'ES'),false);
    END
    $function$;

    CREATE OR REPLACE FUNCTION real_preview.capture_spain_geoapify_private_display()
    RETURNS trigger LANGUAGE plpgsql AS $function$
    DECLARE payload JSONB; selected JSONB; context RECORD; viable_count INTEGER;
        selected_index INTEGER; latitude DOUBLE PRECISION; longitude DOUBLE PRECISION;
    BEGIN
        IF NEW.provider_id IS DISTINCT FROM 'geoapify' OR NEW.status IS DISTINCT FROM 'accepted'
           OR NEW.precision IS DISTINCT FROM 'geoapify_address_point' OR NEW.match_method IS DISTINCT FROM 'geoapify_forward'
           OR NEW.result IS NULL OR NEW.response IS NULL OR length(NEW.query)>2500
        THEN RETURN NEW; END IF;
        -- Legacy locality jobs use their separate bridge. New address jobs
        -- retain the complete structured query, including source-bound town.
        BEGIN payload := NEW.query::JSONB;
        EXCEPTION WHEN invalid_text_representation THEN RETURN NEW; END;
        IF jsonb_typeof(payload) IS DISTINCT FROM 'object'
           OR jsonb_typeof(NEW.response->'features') IS DISTINCT FROM 'array'
        THEN RETURN NEW; END IF;
        IF jsonb_array_length(NEW.response->'features') NOT BETWEEN 1 AND 2
           OR coalesce(NEW.response->>'_uec_selected_feature_index','') !~ '^[01]$'
        THEN RETURN NEW; END IF;
        selected_index := (NEW.response->>'_uec_selected_feature_index')::INTEGER;
        selected := NEW.response->'features'->selected_index;

        FOR context IN
            SELECT DISTINCT candidate.candidate_id,location.location_evidence AS location,
                verified.municipality
            FROM uec.geocode_jobs job
            JOIN real_preview.geocode_targets target USING(job_id)
            JOIN real_preview.candidates candidate ON candidate.candidate_id=target.candidate_id
                AND candidate.source_id=target.source_id AND candidate.snapshot_sha256=target.snapshot_sha256
            JOIN real_preview.candidate_private_location_evidence location
                ON location.candidate_id=candidate.candidate_id AND location.snapshot_sha256=candidate.snapshot_sha256
                AND location.source_id=candidate.source_id
            JOIN real_preview.private_geocoding_source_profiles profile
                ON profile.source_id=candidate.source_id AND profile.country_code=candidate.country_code
                AND profile.profile_id='geoapify-es-aesan-rgseaa' AND profile.provider_id='geoapify' AND profile.enabled
            JOIN LATERAL (
                SELECT evidence.municipality FROM real_preview.spain_verified_locality_evidence evidence
                WHERE evidence.candidate_id=candidate.candidate_id
                    AND evidence.snapshot_sha256=candidate.snapshot_sha256 AND evidence.source_id=candidate.source_id
                ORDER BY evidence.retrieved_at DESC,evidence.evidence_event_id DESC LIMIT 1
            ) verified ON true
            WHERE job.source_record_id=NEW.source_record_id AND job.provider_id=NEW.provider_id AND job.query=NEW.query
                AND candidate.source_id='es.locations' AND candidate.country_code='ES' AND candidate.default_map_scope
                AND candidate.latitude IS NULL AND candidate.longitude IS NULL
                AND candidate.location_class<>'numeric_source_coordinate'
                AND location.location_evidence->>'country_code'='ES'
                AND candidate.snapshot_sha256=(SELECT run.snapshot_sha256 FROM real_preview.source_preview_runs run
                    WHERE run.source_id=candidate.source_id ORDER BY run.created_at DESC,run.run_id DESC LIMIT 1)
                AND EXISTS(SELECT 1 FROM uec.geocode_job_events queued WHERE queued.job_id=job.job_id
                    AND queued.event_type='queued' AND queued.details->>'processing_mode'='private_geoapify_source_profile'
                    AND queued.details->>'profile_id'=profile.profile_id)
                AND NOT EXISTS(SELECT 1 FROM uec.public_access_restricted restricted WHERE restricted.source_record_id=NEW.source_record_id)
                AND NOT EXISTS(SELECT 1 FROM real_preview.enrichment_state_events state
                    WHERE state.candidate_id=candidate.candidate_id AND state.state_code='restricted')
        LOOP
            IF payload IS DISTINCT FROM jsonb_build_object(
                'schema_version','uec-address-query-v1','address',context.location->>'address',
                'locality',context.municipality,'postcode',nullif(coalesce(context.location->>'postal_code',context.location->>'postcode'),''),
                'region',nullif(context.location->>'region',''),'country_code','ES')
            THEN CONTINUE; END IF;
            SELECT count(*)::INTEGER INTO viable_count FROM jsonb_array_elements(NEW.response->'features') feature
                WHERE real_preview.spanish_geoapify_address_matches(feature,payload->>'address',payload->>'locality',
                    payload->>'postcode',payload->>'region');
            IF viable_count<>1 OR NOT real_preview.spanish_geoapify_address_matches(selected,
                payload->>'address',payload->>'locality',payload->>'postcode',payload->>'region')
            THEN CONTINUE; END IF;
            latitude := (selected#>>'{geometry,coordinates,1}')::DOUBLE PRECISION;
            longitude := (selected#>>'{geometry,coordinates,0}')::DOUBLE PRECISION;
            IF latitude<>ST_Y(NEW.result::geometry) OR longitude<>ST_X(NEW.result::geometry)
            THEN CONTINUE; END IF;
            INSERT INTO real_preview.geocode_display_evidence
                (candidate_id,geocode_result_id,display_latitude,display_longitude,display_precision,
                 display_geometry_source,coordinate_review_status,match_confidence,match_confidence_band)
            VALUES(context.candidate_id,NEW.geocode_result_id,latitude,longitude,'provider_address_point_high_confidence',
                'Geoapify; source street, house number, verified town and supplied postcode/province matched',
                'automated_high_confidence_private_display',(selected#>>'{properties,rank,confidence}')::DOUBLE PRECISION,'high_heuristic')
            ON CONFLICT(candidate_id,geocode_result_id) DO NOTHING;
        END LOOP;
        RETURN NEW;
    END
    $function$;

    -- The historical shared trigger also matched Spanish address lines. It
    -- must not bypass the dedicated source-context bridge above.
    definition := pg_get_functiondef('real_preview.capture_geoapify_private_display()'::regprocedure);
    IF position('AND profile.source_id <> ''es.locations''' IN definition)=0 THEN
        IF length(definition)-length(replace(definition,marker,''))<>length(marker) THEN
            RAISE EXCEPTION 'Shared Geoapify source guard marker is not unique';
        END IF;
        EXECUTE replace(definition,marker,marker||' AND profile.source_id <> ''es.locations''');
    END IF;
END
$migration$;
