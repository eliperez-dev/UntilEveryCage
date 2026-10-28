-- Private LocationIQ capture for structured ES/GB/NZ source-address queries.
-- No public release, source record, or acquisition state is changed here.
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
           AND NEW.coordinate_method='locationiq_forward' AND NEW.coordinate_provider='LocationIQ'
           AND NEW.coordinate_confidence IS NULL AND NEW.coordinate_confidence_band='high'
           AND EXISTS (SELECT 1 FROM real_preview.geocode_display_evidence evidence
               JOIN uec.geocode_results result USING(geocode_result_id)
               JOIN real_preview.locationiq_first_pass_context_audit audit
                 ON audit.candidate_id=evidence.candidate_id
                AND audit.geocode_result_id=evidence.geocode_result_id
                AND audit.snapshot_sha256=NEW.snapshot_sha256
                AND audit.source_id=NEW.source_id AND audit.outcome='matched'
               WHERE evidence.candidate_id=NEW.candidate_id
                 AND result.provider_id='locationiq' AND result.status='accepted'
                 AND evidence.display_latitude=NEW.display_latitude
                 AND evidence.display_longitude=NEW.display_longitude
                 AND evidence.display_geometry_source=NEW.display_geometry_source)
        THEN RETURN NEW; END IF;
        $guard$;
BEGIN
    IF to_regnamespace('real_preview') IS NULL
       OR to_regclass('real_preview.private_geocoding_source_profiles') IS NULL
       OR to_regclass('real_preview.candidate_private_location_evidence') IS NULL
       OR to_regclass('real_preview.geocode_targets') IS NULL
       OR to_regclass('real_preview.geocode_display_evidence') IS NULL
       OR to_regclass('real_preview.spain_verified_locality_evidence') IS NULL
       OR to_regprocedure('real_preview.reject_mutation()') IS NULL
       OR to_regprocedure('real_preview.normalize_geocode_address(text)') IS NULL
       OR to_regprocedure('real_preview.normalize_new_zealand_geocode_text(text)') IS NULL THEN
        RETURN;
    END IF;

    ALTER TABLE real_preview.private_geocoding_source_profiles
        DROP CONSTRAINT IF EXISTS private_geocoding_source_profiles_spain_profile_scope;
    ALTER TABLE real_preview.private_geocoding_source_profiles
        ADD CONSTRAINT private_geocoding_source_profiles_spain_profile_scope CHECK (
            (source_id='es.locations' AND country_code='ES'
             AND profile_id IN ('geoapify-es-aesan-rgseaa',
                                'geoapify-es-aesan-verified-municipality',
                                'locationiq-es-aesan-rgseaa'))
            OR (source_id='es.cat.feed-sandach' AND country_code='ES'
                AND profile_id='locationiq-es-cat-feed-sandach')
            OR (source_id NOT IN ('es.locations','es.cat.feed-sandach')
                AND profile_id NOT IN ('geoapify-es-aesan-rgseaa',
                                       'geoapify-es-aesan-verified-municipality',
                                       'locationiq-es-aesan-rgseaa',
                                       'locationiq-es-cat-feed-sandach'))
        );

    INSERT INTO real_preview.private_geocoding_source_profiles
        (profile_id,source_id,country_code,enabled,source_scope,provider_id)
    VALUES
        ('locationiq-es-aesan-rgseaa','es.locations','ES',true,
         'AESAN RGSEAA source-address first-pass only; query and result independently checked against retained private location and latest source-bound verified locality evidence','locationiq'),
        ('locationiq-es-cat-feed-sandach','es.cat.feed-sandach','ES',true,
         'Catalonia SANDACH source-address first-pass only; private source-address evidence and current-snapshot scope required','locationiq')
    ON CONFLICT (profile_id) DO UPDATE SET
        source_id=EXCLUDED.source_id,country_code=EXCLUDED.country_code,
        enabled=true,source_scope=EXCLUDED.source_scope,provider_id=EXCLUDED.provider_id;

    CREATE TABLE IF NOT EXISTS real_preview.locationiq_first_pass_context_audit (
        candidate_id UUID NOT NULL REFERENCES real_preview.candidates(candidate_id),
        snapshot_sha256 CHAR(64) NOT NULL,
        geocode_result_id UUID NOT NULL REFERENCES uec.geocode_results(geocode_result_id),
        profile_id TEXT NOT NULL CHECK (profile_id IN (
            'locationiq-es-aesan-rgseaa','locationiq-es-cat-feed-sandach',
            'locationiq-gb-fsa-approved-establishments',
            'locationiq-gb-fss-approved-establishments','locationiq-nz-mpi-rmp')),
        source_id TEXT NOT NULL CHECK (source_id IN (
            'es.locations','es.cat.feed-sandach','fsa_approved_establishments',
            'fss_approved_establishments','nz.locations')),
        outcome TEXT NOT NULL CHECK (outcome='matched'),
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        PRIMARY KEY(candidate_id,geocode_result_id),
        CHECK ((profile_id='locationiq-es-aesan-rgseaa' AND source_id='es.locations')
            OR (profile_id='locationiq-es-cat-feed-sandach' AND source_id='es.cat.feed-sandach')
            OR (profile_id='locationiq-gb-fsa-approved-establishments' AND source_id='fsa_approved_establishments')
            OR (profile_id='locationiq-gb-fss-approved-establishments' AND source_id='fss_approved_establishments')
            OR (profile_id='locationiq-nz-mpi-rmp' AND source_id='nz.locations'))
    );
    DROP TRIGGER IF EXISTS locationiq_first_pass_context_audit_immutable
        ON real_preview.locationiq_first_pass_context_audit;
    CREATE TRIGGER locationiq_first_pass_context_audit_immutable
        BEFORE UPDATE OR DELETE ON real_preview.locationiq_first_pass_context_audit
        FOR EACH ROW EXECUTE FUNCTION real_preview.reject_mutation();

    CREATE OR REPLACE FUNCTION real_preview.locationiq_first_pass_address_matches(
        item JSONB, source_address TEXT, source_locality TEXT,
        source_postcode TEXT, source_region TEXT, country_code TEXT)
    RETURNS BOOLEAN LANGUAGE plpgsql IMMUTABLE AS $function$
    DECLARE
        result_address JSONB := item->'address';
        house TEXT;
        road TEXT;
        result_locality_match BOOLEAN;
        result_postcode_match BOOLEAN;
        result_region_match BOOLEAN;
        viable_fragments INTEGER;
        latitude DOUBLE PRECISION;
        longitude DOUBLE PRECISION;
    BEGIN
        IF country_code IS NULL OR country_code NOT IN ('ES','GB','NZ')
           OR jsonb_typeof(item) IS DISTINCT FROM 'object'
           OR jsonb_typeof(result_address) IS DISTINCT FROM 'object'
           OR jsonb_typeof(item->'lat') IS DISTINCT FROM 'string'
           OR jsonb_typeof(item->'lon') IS DISTINCT FROM 'string'
           OR nullif(btrim(source_address),'') IS NULL
           OR (nullif(btrim(source_locality),'') IS NULL
               AND NOT (country_code='GB' AND nullif(btrim(source_postcode),'') IS NOT NULL))
           OR nullif(btrim(result_address->>'road'),'') IS NULL
           OR nullif(btrim(result_address->>'house_number'),'') IS NULL
           OR lower(coalesce(result_address->>'country_code','')) <> lower(country_code)
           OR item->>'type' IN ('houses','road','city','town','village','municipality','postcode')
           OR item->>'addresstype' IN ('houses','road','city','town','village','municipality','postcode')
           OR ((item->>'class') IN ('highway','boundary','place','landuse')
               AND NOT (item->>'class'='place' AND item->>'type'='house'
                        AND coalesce(item->>'addresstype','') IN ('','house','building')))
        THEN RETURN false; END IF;

        BEGIN
            latitude := (item->>'lat')::DOUBLE PRECISION;
            longitude := (item->>'lon')::DOUBLE PRECISION;
        EXCEPTION WHEN invalid_text_representation OR numeric_value_out_of_range THEN
            RETURN false;
        END;
        IF (country_code='ES' AND NOT (latitude BETWEEN 27 AND 44.5 AND longitude BETWEEN -19 AND 5))
           OR (country_code='GB' AND NOT (latitude BETWEEN 49.8 AND 60.9 AND longitude BETWEEN -8.7 AND 2.1))
           OR (country_code='NZ' AND NOT (latitude BETWEEN -47.5 AND -34.0 AND longitude BETWEEN 166 AND 179.9))
        THEN RETURN false; END IF;

        road := lower(btrim(result_address->>'road'));
        house := lower(btrim(result_address->>'house_number'));
        IF nullif(btrim(source_locality),'') IS NULL THEN
            result_locality_match := country_code='GB'
                AND nullif(btrim(source_postcode),'') IS NOT NULL;
        ELSIF country_code='NZ' THEN
            road := real_preview.normalize_new_zealand_geocode_text(road);
            house := real_preview.normalize_new_zealand_geocode_text(house);
        ELSE
            road := real_preview.normalize_geocode_address(road);
            house := real_preview.normalize_geocode_address(house);
        END IF;
        IF country_code='NZ' THEN
            SELECT count(*)::integer INTO viable_fragments
              FROM regexp_split_to_table(source_address,',') AS fragments(part)
             WHERE real_preview.normalize_new_zealand_geocode_text(btrim(part)) IN
                   (house||' '||road,road||' '||house);
        ELSE
            SELECT count(*)::integer INTO viable_fragments
              FROM regexp_split_to_table(source_address,',') AS fragments(part)
             WHERE real_preview.normalize_geocode_address(btrim(part)) IN
                   (house||' '||road,road||' '||house);
        END IF;
        IF viable_fragments <> 1 THEN RETURN false; END IF;

        IF country_code='NZ' THEN
            result_locality_match := real_preview.normalize_new_zealand_geocode_text(source_locality) IN (
                real_preview.normalize_new_zealand_geocode_text(result_address->>'city'),
                real_preview.normalize_new_zealand_geocode_text(result_address->>'town'),
                real_preview.normalize_new_zealand_geocode_text(result_address->>'municipality'),
                real_preview.normalize_new_zealand_geocode_text(result_address->>'village'),
                real_preview.normalize_new_zealand_geocode_text(result_address->>'suburb'));
        ELSE
            result_locality_match := real_preview.normalize_geocode_address(source_locality) IN (
                real_preview.normalize_geocode_address(result_address->>'city'),
                real_preview.normalize_geocode_address(result_address->>'town'),
                real_preview.normalize_geocode_address(result_address->>'municipality'),
                real_preview.normalize_geocode_address(result_address->>'village'),
                real_preview.normalize_geocode_address(result_address->>'suburb'));
        END IF;
        IF NOT result_locality_match THEN RETURN false; END IF;

        result_postcode_match := nullif(btrim(source_postcode),'') IS NULL
            OR upper(regexp_replace(coalesce(result_address->>'postcode',''),'\s+','','g'))
               = upper(regexp_replace(source_postcode,'\s+','','g'));
        result_region_match := nullif(btrim(source_region),'') IS NULL
            OR real_preview.normalize_geocode_address(source_region) IN (
                real_preview.normalize_geocode_address(result_address->>'state'),
                real_preview.normalize_geocode_address(result_address->>'state_code'),
                real_preview.normalize_geocode_address(result_address->>'county'));
        RETURN result_postcode_match AND result_region_match;
    END
    $function$;

    CREATE OR REPLACE FUNCTION real_preview.capture_locationiq_first_pass_private_display()
    RETURNS trigger LANGUAGE plpgsql AS $function$
    DECLARE
        payload JSONB;
        selected JSONB;
        candidate_context RECORD;
        viable_count INTEGER;
        selected_index INTEGER;
        selected_latitude DOUBLE PRECISION;
        selected_longitude DOUBLE PRECISION;
        geometry_latitude DOUBLE PRECISION;
        geometry_longitude DOUBLE PRECISION;
    BEGIN
        IF NEW.provider_id <> 'locationiq' OR NEW.status <> 'accepted'
           OR NEW.precision <> 'locationiq_address_point'
           OR NEW.match_method <> 'locationiq_forward' OR NEW.result IS NULL
           OR NEW.response IS NULL
        THEN RETURN NEW; END IF;
        IF jsonb_typeof(NEW.response->'results') IS DISTINCT FROM 'array' THEN RETURN NEW; END IF;
        IF jsonb_array_length(NEW.response->'results') NOT BETWEEN 1 AND 2
           OR coalesce(NEW.response->>'_uec_selected_result_index','') !~ '^[01]$'
        THEN RETURN NEW; END IF;
        BEGIN
            IF length(NEW.query) > 2500 THEN RETURN NEW; END IF;
            payload := NEW.query::JSONB;
        EXCEPTION WHEN invalid_text_representation THEN
            RETURN NEW;
        END;
        IF jsonb_typeof(payload) IS DISTINCT FROM 'object' THEN RETURN NEW; END IF;
        IF (SELECT count(*) FROM jsonb_object_keys(payload)) <> 6
           OR payload - ARRAY['schema_version','address','locality','postcode','region','country_code'] <> '{}'::jsonb
           OR payload->>'schema_version' IS DISTINCT FROM 'uec-address-query-v1'
           OR jsonb_typeof(payload->'address') IS DISTINCT FROM 'string'
           OR length(payload->>'address') NOT BETWEEN 1 AND 1200
           OR jsonb_typeof(payload->'locality') IS DISTINCT FROM 'string'
           OR length(payload->>'locality') > 200
           OR jsonb_typeof(payload->'country_code') IS DISTINCT FROM 'string'
           OR payload->>'country_code' NOT IN ('ES','GB','NZ')
           OR (jsonb_typeof(payload->'postcode') NOT IN ('string','null'))
           OR (jsonb_typeof(payload->'region') NOT IN ('string','null'))
           OR length(coalesce(payload->>'postcode','')) > 20
           OR length(coalesce(payload->>'region','')) > 200
        THEN RETURN NEW; END IF;
        selected_index := (NEW.response->>'_uec_selected_result_index')::INTEGER;
        selected := NEW.response->'results'->selected_index;

        FOR candidate_context IN
            SELECT candidate.candidate_id,candidate.snapshot_sha256,
                   candidate.source_id,profile.profile_id,
                   payload->>'address' AS source_address,
                   payload->>'locality' AS source_locality,
                   nullif(payload->>'postcode','') AS source_postcode,
                   nullif(payload->>'region','') AS source_region,
                   payload->>'country_code' AS country_code
              FROM uec.geocode_jobs job
              JOIN real_preview.geocode_targets target ON target.job_id=job.job_id
              JOIN real_preview.candidates candidate ON candidate.candidate_id=target.candidate_id
              JOIN real_preview.candidate_private_location_evidence location
                ON location.candidate_id=candidate.candidate_id
               AND location.snapshot_sha256=candidate.snapshot_sha256
               AND location.source_id=candidate.source_id
              JOIN real_preview.private_geocoding_source_profiles profile
                ON profile.profile_id IN (
                    'locationiq-es-aesan-rgseaa','locationiq-es-cat-feed-sandach',
                    'locationiq-gb-fsa-approved-establishments',
                    'locationiq-gb-fss-approved-establishments','locationiq-nz-mpi-rmp')
               AND profile.provider_id='locationiq' AND profile.source_id=candidate.source_id
               AND profile.country_code=candidate.country_code AND profile.enabled
              JOIN uec.geocode_job_events queued ON queued.job_id=job.job_id
               AND queued.event_type='queued'
               AND queued.details->>'processing_mode'='private_locationiq_source_profile'
               AND queued.details->>'profile_id'=profile.profile_id
              LEFT JOIN LATERAL (
                  SELECT evidence.evidence_event_id,evidence.municipality
                    FROM real_preview.spain_verified_locality_evidence evidence
                   WHERE evidence.candidate_id=candidate.candidate_id
                     AND evidence.snapshot_sha256=candidate.snapshot_sha256
                     AND evidence.source_id=candidate.source_id
                   ORDER BY evidence.retrieved_at DESC,evidence.evidence_event_id DESC
                   LIMIT 1
              ) verified ON profile.profile_id='locationiq-es-aesan-rgseaa'
             WHERE job.source_record_id=NEW.source_record_id
               AND job.query=NEW.query AND job.provider_id=NEW.provider_id
               AND target.source_id=candidate.source_id
               AND target.snapshot_sha256=candidate.snapshot_sha256
               AND candidate.default_map_scope
               AND candidate.latitude IS NULL AND candidate.longitude IS NULL
               AND candidate.location_class <> 'numeric_source_coordinate'
               AND candidate.snapshot_sha256=COALESCE(
                   (SELECT run.snapshot_sha256 FROM real_preview.source_preview_runs run
                    WHERE run.source_id=candidate.source_id
                    ORDER BY run.created_at DESC,run.run_id DESC LIMIT 1),
                   (SELECT manifest.snapshot_sha256 FROM real_preview.source_manifests manifest
                    WHERE manifest.source_id=candidate.source_id
                    ORDER BY manifest.retrieved_at DESC,manifest.snapshot_sha256 DESC LIMIT 1))
               AND candidate.country_code=payload->>'country_code'
               AND location.location_evidence->>'country_code'=candidate.country_code
               AND ((profile.profile_id='locationiq-es-aesan-rgseaa'
                     AND candidate.source_id='es.locations' AND candidate.country_code='ES')
                 OR (profile.profile_id='locationiq-es-cat-feed-sandach'
                     AND candidate.source_id='es.cat.feed-sandach' AND candidate.country_code='ES')
                 OR (profile.profile_id='locationiq-gb-fsa-approved-establishments'
                     AND candidate.source_id='fsa_approved_establishments' AND candidate.country_code='GB')
                 OR (profile.profile_id='locationiq-gb-fss-approved-establishments'
                     AND candidate.source_id='fss_approved_establishments' AND candidate.country_code='GB')
                 OR (profile.profile_id='locationiq-nz-mpi-rmp'
                     AND candidate.source_id='nz.locations' AND candidate.country_code='NZ'))
               AND payload->>'address' = CASE
                   WHEN profile.profile_id IN ('locationiq-gb-fsa-approved-establishments',
                                                'locationiq-gb-fss-approved-establishments')
                   THEN (SELECT string_agg(line.value #>> '{}', ', ' ORDER BY line.ordinality)
                           FROM jsonb_array_elements(location.location_evidence->'address_lines')
                                WITH ORDINALITY AS line(value,ordinality))
                   ELSE location.location_evidence->>'address' END
               AND (profile.profile_id NOT IN ('locationiq-gb-fsa-approved-establishments',
                                                'locationiq-gb-fss-approved-establishments')
                    OR (jsonb_typeof(location.location_evidence->'address_lines')='array'
                        AND NOT EXISTS (SELECT 1
                            FROM jsonb_array_elements(location.location_evidence->'address_lines') AS lines(value)
                            WHERE jsonb_typeof(value) IS DISTINCT FROM 'string')))
               AND (
                    payload->>'locality' IS NOT DISTINCT FROM nullif(location.location_evidence->>'city','')
                    OR (candidate.country_code='GB'
                        AND nullif(payload->>'locality','') IS NULL
                        AND nullif(location.location_evidence->>'city','') IS NULL
                        AND nullif(payload->>'postcode','') IS NOT NULL)
                    OR (profile.profile_id='locationiq-es-aesan-rgseaa'
                        AND verified.evidence_event_id IS NOT NULL
                        AND payload->>'locality'=verified.municipality)
               )
               AND nullif(payload->>'postcode','') IS NOT DISTINCT FROM
                   nullif(location.location_evidence->>'postal_code','')
               AND nullif(payload->>'region','') IS NOT DISTINCT FROM
                   nullif(location.location_evidence->>'region','')
               AND (jsonb_typeof(location.location_evidence->'coordinates') IS DISTINCT FROM 'object'
                    OR NOT (location.location_evidence->'coordinates' ?| ARRAY[
                        'latitude','longitude','x','y']))
               AND NOT EXISTS (SELECT 1 FROM uec.public_access_restricted restricted
                                WHERE restricted.source_record_id=NEW.source_record_id)
               AND NOT EXISTS (SELECT 1 FROM real_preview.enrichment_state_events state
                                WHERE state.candidate_id=candidate.candidate_id
                                  AND state.state_code='restricted')
               AND (candidate.source_id<>'nz.locations'
                    OR (trim(coalesce(location.location_evidence->>'number_of_locations',''))='1'
                        AND jsonb_typeof(location.location_evidence->'location_count')='number'
                        AND location.location_evidence->>'location_count'='1'))
             FOR UPDATE OF candidate
        LOOP
            SELECT count(*)::integer INTO viable_count
              FROM jsonb_array_elements(NEW.response->'results') item
             WHERE real_preview.locationiq_first_pass_address_matches(
                 item,candidate_context.source_address,candidate_context.source_locality,
                 candidate_context.source_postcode,candidate_context.source_region,
                 candidate_context.country_code);
            IF viable_count <> 1
               OR NOT real_preview.locationiq_first_pass_address_matches(
                   selected,candidate_context.source_address,candidate_context.source_locality,
                   candidate_context.source_postcode,candidate_context.source_region,
                   candidate_context.country_code)
            THEN CONTINUE; END IF;
            BEGIN
                selected_latitude := (selected->>'lat')::DOUBLE PRECISION;
                selected_longitude := (selected->>'lon')::DOUBLE PRECISION;
                geometry_latitude := ST_Y(NEW.result::geometry);
                geometry_longitude := ST_X(NEW.result::geometry);
            EXCEPTION WHEN invalid_text_representation OR numeric_value_out_of_range THEN
                CONTINUE;
            END;
            IF geometry_latitude <> selected_latitude OR geometry_longitude <> selected_longitude
            THEN CONTINUE; END IF;

            INSERT INTO real_preview.locationiq_first_pass_context_audit
                (candidate_id,snapshot_sha256,geocode_result_id,profile_id,source_id,outcome)
            VALUES(candidate_context.candidate_id,candidate_context.snapshot_sha256,
                   NEW.geocode_result_id,candidate_context.profile_id,candidate_context.source_id,'matched')
            ON CONFLICT DO NOTHING;
            INSERT INTO real_preview.geocode_display_evidence
                (candidate_id,geocode_result_id,display_latitude,display_longitude,
                 display_precision,display_geometry_source,coordinate_review_status,
                 match_confidence,match_confidence_band)
            VALUES(candidate_context.candidate_id,NEW.geocode_result_id,
                   geometry_latitude,geometry_longitude,
                   'provider_address_point_high_confidence',
                   'LocationIQ; retained structured source address, locality, optional postcode and region matched; private preview only',
                   'automated_high_confidence_private_display',NULL,'high_heuristic')
            ON CONFLICT (candidate_id,geocode_result_id) DO NOTHING;
        END LOOP;
        RETURN NEW;
    END
    $function$;

    DROP TRIGGER IF EXISTS geocode_results_locationiq_first_pass_private_display ON uec.geocode_results;
    CREATE TRIGGER geocode_results_locationiq_first_pass_private_display
        AFTER INSERT ON uec.geocode_results
        FOR EACH ROW EXECUTE FUNCTION real_preview.capture_locationiq_first_pass_private_display();

    -- Add this audit exception without removing the existing private append-only gates.
    definition := pg_get_functiondef('real_preview.reject_mutation()'::regprocedure);
    IF length(definition)-length(replace(definition,marker,'')) <> length(marker) THEN
        RAISE EXCEPTION 'first-pass candidate cache guard marker is not unique';
    END IF;
    EXECUTE replace(definition,marker,addition || E'\n' || marker);
END
$migration$;
