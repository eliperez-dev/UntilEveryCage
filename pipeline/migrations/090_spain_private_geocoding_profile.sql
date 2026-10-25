-- Add the AESAN RGSEAA address lane only to installations that have the
-- private real-preview schema. The public/production schema is unaffected.
DO $migration$
BEGIN
    IF to_regnamespace('real_preview') IS NULL
       OR to_regclass('real_preview.private_geocoding_source_profiles') IS NULL THEN
        RETURN;
    END IF;

    ALTER TABLE real_preview.private_geocoding_source_profiles
        DROP CONSTRAINT IF EXISTS private_geocoding_source_profiles_country_code_check;
    ALTER TABLE real_preview.private_geocoding_source_profiles
        ADD CONSTRAINT private_geocoding_source_profiles_country_code_check
        CHECK (country_code IN ('GB','DK','NL','US','ES'));

    INSERT INTO real_preview.private_geocoding_source_profiles
        (profile_id, source_id, country_code, enabled, source_scope)
    VALUES
        ('geoapify-es-aesan-rgseaa', 'es.locations', 'ES', true,
         'AESAN RGSEAA animal-origin industrial addresses only; exact address matches retain the source house number; no locality-only display')
    ON CONFLICT (profile_id) DO UPDATE SET
        source_id=EXCLUDED.source_id,
        country_code=EXCLUDED.country_code,
        source_scope=EXCLUDED.source_scope,
        enabled=true;

    CREATE OR REPLACE FUNCTION real_preview.normalize_geocode_address(input_text TEXT)
    RETURNS TEXT LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $function$
        SELECT trim(regexp_replace(
            translate(lower(coalesce(input_text,'')),
                      'áàäâãåéèëêíìïîóòöôõúùüûñç',
                      'aaaaaaeeeeiiiiooooouuuunc'),
            '[^[:alnum:]]+', ' ', 'g'))
    $function$;

    CREATE OR REPLACE FUNCTION real_preview.capture_geoapify_private_display()
    RETURNS trigger LANGUAGE plpgsql AS $function$
    DECLARE
        matched_candidate UUID;
        profile_country TEXT;
        properties JSONB;
        result_type TEXT;
        result_country TEXT;
        confidence_text TEXT;
        confidence_score DOUBLE PRECISION;
        result_address TEXT;
        source_address TEXT;
        precision_label TEXT;
        disclosure TEXT;
        review_state TEXT;
        viable_match_count INTEGER;
    BEGIN
        IF NEW.provider_id <> 'geoapify' OR NEW.status <> 'accepted'
           OR NEW.result IS NULL OR NEW.response IS NULL THEN
            RETURN NEW;
        END IF;

        SELECT profile.country_code::text, target.candidate_id,
               COALESCE(private_location.location_evidence->'address_lines'->>0,
                        private_location.location_evidence->>'address'),
               feature->'properties'
          INTO profile_country, matched_candidate, source_address, properties
          FROM uec.geocode_jobs job
          JOIN real_preview.geocode_targets target ON target.job_id = job.job_id
          JOIN real_preview.candidates candidate ON candidate.candidate_id = target.candidate_id
          JOIN real_preview.candidate_private_location_evidence private_location
            ON private_location.candidate_id = candidate.candidate_id
          JOIN real_preview.private_geocoding_source_profiles profile
            ON profile.source_id = candidate.source_id AND profile.enabled
          JOIN uec.geocode_job_events queued ON queued.job_id = job.job_id
            AND queued.event_type = 'queued'
            AND queued.details->>'processing_mode' = 'private_geoapify_source_profile'
            AND queued.details->>'profile_id' = profile.profile_id
          CROSS JOIN LATERAL (SELECT NEW.response->'features'->
              CASE WHEN COALESCE(NEW.response->>'_uec_selected_feature_index','') ~ '^[0-9]+$'
                   THEN (NEW.response->>'_uec_selected_feature_index')::integer ELSE 0 END AS feature) item
         WHERE job.source_record_id = NEW.source_record_id
           AND job.provider_id = NEW.provider_id AND job.query = NEW.query
           AND profile.country_code = candidate.country_code
           AND private_location.location_evidence->>'country_code' = profile.country_code
           AND candidate.source_id = 'es.locations'
           AND profile.profile_id = 'geoapify-es-aesan-rgseaa'
           AND candidate.snapshot_sha256 = COALESCE(
               (SELECT run.snapshot_sha256 FROM real_preview.source_preview_runs run
                WHERE run.source_id = candidate.source_id
                ORDER BY run.created_at DESC,run.run_id DESC LIMIT 1),
               (SELECT manifest.snapshot_sha256 FROM real_preview.source_manifests manifest
                WHERE manifest.source_id = candidate.source_id
                ORDER BY manifest.retrieved_at DESC,manifest.snapshot_sha256 DESC LIMIT 1))
           AND NOT EXISTS (SELECT 1 FROM uec.public_access_restricted restricted
                           WHERE restricted.source_record_id = NEW.source_record_id)
         ORDER BY target.created_at DESC
         LIMIT 1;

        result_type := properties->>'result_type';
        result_country := upper(properties->>'country_code');
        confidence_text := properties#>>'{rank,confidence}';
        IF result_country <> profile_country
           OR COALESCE(confidence_text,'') !~ '^[0-9]+([.][0-9]+)?$' THEN RETURN NEW; END IF;
        confidence_score := confidence_text::DOUBLE PRECISION;
        IF confidence_score < .90 OR confidence_score > 1 THEN RETURN NEW; END IF;
        IF result_type NOT IN ('building','amenity') THEN RETURN NEW; END IF;

        result_address := COALESCE(properties->>'address_line1',
            CASE WHEN properties->>'housenumber' IS NOT NULL AND properties->>'street' IS NOT NULL
                 THEN properties->>'housenumber' || ' ' || properties->>'street' END);
        IF real_preview.normalize_geocode_address(source_address) = ''
           OR real_preview.normalize_geocode_address(result_address) = ''
           OR real_preview.normalize_geocode_address(source_address)
              <> real_preview.normalize_geocode_address(result_address) THEN RETURN NEW; END IF;

        SELECT count(*)::integer INTO viable_match_count
          FROM jsonb_array_elements(NEW.response->'features') AS features(feature)
         WHERE upper(feature->'properties'->>'country_code') = profile_country
           AND feature->'properties'->>'result_type' IN ('building','amenity')
           AND COALESCE(feature->'properties'#>>'{rank,confidence}','') ~ '^[0-9]+([.][0-9]+)?$'
           AND (feature->'properties'#>>'{rank,confidence}')::DOUBLE PRECISION BETWEEN .90 AND 1
           AND real_preview.normalize_geocode_address(
               COALESCE(feature->'properties'->>'address_line1',
                   CASE WHEN feature->'properties'->>'housenumber' IS NOT NULL
                          AND feature->'properties'->>'street' IS NOT NULL
                        THEN feature->'properties'->>'housenumber' || ' ' || feature->'properties'->>'street' END))
               = real_preview.normalize_geocode_address(source_address);
        IF viable_match_count <> 1 THEN RETURN NEW; END IF;

        precision_label := 'provider_address_point_high_confidence';
        disclosure := 'Geoapify; rank confidence >= 0.90 heuristic and accent-normalized exact source-address line match; private preview only';
        review_state := 'automated_high_confidence_private_display';
        INSERT INTO real_preview.geocode_display_evidence
            (candidate_id,geocode_result_id,display_latitude,display_longitude,
             display_precision,display_geometry_source,coordinate_review_status,
             match_confidence,match_confidence_band)
        VALUES (matched_candidate,NEW.geocode_result_id,ST_Y(NEW.result::geometry),ST_X(NEW.result::geometry),
                precision_label,disclosure,review_state,confidence_score,'high_heuristic')
        ON CONFLICT (candidate_id,geocode_result_id) DO NOTHING;
        RETURN NEW;
    END
    $function$;
END
$migration$;
