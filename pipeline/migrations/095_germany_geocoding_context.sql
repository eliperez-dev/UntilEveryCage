-- Germany-only Geoapify display bridge. Keep the shared GB/DK/NL/US bridge
-- unchanged; this source needs postcode and locality context from BVL's Ort.
DO $migration$
DECLARE
    generic_definition TEXT;
    generic_join TEXT := 'ON profile.source_id = candidate.source_id AND profile.enabled';
    german_join TEXT := 'ON profile.source_id = candidate.source_id AND profile.enabled AND profile.profile_id <> ''geoapify-de-bltu''';
BEGIN
    IF to_regnamespace('real_preview') IS NULL
       OR to_regclass('real_preview.private_geocoding_source_profiles') IS NULL THEN
        RETURN;
    END IF;

    ALTER TABLE real_preview.private_geocoding_source_profiles
        DROP CONSTRAINT IF EXISTS private_geocoding_source_profiles_country_code_check;
    ALTER TABLE real_preview.private_geocoding_source_profiles
        ADD CONSTRAINT private_geocoding_source_profiles_country_code_check
        CHECK (country_code IN ('GB','DK','NL','US','ES','DE'));

    INSERT INTO real_preview.private_geocoding_source_profiles
        (profile_id, source_id, country_code, enabled, source_scope)
    VALUES ('geoapify-de-bltu','de.locations','DE',true,
            'Current BVL BLtU business street-address candidates with exact five-digit postcode and locality context; private processing only')
    ON CONFLICT (profile_id) DO UPDATE SET
        source_id=EXCLUDED.source_id,country_code=EXCLUDED.country_code,
        enabled=true,source_scope=EXCLUDED.source_scope;

    CREATE OR REPLACE FUNCTION real_preview.normalize_germany_geocode_text(input_text TEXT)
    RETURNS TEXT LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $function$
        SELECT trim(regexp_replace(
            translate(replace(lower(coalesce(input_text,'')),'ß','ss'), 'äöü', 'aou'),
            '[^[:alnum:]]+', ' ', 'g'))
    $function$;

    CREATE OR REPLACE FUNCTION real_preview.normalize_germany_state(input_text TEXT)
    RETURNS TEXT LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $function$
        SELECT CASE real_preview.normalize_germany_geocode_text(input_text)
            WHEN 'baden wurttemberg' THEN 'bw' WHEN 'bayern' THEN 'by'
            WHEN 'berlin' THEN 'be' WHEN 'brandenburg' THEN 'bb' WHEN 'bremen' THEN 'hb'
            WHEN 'hamburg' THEN 'hh' WHEN 'hessen' THEN 'he'
            WHEN 'mecklenburg vorpommern' THEN 'mv' WHEN 'niedersachsen' THEN 'ni'
            WHEN 'nordrhein westfalen' THEN 'nw' WHEN 'rheinland pfalz' THEN 'rp'
            WHEN 'saarland' THEN 'sl' WHEN 'sachsen' THEN 'sn'
            WHEN 'sachsen anhalt' THEN 'st' WHEN 'schleswig holstein' THEN 'sh'
            WHEN 'thuringen' THEN 'th'
            ELSE regexp_replace(real_preview.normalize_germany_geocode_text(input_text),'^de ','') END
    $function$;

    -- Preserve the installed generic trigger body byte-for-byte except for a
    -- guarded exclusion of the DE profile. This leaves every other country on
    -- the previously verified implementation.
    generic_definition := pg_get_functiondef('real_preview.capture_geoapify_private_display()'::regprocedure);
    IF md5(generic_definition) <> '3a11e2f75ee9bd2adefae58c0f50aebf' THEN
        RAISE EXCEPTION 'generic Geoapify display function differs from reviewed baseline';
    END IF;
    IF length(generic_definition)-length(replace(generic_definition,generic_join,'')) <> length(generic_join) THEN
        RAISE EXCEPTION 'generic Geoapify profile join replacement is not unique';
    END IF;
    EXECUTE replace(generic_definition,generic_join,german_join);

    CREATE OR REPLACE FUNCTION real_preview.capture_germany_geoapify_private_display()
    RETURNS trigger LANGUAGE plpgsql AS $function$
    DECLARE
        matched_candidate UUID;
        source_address TEXT;
        source_city TEXT;
        source_postcode TEXT;
        source_region TEXT;
        properties JSONB;
        selected_feature JSONB;
        confidence DOUBLE PRECISION;
        feature JSONB;
        feature_props JSONB;
        viable_count INTEGER := 0;
        result_address TEXT;
        result_postcode TEXT;
        result_city TEXT;
        result_region TEXT;
    BEGIN
        IF NEW.provider_id <> 'geoapify' OR NEW.status <> 'accepted'
           OR NEW.result IS NULL OR NEW.response IS NULL THEN RETURN NEW; END IF;

        SELECT target.candidate_id,
               COALESCE(location.location_evidence->'address_lines'->>0,
                        location.location_evidence->>'address'),
               COALESCE(location.location_evidence->>'city',candidate.city),
               COALESCE(location.location_evidence->>'postal_code',
                        (regexp_match(COALESCE(location.location_evidence->>'city',candidate.city),
                                      '^([0-9]{5})[[:space:]]+'))[1]),
               location.location_evidence->>'region',
               NEW.response->'features'->CASE
                   WHEN COALESCE(NEW.response->>'_uec_selected_feature_index','') ~ '^[0-9]+$'
                   THEN (NEW.response->>'_uec_selected_feature_index')::integer ELSE 0 END
          INTO matched_candidate,source_address,source_city,source_postcode,source_region,selected_feature
          FROM uec.geocode_jobs job
          JOIN real_preview.geocode_targets target ON target.job_id=job.job_id
          JOIN real_preview.candidates candidate ON candidate.candidate_id=target.candidate_id
          JOIN real_preview.candidate_private_location_evidence location ON location.candidate_id=candidate.candidate_id
          JOIN real_preview.private_geocoding_source_profiles profile
            ON profile.source_id=candidate.source_id AND profile.profile_id='geoapify-de-bltu' AND profile.enabled
          JOIN uec.geocode_job_events queued ON queued.job_id=job.job_id
            AND queued.event_type='queued'
            AND queued.details->>'processing_mode'='private_geoapify_source_profile'
            AND queued.details->>'profile_id'=profile.profile_id
         WHERE job.source_record_id=NEW.source_record_id AND job.provider_id=NEW.provider_id AND job.query=NEW.query
           AND candidate.source_id='de.locations' AND candidate.country_code='DE'
           AND target.snapshot_sha256=candidate.snapshot_sha256
           AND candidate.snapshot_sha256=COALESCE(
               (SELECT run.snapshot_sha256 FROM real_preview.source_preview_runs run
                 WHERE run.source_id=candidate.source_id ORDER BY run.created_at DESC,run.run_id DESC LIMIT 1),
               (SELECT manifest.snapshot_sha256 FROM real_preview.source_manifests manifest
                 WHERE manifest.source_id=candidate.source_id ORDER BY manifest.retrieved_at DESC,manifest.snapshot_sha256 DESC LIMIT 1))
           AND NOT EXISTS (SELECT 1 FROM uec.public_access_restricted restricted
                            WHERE restricted.source_record_id=NEW.source_record_id)
         ORDER BY target.created_at DESC LIMIT 1;

        IF matched_candidate IS NULL OR jsonb_typeof(selected_feature) <> 'object'
           OR COALESCE(source_postcode,'') !~ '^[0-9]{5}$'
           OR NULLIF(trim(source_city),'') IS NULL OR NULLIF(trim(source_address),'') IS NULL THEN RETURN NEW; END IF;

        properties := selected_feature->'properties';
        IF upper(properties->>'country_code') <> 'DE'
           OR properties->>'result_type' NOT IN ('building','amenity')
           OR COALESCE(properties#>>'{rank,confidence}','') !~ '^[0-9]+([.][0-9]+)?$' THEN RETURN NEW; END IF;
        confidence := (properties#>>'{rank,confidence}')::DOUBLE PRECISION;
        IF confidence < .90 OR confidence > 1 THEN RETURN NEW; END IF;

        result_address := COALESCE(properties->>'address_line1',
            CASE WHEN properties->>'housenumber' IS NOT NULL AND properties->>'street' IS NOT NULL
                 THEN (properties->>'housenumber') || ' ' || (properties->>'street') END);
        result_postcode := properties->>'postcode';
        result_city := COALESCE(properties->>'city',properties->>'town',properties->>'municipality',properties->>'village');
        result_region := COALESCE(properties->>'state_code',properties->>'state');
        IF real_preview.normalize_germany_geocode_text(result_address) = ''
           OR real_preview.normalize_germany_geocode_text(result_address)
                <> real_preview.normalize_germany_geocode_text(source_address)
           OR regexp_replace(COALESCE(result_postcode,''),'[[:space:]]','','g') <> source_postcode
           OR NOT EXISTS(SELECT 1 FROM (VALUES(properties->>'city'),(properties->>'town'),
                (properties->>'municipality'),(properties->>'village')) AS loc(value)
                WHERE real_preview.normalize_germany_geocode_text(loc.value)
                    =real_preview.normalize_germany_geocode_text(regexp_replace(source_city,'^[0-9]{5}[[:space:]]+',''))) THEN RETURN NEW; END IF;
        IF NULLIF(trim(result_region),'') IS NOT NULL AND NULLIF(trim(source_region),'') IS NOT NULL
           AND real_preview.normalize_germany_state(result_region)
                <>real_preview.normalize_germany_state(source_region) THEN RETURN NEW; END IF;

        FOR feature IN SELECT value FROM jsonb_array_elements(NEW.response->'features') LOOP
            feature_props := feature->'properties';
            IF upper(feature_props->>'country_code')='DE'
               AND feature_props->>'result_type' IN ('building','amenity')
               AND COALESCE(feature_props#>>'{rank,confidence}','') ~ '^[0-9]+([.][0-9]+)?$'
               AND (feature_props#>>'{rank,confidence}')::DOUBLE PRECISION BETWEEN .90 AND 1
               AND real_preview.normalize_germany_geocode_text(COALESCE(feature_props->>'address_line1',
                   CASE WHEN feature_props->>'housenumber' IS NOT NULL AND feature_props->>'street' IS NOT NULL
                        THEN (feature_props->>'housenumber') || ' ' || (feature_props->>'street') END))
                    = real_preview.normalize_germany_geocode_text(source_address)
               AND regexp_replace(COALESCE(feature_props->>'postcode',''),'[[:space:]]','','g')=source_postcode
               AND EXISTS(SELECT 1 FROM (VALUES(feature_props->>'city'),(feature_props->>'town'),
                    (feature_props->>'municipality'),(feature_props->>'village')) AS loc(value)
                    WHERE real_preview.normalize_germany_geocode_text(loc.value)
                        =real_preview.normalize_germany_geocode_text(regexp_replace(source_city,'^[0-9]{5}[[:space:]]+','')))
               AND (NULLIF(trim(COALESCE(feature_props->>'state_code',feature_props->>'state')),'') IS NULL
                    OR NULLIF(trim(source_region),'') IS NULL
                    OR real_preview.normalize_germany_state(COALESCE(feature_props->>'state_code',feature_props->>'state'))
                        =real_preview.normalize_germany_state(source_region)) THEN
                viable_count := viable_count+1;
            END IF;
        END LOOP;
        IF viable_count <> 1 THEN RETURN NEW; END IF;

        INSERT INTO real_preview.germany_geocode_context_audit
            (candidate_id,snapshot_sha256,geocode_result_id,outcome)
        SELECT matched_candidate,candidate.snapshot_sha256,NEW.geocode_result_id,'matched'
          FROM real_preview.candidates candidate
         WHERE candidate.candidate_id=matched_candidate
        ON CONFLICT(candidate_id,geocode_result_id) DO NOTHING;

        INSERT INTO real_preview.geocode_display_evidence
            (candidate_id,geocode_result_id,display_latitude,display_longitude,
             display_precision,display_geometry_source,coordinate_review_status,
             match_confidence,match_confidence_band)
        VALUES (matched_candidate,NEW.geocode_result_id,ST_Y(NEW.result::geometry),ST_X(NEW.result::geometry),
                'provider_address_point_high_confidence',
                'Geoapify; rank confidence >= 0.90 heuristic and normalized source-address line match; exact postcode and locality context; private preview only',
                'automated_high_confidence_private_display',confidence,'high_heuristic')
        ON CONFLICT (candidate_id,geocode_result_id) DO NOTHING;
        RETURN NEW;
    END
    $function$;

    DROP TRIGGER IF EXISTS geocode_results_germany_geoapify_private_display ON uec.geocode_results;
    CREATE TRIGGER geocode_results_germany_geoapify_private_display
        AFTER INSERT ON uec.geocode_results
        FOR EACH ROW EXECUTE FUNCTION real_preview.capture_germany_geoapify_private_display();

    CREATE TABLE real_preview.germany_geocode_context_audit (
        audit_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        candidate_id UUID NOT NULL REFERENCES real_preview.candidates(candidate_id),
        snapshot_sha256 CHAR(64) NOT NULL,
        geocode_result_id UUID NOT NULL REFERENCES uec.geocode_results(geocode_result_id),
        outcome TEXT NOT NULL CHECK (outcome IN ('matched','country_mismatch','confidence_or_precision_mismatch',
            'address_mismatch','postcode_mismatch','locality_mismatch','state_mismatch','ambiguous')),
        audited_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        UNIQUE(candidate_id,geocode_result_id)
    );
    CREATE INDEX germany_geocode_context_audit_latest_idx
        ON real_preview.germany_geocode_context_audit(candidate_id,audited_at DESC,audit_id DESC);
    CREATE TRIGGER germany_geocode_context_audit_immutable
        BEFORE UPDATE OR DELETE ON real_preview.germany_geocode_context_audit
        FOR EACH ROW EXECUTE FUNCTION real_preview.reject_mutation();

    -- Reconcile already retained responses without mutating their immutable
    -- provider rows. The audit contains statuses only, never source values.
    WITH current_candidates AS (
        SELECT candidate.candidate_id,candidate.snapshot_sha256,candidate.source_id,candidate.country_code,
               candidate.city,location.location_evidence,
               COALESCE(location.location_evidence->'address_lines'->>0,location.location_evidence->>'address') AS source_address,
               COALESCE(location.location_evidence->>'postal_code',
                   (regexp_match(COALESCE(location.location_evidence->>'city',candidate.city),'^([0-9]{5})[[:space:]]+'))[1]) AS source_postcode,
               regexp_replace(COALESCE(location.location_evidence->>'city',candidate.city),'^[0-9]{5}[[:space:]]+','') AS source_city
          FROM real_preview.candidates candidate
          JOIN real_preview.candidate_private_location_evidence location USING(candidate_id)
         WHERE candidate.source_id='de.locations' AND candidate.country_code='DE'
           AND candidate.snapshot_sha256=COALESCE(
               (SELECT run.snapshot_sha256 FROM real_preview.source_preview_runs run WHERE run.source_id='de.locations'
                ORDER BY run.created_at DESC,run.run_id DESC LIMIT 1),
               (SELECT manifest.snapshot_sha256 FROM real_preview.source_manifests manifest WHERE manifest.source_id='de.locations'
                ORDER BY manifest.retrieved_at DESC,manifest.snapshot_sha256 DESC LIMIT 1))
    ), retained AS (
        SELECT candidate.candidate_id,candidate.snapshot_sha256,result.geocode_result_id,result.response,
               result.result, result.status, candidate.source_address,candidate.source_postcode,
               candidate.source_city,candidate.location_evidence->>'region' AS source_region,
               result.response->'features'->CASE
                   WHEN COALESCE(result.response->>'_uec_selected_feature_index','') ~ '^[0-9]+$'
                   THEN (result.response->>'_uec_selected_feature_index')::integer ELSE 0 END->'properties' AS properties
          FROM current_candidates candidate
          JOIN real_preview.geocode_targets target ON target.candidate_id=candidate.candidate_id
          JOIN uec.geocode_jobs job ON job.job_id=target.job_id
          JOIN uec.geocode_job_events queued ON queued.job_id=job.job_id AND queued.event_type='queued'
            AND queued.details->>'processing_mode'='private_geoapify_source_profile'
            AND queued.details->>'profile_id'='geoapify-de-bltu'
          JOIN uec.geocode_results result ON result.source_record_id=job.source_record_id
            AND result.provider_id='geoapify' AND result.query=job.query
         WHERE target.snapshot_sha256=candidate.snapshot_sha256
           AND NOT EXISTS(SELECT 1 FROM uec.public_access_restricted restricted
                           WHERE restricted.source_record_id=result.source_record_id)
    ), assessed AS (
        SELECT retained.*,
               COALESCE(properties->>'address_line1',
                   CASE WHEN properties->>'housenumber' IS NOT NULL AND properties->>'street' IS NOT NULL
                        THEN (properties->>'housenumber')||' '||(properties->>'street') END) AS result_address,
               regexp_replace(COALESCE(properties->>'postcode',''),'[[:space:]]','','g') AS result_postcode,
               COALESCE(properties->>'city',properties->>'town',properties->>'municipality',properties->>'village') AS result_city,
               COALESCE(properties->>'state_code',properties->>'state') AS result_region,
               (SELECT count(*) FROM jsonb_array_elements(response->'features') AS feature
                 WHERE upper(feature->'properties'->>'country_code')='DE'
                   AND feature->'properties'->>'result_type' IN ('building','amenity')
                   AND COALESCE(feature->'properties'#>>'{rank,confidence}','') ~ '^[0-9]+([.][0-9]+)?$'
                   AND (feature->'properties'#>>'{rank,confidence}')::DOUBLE PRECISION BETWEEN .90 AND 1
                   AND real_preview.normalize_germany_geocode_text(COALESCE(feature->'properties'->>'address_line1',
                       CASE WHEN feature->'properties'->>'housenumber' IS NOT NULL AND feature->'properties'->>'street' IS NOT NULL
                            THEN (feature->'properties'->>'housenumber')||' '||(feature->'properties'->>'street') END))
                       =real_preview.normalize_germany_geocode_text(source_address)
                   AND regexp_replace(COALESCE(feature->'properties'->>'postcode',''),'[[:space:]]','','g')=source_postcode
                   AND EXISTS(SELECT 1 FROM (VALUES(feature->'properties'->>'city'),(feature->'properties'->>'town'),
                       (feature->'properties'->>'municipality'),(feature->'properties'->>'village')) AS loc(value)
                       WHERE real_preview.normalize_germany_geocode_text(loc.value)
                           =real_preview.normalize_germany_geocode_text(source_city))
                   AND (NULLIF(trim(COALESCE(feature->'properties'->>'state_code',feature->'properties'->>'state')),'') IS NULL
                        OR NULLIF(trim(source_region),'') IS NULL
                        OR real_preview.normalize_germany_state(COALESCE(feature->'properties'->>'state_code',feature->'properties'->>'state'))
                            =real_preview.normalize_germany_state(source_region))) AS viable_count
          FROM retained
    ), outcomes AS (
        SELECT *,CASE
            WHEN status<>'accepted' OR properties IS NULL OR properties->>'result_type' NOT IN ('building','amenity')
                 OR COALESCE(properties#>>'{rank,confidence}','') !~ '^[0-9]+([.][0-9]+)?$'
                 OR (properties#>>'{rank,confidence}')::DOUBLE PRECISION NOT BETWEEN .90 AND 1
                 OR (result)::geometry IS NULL THEN 'confidence_or_precision_mismatch'
            WHEN upper(properties->>'country_code')<>'DE' THEN 'country_mismatch'
            WHEN real_preview.normalize_germany_geocode_text(result_address)
                 <>real_preview.normalize_germany_geocode_text(source_address) THEN 'address_mismatch'
            WHEN result_postcode<>source_postcode THEN 'postcode_mismatch'
            WHEN NOT EXISTS(SELECT 1 FROM (VALUES(properties->>'city'),(properties->>'town'),
                 (properties->>'municipality'),(properties->>'village')) AS loc(value)
                 WHERE real_preview.normalize_germany_geocode_text(loc.value)
                     =real_preview.normalize_germany_geocode_text(source_city)) THEN 'locality_mismatch'
            WHEN NULLIF(trim(COALESCE(properties->>'state_code',properties->>'state')),'') IS NOT NULL
                 AND NULLIF(trim(source_region),'') IS NOT NULL
                 AND real_preview.normalize_germany_state(COALESCE(properties->>'state_code',properties->>'state'))
                     <>real_preview.normalize_germany_state(source_region) THEN 'state_mismatch'
            WHEN viable_count<>1 THEN 'ambiguous'
            ELSE 'matched' END AS outcome
          FROM assessed
    )
    INSERT INTO real_preview.germany_geocode_context_audit(candidate_id,snapshot_sha256,geocode_result_id,outcome)
    SELECT candidate_id,snapshot_sha256,geocode_result_id,outcome FROM outcomes
    ON CONFLICT(candidate_id,geocode_result_id) DO NOTHING;

    -- Insert display evidence for old accepted matches that the prior shared
    -- bridge withheld (notably Unicode casefold cases). No provider call and
    -- no source/provider response row is changed.
    INSERT INTO real_preview.geocode_display_evidence
        (candidate_id,geocode_result_id,display_latitude,display_longitude,display_precision,
         display_geometry_source,coordinate_review_status,match_confidence,match_confidence_band)
    SELECT audit.candidate_id,result.geocode_result_id,ST_Y(result.result::geometry),ST_X(result.result::geometry),
           'provider_address_point_high_confidence',
           'Geoapify; rank confidence >= 0.90 heuristic and normalized source-address line match; exact postcode and locality context; private preview only',
           'automated_high_confidence_private_display',
           ((result.response->'features'->CASE
               WHEN COALESCE(result.response->>'_uec_selected_feature_index','') ~ '^[0-9]+$'
               THEN (result.response->>'_uec_selected_feature_index')::integer ELSE 0 END
             ->'properties')#>>'{rank,confidence}')::DOUBLE PRECISION,'high_heuristic'
      FROM real_preview.germany_geocode_context_audit audit
      JOIN uec.geocode_results result USING(geocode_result_id)
     WHERE audit.outcome='matched'
       AND result.status='accepted'
       AND result.result IS NOT NULL
       AND NOT EXISTS(SELECT 1 FROM real_preview.geocode_display_evidence existing
                      WHERE existing.candidate_id=audit.candidate_id
                        AND existing.geocode_result_id=audit.geocode_result_id)
    ON CONFLICT(candidate_id,geocode_result_id) DO NOTHING;

    CREATE OR REPLACE VIEW real_preview.candidate_display AS
    SELECT candidate.candidate_id,candidate.snapshot_sha256,candidate.source_id,
           candidate.location_class,candidate.country_code,candidate.city,candidate.postal_code,
           candidate.latitude,candidate.longitude,candidate.coordinate_precision,
           COALESCE(reference.reference_latitude,german.display_latitude,
               CASE WHEN candidate.source_id='de.locations'
                    AND candidate.location_class <> 'numeric_source_coordinate' THEN NULL
                    ELSE candidate.display_latitude END) AS display_latitude,
           COALESCE(reference.reference_longitude,german.display_longitude,
               CASE WHEN candidate.source_id='de.locations'
                    AND candidate.location_class <> 'numeric_source_coordinate' THEN NULL
                    ELSE candidate.display_longitude END) AS display_longitude,
           COALESCE(reference.display_geometry_source,german.display_geometry_source,
               CASE WHEN candidate.source_id='de.locations'
                    AND candidate.location_class <> 'numeric_source_coordinate' THEN NULL
                    ELSE candidate.display_geometry_source END) AS display_geometry_source
      FROM real_preview.candidates candidate
      LEFT JOIN LATERAL (
          SELECT reference_latitude,reference_longitude,display_geometry_source
            FROM real_preview.local_reference_display_evidence
           WHERE candidate_id=candidate.candidate_id
           ORDER BY created_at DESC,evidence_id DESC LIMIT 1
      ) reference ON true
      LEFT JOIN LATERAL (
          SELECT evidence.display_latitude,evidence.display_longitude,evidence.display_geometry_source
            FROM real_preview.geocode_display_evidence evidence
            JOIN real_preview.germany_geocode_context_audit audit
              ON audit.candidate_id=evidence.candidate_id AND audit.geocode_result_id=evidence.geocode_result_id
             AND audit.outcome='matched'
           WHERE evidence.candidate_id=candidate.candidate_id AND candidate.source_id='de.locations'
           ORDER BY evidence.created_at DESC,evidence.evidence_id DESC LIMIT 1
      ) german ON true;
END
$migration$;
