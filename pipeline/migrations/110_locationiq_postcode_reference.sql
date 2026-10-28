-- Offline, explicitly approximate postcode references from retained GB results.
-- The ordinary/public schema is untouched when private real_preview is absent.
DO $migration$
DECLARE
    definition TEXT;
    marker TEXT := '    RAISE EXCEPTION ''real preview evidence is append-only'';';
    addition TEXT := $guard$
        IF TG_TABLE_SCHEMA='real_preview' AND TG_TABLE_NAME='candidates' AND TG_OP='UPDATE'
           AND (to_jsonb(OLD)-ARRAY['display_latitude','display_longitude','display_geometry_source',
               'coordinate_method','coordinate_provider','coordinate_confidence','coordinate_confidence_band'])
             = (to_jsonb(NEW)-ARRAY['display_latitude','display_longitude','display_geometry_source',
               'coordinate_method','coordinate_provider','coordinate_confidence','coordinate_confidence_band'])
           AND NEW.source_id IN ('fsa_approved_establishments','fss_approved_establishments')
           AND NEW.country_code='GB'
           AND NEW.coordinate_method='locationiq_postcode_reference_v1'
           AND NEW.coordinate_provider='LocationIQ'
           AND NEW.coordinate_confidence IS NULL AND NEW.coordinate_confidence_band IS NULL
           AND EXISTS (SELECT 1 FROM real_preview.geocode_display_evidence evidence
               JOIN uec.geocode_results result USING(geocode_result_id)
               JOIN real_preview.locationiq_first_pass_context_audit audit
                 ON audit.candidate_id=evidence.candidate_id
                AND audit.geocode_result_id=evidence.geocode_result_id
                AND audit.snapshot_sha256=NEW.snapshot_sha256
                AND audit.source_id=NEW.source_id AND audit.outcome='matched'
               WHERE evidence.candidate_id=NEW.candidate_id
                 AND evidence.display_precision='provider_locality_approximate'
                 AND evidence.coordinate_review_status='approximate_provider_locality_private_display'
                 AND evidence.display_geometry_source='LocationIQ postcode reference; approximate'
                 AND result.provider_id='locationiq' AND result.status='accepted'
                 AND result.precision='locationiq_postcode_point'
                 AND result.match_method='locationiq_postcode_reference_v1'
                 AND evidence.display_latitude=NEW.display_latitude
                 AND evidence.display_longitude=NEW.display_longitude
                 AND evidence.display_geometry_source=NEW.display_geometry_source)
        THEN RETURN NEW; END IF;
        $guard$;
BEGIN
    IF to_regnamespace('real_preview') IS NULL
       OR to_regclass('real_preview.candidates') IS NULL
       OR to_regclass('real_preview.candidate_private_location_evidence') IS NULL
       OR to_regclass('real_preview.geocode_targets') IS NULL
       OR to_regclass('real_preview.geocode_display_evidence') IS NULL
       OR to_regclass('real_preview.locationiq_first_pass_context_audit') IS NULL
       OR to_regclass('real_preview.private_geocoding_source_profiles') IS NULL
       OR to_regclass('real_preview.source_preview_runs') IS NULL
       OR to_regclass('real_preview.source_manifests') IS NULL
       OR to_regclass('real_preview.enrichment_state_events') IS NULL
       OR to_regprocedure('real_preview.reject_mutation()') IS NULL THEN
        RETURN;
    END IF;

    CREATE OR REPLACE FUNCTION real_preview.locationiq_uk_postcode_point(
        item JSONB, source_postcode TEXT)
    RETURNS geometry LANGUAGE plpgsql IMMUTABLE AS $function$
    DECLARE
        address JSONB := item->'address';
        postcode TEXT := upper(regexp_replace(btrim(coalesce(source_postcode,'')),'\s+','','g'));
        provider_postcode TEXT;
        latitude DOUBLE PRECISION;
        longitude DOUBLE PRECISION;
    BEGIN
        IF jsonb_typeof(item) IS DISTINCT FROM 'object'
           OR jsonb_typeof(address) IS DISTINCT FROM 'object'
           OR item->>'class' IS DISTINCT FROM 'place'
           OR item->>'type' IS DISTINCT FROM 'postcode'
           OR lower(coalesce(address->>'country_code','')) <> 'gb'
           OR postcode !~ '^(GIR0AA|[A-Z]{1,2}[0-9][A-Z0-9]?[0-9][A-Z]{2})$'
           OR jsonb_typeof(item->'lat') IS DISTINCT FROM 'string'
           OR jsonb_typeof(item->'lon') IS DISTINCT FROM 'string'
        THEN RETURN NULL; END IF;
        provider_postcode := upper(regexp_replace(btrim(coalesce(address->>'postcode','')),'\s+','','g'));
        IF provider_postcode <> postcode THEN RETURN NULL; END IF;
        BEGIN
            latitude := (item->>'lat')::DOUBLE PRECISION;
            longitude := (item->>'lon')::DOUBLE PRECISION;
        EXCEPTION WHEN invalid_text_representation OR numeric_value_out_of_range THEN
            RETURN NULL;
        END;
        IF NOT (latitude BETWEEN 49.8 AND 60.9 AND longitude BETWEEN -8.7 AND 2.1)
        THEN RETURN NULL; END IF;
        RETURN ST_SetSRID(ST_MakePoint(longitude,latitude),4326);
    END
    $function$;

    CREATE OR REPLACE FUNCTION real_preview.capture_locationiq_uk_postcode_reference()
    RETURNS trigger LANGUAGE plpgsql AS $function$
    DECLARE
        parent uec.geocode_results%ROWTYPE;
        payload JSONB;
        selected JSONB;
        selected_point geometry;
        viable_count INTEGER;
        context RECORD;
        selected_index INTEGER;
    BEGIN
        IF NEW.match_method IS DISTINCT FROM 'locationiq_postcode_reference_v1' THEN RETURN NEW; END IF;
        IF NEW.provider_id IS DISTINCT FROM 'locationiq'
           OR NEW.status IS DISTINCT FROM 'accepted'
           OR NEW.precision IS DISTINCT FROM 'locationiq_postcode_point'
           OR NEW.result IS NULL OR NEW.response IS NULL
           OR NEW.retryable IS DISTINCT FROM false
           OR jsonb_typeof(NEW.response->'results') IS DISTINCT FROM 'array'
           OR NEW.response->>'_uec_ruleset_version' IS DISTINCT FROM 'uk-postcode-reference-v1'
           OR coalesce(NEW.response->>'_uec_selected_result_index','') !~ '^[01]$'
           OR coalesce(NEW.response->>'_uec_parent_geocode_result_id','') !~*
              '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
        THEN RAISE EXCEPTION 'invalid LocationIQ postcode reference' USING ERRCODE='23514'; END IF;
        IF jsonb_array_length(NEW.response->'results') NOT BETWEEN 1 AND 2 THEN
            RAISE EXCEPTION 'invalid LocationIQ postcode result count' USING ERRCODE='23514';
        END IF;

        SELECT * INTO parent FROM uec.geocode_results prior
         WHERE prior.geocode_result_id=(NEW.response->>'_uec_parent_geocode_result_id')::UUID
           AND prior.provider_id='locationiq' AND prior.status='review_required'
           AND prior.source_record_id=NEW.source_record_id AND prior.query=NEW.query
           AND prior.queried_at=NEW.queried_at;
        IF parent.geocode_result_id IS NULL
           OR parent.response->'results' IS DISTINCT FROM NEW.response->'results'
        THEN RAISE EXCEPTION 'postcode reference parent mismatch' USING ERRCODE='23514'; END IF;

        BEGIN
            payload := NEW.query::JSONB;
        EXCEPTION WHEN invalid_text_representation THEN
            RAISE EXCEPTION 'postcode reference query invalid' USING ERRCODE='23514';
        END;
        IF jsonb_typeof(payload) IS DISTINCT FROM 'object' THEN
            RAISE EXCEPTION 'postcode reference query schema invalid' USING ERRCODE='23514';
        END IF;
        IF (SELECT count(*) FROM jsonb_object_keys(payload)) <> 6
           OR payload - ARRAY['schema_version','address','locality','postcode','region','country_code'] <> '{}'::JSONB
           OR payload->>'schema_version' IS DISTINCT FROM 'uec-address-query-v1'
           OR payload->>'country_code' IS DISTINCT FROM 'GB'
           OR jsonb_typeof(payload->'address') IS DISTINCT FROM 'string'
           OR jsonb_typeof(payload->'locality') IS DISTINCT FROM 'string'
           OR payload->>'address' = ''
           OR length(payload->>'address') > 1200
           OR length(payload->>'locality') > 200
           OR jsonb_typeof(payload->'postcode') IS DISTINCT FROM 'string'
           OR length(payload->>'postcode') > 30
           OR jsonb_typeof(payload->'region') NOT IN ('string','null')
           OR length(payload->>'region') > 200
        THEN RAISE EXCEPTION 'postcode reference query schema invalid' USING ERRCODE='23514'; END IF;
        selected_index := (NEW.response->>'_uec_selected_result_index')::INTEGER;
        selected := NEW.response->'results'->selected_index;

        FOR context IN
            SELECT candidate.candidate_id,candidate.snapshot_sha256,candidate.source_id,
                   profile.profile_id,location.location_evidence,payload->>'postcode' AS postcode
              FROM uec.geocode_jobs job
              JOIN real_preview.geocode_targets target ON target.job_id=job.job_id
              JOIN real_preview.candidates candidate ON candidate.candidate_id=target.candidate_id
              JOIN real_preview.candidate_private_location_evidence location
                ON location.candidate_id=candidate.candidate_id
               AND location.snapshot_sha256=candidate.snapshot_sha256
               AND location.source_id=candidate.source_id
              JOIN real_preview.private_geocoding_source_profiles profile
                ON profile.profile_id IN ('locationiq-gb-fsa-approved-establishments',
                                          'locationiq-gb-fss-approved-establishments')
               AND profile.source_id=candidate.source_id AND profile.country_code='GB'
               AND profile.provider_id='locationiq' AND profile.enabled
             WHERE job.source_record_id=NEW.source_record_id AND job.provider_id='locationiq'
               AND job.query=NEW.query AND target.source_id=candidate.source_id
               AND target.snapshot_sha256=candidate.snapshot_sha256
               AND candidate.source_id IN ('fsa_approved_establishments','fss_approved_establishments')
               AND candidate.country_code='GB' AND candidate.default_map_scope
               AND candidate.latitude IS NULL AND candidate.longitude IS NULL
               AND candidate.display_latitude IS NULL AND candidate.display_longitude IS NULL
               AND candidate.snapshot_sha256=COALESCE(
                   (SELECT run.snapshot_sha256 FROM real_preview.source_preview_runs run
                    WHERE run.source_id=candidate.source_id
                    ORDER BY run.created_at DESC,run.run_id DESC LIMIT 1),
                   (SELECT manifest.snapshot_sha256 FROM real_preview.source_manifests manifest
                    WHERE manifest.source_id=candidate.source_id
                    ORDER BY manifest.retrieved_at DESC,manifest.snapshot_sha256 DESC LIMIT 1))
               AND location.location_evidence->>'country_code'='GB'
               AND jsonb_typeof(location.location_evidence->'address_lines')='array'
               AND NOT EXISTS (SELECT 1
                   FROM jsonb_array_elements(location.location_evidence->'address_lines') AS line(value)
                   WHERE jsonb_typeof(value) IS DISTINCT FROM 'string')
               AND payload->>'address'=(SELECT string_agg(btrim(line.value #>> '{}'),', ' ORDER BY line.ordinality)
                   FROM jsonb_array_elements(location.location_evidence->'address_lines')
                        WITH ORDINALITY AS line(value,ordinality)
                   WHERE btrim(line.value #>> '{}')<>'')
               AND payload->>'locality'=coalesce(location.location_evidence->>'city','')
               AND payload->>'postcode'=coalesce(location.location_evidence->>'postal_code',
                                                    location.location_evidence->>'postcode')
               AND nullif(payload->>'region','') IS NOT DISTINCT FROM
                   nullif(location.location_evidence->>'region','')
               AND EXISTS (SELECT 1 FROM uec.geocode_job_events queued
                   WHERE queued.job_id=job.job_id AND queued.event_type='queued'
                     AND queued.details->>'processing_mode'='private_locationiq_source_profile'
                     AND queued.details->>'profile_id'=profile.profile_id
                     AND queued.details->>'first_pass_only'='true')
               AND NOT EXISTS (SELECT 1 FROM uec.public_access_restricted restricted
                   WHERE restricted.source_record_id=NEW.source_record_id)
               AND NOT EXISTS (SELECT 1 FROM real_preview.enrichment_state_events state
                   WHERE state.candidate_id=candidate.candidate_id AND state.state_code='restricted')
             FOR UPDATE OF candidate
        LOOP
            IF real_preview.locationiq_uk_postcode_point(selected,context.postcode) IS NULL THEN CONTINUE; END IF;
            SELECT count(DISTINCT ST_AsEWKB(result_point.candidate_point))::INTEGER INTO viable_count
              FROM jsonb_array_elements(NEW.response->'results') item
              CROSS JOIN LATERAL (SELECT real_preview.locationiq_uk_postcode_point(item,context.postcode))
                   AS result_point(candidate_point)
             WHERE result_point.candidate_point IS NOT NULL;
            IF viable_count<>1 THEN CONTINUE; END IF;
            selected_point:=real_preview.locationiq_uk_postcode_point(selected,context.postcode);
            IF ST_X(NEW.result::geometry)<>ST_X(selected_point)
               OR ST_Y(NEW.result::geometry)<>ST_Y(selected_point)
            THEN CONTINUE; END IF;

            INSERT INTO real_preview.locationiq_first_pass_context_audit
                (candidate_id,snapshot_sha256,geocode_result_id,profile_id,source_id,outcome)
            VALUES(context.candidate_id,context.snapshot_sha256,NEW.geocode_result_id,
                   context.profile_id,context.source_id,'matched') ON CONFLICT DO NOTHING;
            INSERT INTO real_preview.geocode_display_evidence
                (candidate_id,geocode_result_id,display_latitude,display_longitude,display_precision,
                 display_geometry_source,coordinate_review_status,match_confidence,match_confidence_band)
            VALUES(context.candidate_id,NEW.geocode_result_id,ST_Y(selected_point),ST_X(selected_point),
                   'provider_locality_approximate','LocationIQ postcode reference; approximate',
                   'approximate_provider_locality_private_display',NULL,NULL)
            ON CONFLICT (candidate_id,geocode_result_id) DO NOTHING;
        END LOOP;
        RETURN NEW;
    END
    $function$;

    -- The shared cache sync retains exact-result behavior while marking a
    -- postcode reference as approximate rather than assigning a confidence band.
    CREATE OR REPLACE FUNCTION real_preview.sync_geoapify_private_display()
    RETURNS trigger LANGUAGE plpgsql AS $function$
    DECLARE
        provider TEXT;
        result_method TEXT;
    BEGIN
        SELECT provider_id,match_method INTO provider,result_method
          FROM uec.geocode_results WHERE geocode_result_id=NEW.geocode_result_id;
        UPDATE real_preview.candidates
           SET display_latitude=NEW.display_latitude,
               display_longitude=NEW.display_longitude,
               display_geometry_source=NEW.display_geometry_source,
               coordinate_method=CASE
                   WHEN result_method='locationiq_postcode_reference_v1' THEN result_method
                   WHEN provider='locationiq' THEN 'locationiq_forward'
                   ELSE 'geoapify_forward' END,
               coordinate_provider=CASE WHEN provider='locationiq' THEN 'LocationIQ' ELSE 'Geoapify' END,
               coordinate_confidence=NEW.match_confidence,
               coordinate_confidence_band=CASE
                   WHEN result_method='locationiq_postcode_reference_v1' THEN NULL
                   ELSE 'high' END
         WHERE candidate_id=NEW.candidate_id;
        RETURN NEW;
    END
    $function$;

    DROP TRIGGER IF EXISTS geocode_results_locationiq_uk_postcode_reference ON uec.geocode_results;
    CREATE TRIGGER geocode_results_locationiq_uk_postcode_reference
        AFTER INSERT ON uec.geocode_results
        FOR EACH ROW EXECUTE FUNCTION real_preview.capture_locationiq_uk_postcode_reference();

    definition := pg_get_functiondef('real_preview.reject_mutation()'::regprocedure);
    IF length(definition)-length(replace(definition,marker,'')) <> length(marker) THEN
        RAISE EXCEPTION 'postcode-reference candidate cache guard marker is not unique';
    END IF;
    EXECUTE replace(definition,marker,addition || E'\n' || marker);
END
$migration$;
