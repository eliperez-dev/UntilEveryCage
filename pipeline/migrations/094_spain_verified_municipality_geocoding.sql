-- Add a second, municipality-only Geoapify profile for AESAN records with
-- append-only source-key evidence. The address profile and shared bridge stay
-- unchanged; this branch emits approximate municipality points only.
DO $migration$
BEGIN
    IF to_regnamespace('real_preview') IS NULL
       OR to_regclass('real_preview.private_geocoding_source_profiles') IS NULL
       OR to_regclass('real_preview.spain_verified_locality_evidence') IS NULL
       OR to_regprocedure('real_preview.reject_mutation()') IS NULL THEN
        RETURN;
    END IF;

    ALTER TABLE real_preview.private_geocoding_source_profiles
        DROP CONSTRAINT IF EXISTS private_geocoding_source_profiles_source_id_key;
    CREATE UNIQUE INDEX IF NOT EXISTS private_geocoding_source_profiles_one_non_es_profile
        ON real_preview.private_geocoding_source_profiles(source_id)
        WHERE source_id <> 'es.locations';

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conrelid='real_preview.private_geocoding_source_profiles'::regclass
           AND conname='private_geocoding_source_profiles_spain_profile_scope'
    ) THEN
        ALTER TABLE real_preview.private_geocoding_source_profiles
            ADD CONSTRAINT private_geocoding_source_profiles_spain_profile_scope CHECK (
                (source_id='es.locations' AND country_code='ES'
                 AND profile_id IN ('geoapify-es-aesan-rgseaa',
                                    'geoapify-es-aesan-verified-municipality'))
                OR (source_id <> 'es.locations'
                    AND profile_id NOT IN ('geoapify-es-aesan-rgseaa',
                                           'geoapify-es-aesan-verified-municipality'))
            );
    END IF;

    INSERT INTO real_preview.private_geocoding_source_profiles
        (profile_id,source_id,country_code,enabled,source_scope)
    VALUES
        ('geoapify-es-aesan-verified-municipality','es.locations','ES',true,
         'AESAN registration-key verified municipality and province only; query municipality, province, Spain; accepted city points are approximate municipality references, never facility coordinates')
    ON CONFLICT (profile_id) DO UPDATE SET
        source_id=EXCLUDED.source_id,
        country_code=EXCLUDED.country_code,
        source_scope=EXCLUDED.source_scope,
        enabled=true;

    CREATE OR REPLACE FUNCTION real_preview.capture_spain_verified_municipality_display()
    RETURNS trigger LANGUAGE plpgsql AS $function$
    DECLARE
        matched_candidate UUID;
        properties JSONB;
        evidence_municipality TEXT;
        evidence_province TEXT;
        confidence_text TEXT;
        confidence_score DOUBLE PRECISION;
        result_country TEXT;
        result_type TEXT;
        viable_match_count INTEGER;
        query_parts TEXT[];
    BEGIN
        IF NEW.provider_id <> 'geoapify' OR NEW.status <> 'accepted'
           OR NEW.result IS NULL OR NEW.response IS NULL THEN
            RETURN NEW;
        END IF;

        query_parts := string_to_array(NEW.query, ',');
        IF cardinality(query_parts) <> 3
           OR real_preview.normalize_geocode_address(query_parts[3]) <> 'spain' THEN
            RETURN NEW;
        END IF;

        SELECT target.candidate_id,evidence.municipality,evidence.province,
               feature->'properties'
          INTO matched_candidate,evidence_municipality,evidence_province,properties
          FROM uec.geocode_jobs job
          JOIN real_preview.geocode_targets target ON target.job_id=job.job_id
          JOIN real_preview.candidates candidate ON candidate.candidate_id=target.candidate_id
          JOIN real_preview.candidate_private_location_evidence location
            ON location.candidate_id=candidate.candidate_id
          JOIN real_preview.private_geocoding_source_profiles profile
            ON profile.profile_id='geoapify-es-aesan-verified-municipality'
           AND profile.source_id=candidate.source_id AND profile.enabled
          JOIN real_preview.spain_verified_locality_evidence evidence
            ON evidence.candidate_id=candidate.candidate_id
           AND evidence.snapshot_sha256=candidate.snapshot_sha256
           AND evidence.source_id=candidate.source_id
          JOIN uec.geocode_job_events queued ON queued.job_id=job.job_id
            AND queued.event_type='queued'
            AND queued.details->>'processing_mode'='private_geoapify_source_profile'
            AND queued.details->>'profile_id'=profile.profile_id
            AND queued.details->>'locality_evidence_event_id'=evidence.evidence_event_id::text
          CROSS JOIN LATERAL (SELECT NEW.response->'features'->
              CASE WHEN COALESCE(NEW.response->>'_uec_selected_feature_index','') ~ '^[0-9]+$'
                   THEN (NEW.response->>'_uec_selected_feature_index')::integer ELSE 0 END AS feature) item
         WHERE job.source_record_id=NEW.source_record_id
           AND job.provider_id=NEW.provider_id AND job.query=NEW.query
           AND candidate.source_id='es.locations' AND candidate.country_code='ES'
           AND location.location_evidence->>'country_code'='ES'
           AND candidate.snapshot_sha256=COALESCE(
               (SELECT run.snapshot_sha256 FROM real_preview.source_preview_runs run
                WHERE run.source_id='es.locations'
                ORDER BY run.created_at DESC,run.run_id DESC LIMIT 1),
               (SELECT manifest.snapshot_sha256 FROM real_preview.source_manifests manifest
                WHERE manifest.source_id='es.locations'
                ORDER BY manifest.retrieved_at DESC,manifest.snapshot_sha256 DESC LIMIT 1))
           AND NOT EXISTS (SELECT 1 FROM uec.public_access_restricted restricted
                           WHERE restricted.source_record_id=NEW.source_record_id)
           AND NOT EXISTS (
               SELECT 1 FROM real_preview.spain_verified_locality_evidence newer
                WHERE newer.candidate_id=evidence.candidate_id
                  AND newer.snapshot_sha256=evidence.snapshot_sha256
                  AND (newer.retrieved_at,newer.evidence_event_id)
                      > (evidence.retrieved_at,evidence.evidence_event_id)
           )
           AND real_preview.normalize_geocode_address(query_parts[1])
                 = real_preview.normalize_geocode_address(evidence.municipality)
           AND real_preview.normalize_geocode_address(query_parts[2])
                 = real_preview.normalize_geocode_address(evidence.province)
         ORDER BY evidence.retrieved_at DESC,evidence.evidence_event_id DESC
         LIMIT 1;
        IF matched_candidate IS NULL OR properties IS NULL THEN RETURN NEW; END IF;

        result_type := properties->>'result_type';
        result_country := upper(properties->>'country_code');
        confidence_text := properties#>>'{rank,confidence}';
        IF result_type <> 'city' OR result_country <> 'ES'
           OR COALESCE(confidence_text,'') !~ '^[0-9]+([.][0-9]+)?$' THEN
            RETURN NEW;
        END IF;
        confidence_score := confidence_text::DOUBLE PRECISION;
        IF confidence_score < .90 OR confidence_score > 1
           OR real_preview.normalize_geocode_address(properties->>'city')
                <> real_preview.normalize_geocode_address(evidence_municipality)
           OR real_preview.normalize_geocode_address(properties->>'county')
                <> real_preview.normalize_geocode_address(evidence_province) THEN
            RETURN NEW;
        END IF;

        SELECT count(*)::integer INTO viable_match_count
          FROM jsonb_array_elements(NEW.response->'features') AS items(feature)
         WHERE feature->'properties'->>'result_type'='city'
           AND upper(feature->'properties'->>'country_code')='ES'
           AND COALESCE(feature->'properties'#>>'{rank,confidence}','') ~ '^[0-9]+([.][0-9]+)?$'
           AND (feature->'properties'#>>'{rank,confidence}')::DOUBLE PRECISION BETWEEN .90 AND 1
           AND real_preview.normalize_geocode_address(feature->'properties'->>'city')
                 = real_preview.normalize_geocode_address(evidence_municipality)
           AND real_preview.normalize_geocode_address(feature->'properties'->>'county')
                 = real_preview.normalize_geocode_address(evidence_province);
        IF viable_match_count <> 1 THEN RETURN NEW; END IF;

        INSERT INTO real_preview.geocode_display_evidence
            (candidate_id,geocode_result_id,display_latitude,display_longitude,
             display_precision,display_geometry_source,coordinate_review_status,
             match_confidence,match_confidence_band)
        VALUES (matched_candidate,NEW.geocode_result_id,
                ST_Y(NEW.result::geometry),ST_X(NEW.result::geometry),
                'provider_locality_approximate',
                'Geoapify; rank confidence >= 0.90 heuristic and exact AESAN verified municipality/province match; approximate municipality point, not facility coordinates; private preview only',
                'approximate_provider_locality_private_display',confidence_score,'high_heuristic')
        ON CONFLICT (candidate_id,geocode_result_id) DO NOTHING;
        RETURN NEW;
    END
    $function$;

    DROP TRIGGER IF EXISTS geocode_results_spain_verified_municipality_display
        ON uec.geocode_results;
    CREATE TRIGGER geocode_results_spain_verified_municipality_display
        AFTER INSERT ON uec.geocode_results
        FOR EACH ROW EXECUTE FUNCTION real_preview.capture_spain_verified_municipality_display();
END
$migration$;
