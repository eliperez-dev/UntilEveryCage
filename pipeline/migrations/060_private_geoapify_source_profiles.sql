-- Source-scoped private Geoapify processing. This adds no publication grants.
DO $$
DECLARE constraint_row record;
BEGIN
    FOR constraint_row IN
        SELECT conname
          FROM pg_constraint
         WHERE conrelid = 'real_preview.candidate_private_location_evidence'::regclass
           AND contype = 'c'
           AND (pg_get_constraintdef(oid) LIKE '%location_evidence -%'
                OR pg_get_constraintdef(oid) LIKE '%coordinates%')
    LOOP
        EXECUTE format('ALTER TABLE real_preview.candidate_private_location_evidence DROP CONSTRAINT %I', constraint_row.conname);
    END LOOP;
END $$;

ALTER TABLE real_preview.candidate_private_location_evidence
    ADD CONSTRAINT candidate_private_location_evidence_allowed_keys CHECK (
        location_evidence - ARRAY[
            'address','address_lines','city','postal_code','region','country_code','coordinates',
            'municipality_code','comarca_code','department_number','region_code'
        ] = '{}'::jsonb
    ),
    ADD CONSTRAINT candidate_private_location_evidence_coordinate_keys CHECK (
        NOT (location_evidence ? 'coordinates') OR
        (jsonb_typeof(location_evidence->'coordinates') = 'object' AND
         (location_evidence->'coordinates') - ARRAY[
             'latitude','longitude','precision','x','y','axis_labels','coordinate_reference_system'
         ] = '{}'::jsonb AND
         ((location_evidence->'coordinates' ? 'x') = (location_evidence->'coordinates' ? 'y')))
    ),
    ADD CONSTRAINT candidate_private_location_evidence_address_shape CHECK (
        (NOT (location_evidence ? 'address') OR jsonb_typeof(location_evidence->'address') IN ('string','array')) AND
        (NOT (location_evidence ? 'address_lines') OR jsonb_typeof(location_evidence->'address_lines') = 'array')
    );

CREATE TABLE real_preview.private_geocoding_source_profiles (
    profile_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL UNIQUE,
    country_code CHAR(2) NOT NULL CHECK (country_code IN ('GB','DK','NL')),
    enabled BOOLEAN NOT NULL DEFAULT true,
    source_scope TEXT NOT NULL
);

INSERT INTO real_preview.private_geocoding_source_profiles(profile_id, source_id, country_code, source_scope) VALUES
('geoapify-gb-fsa-approved-establishments', 'fsa_approved_establishments', 'GB', 'accepted non-withheld address rows; unverified source axes remain diagnostic and are not display points'),
('geoapify-gb-fss-approved-establishments', 'fss_approved_establishments', 'GB', 'accepted Food Standards Scotland address-only rows'),
('geoapify-dk-smiley', 'dk.smiley', 'DK', 'explicitly eligible, privacy-screened address-only source rows'),
('geoapify-nl-nvwa-approved-food', 'nl.nvwa.approved-food', 'NL', 'explicitly eligible, privacy-screened address-only source rows')
ON CONFLICT (profile_id) DO UPDATE SET
    source_id=EXCLUDED.source_id,
    country_code=EXCLUDED.country_code,
    source_scope=EXCLUDED.source_scope;

CREATE OR REPLACE FUNCTION real_preview.capture_geoapify_private_display()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    matched_candidate UUID;
    profile_country TEXT;
    properties JSONB;
    result_type TEXT;
    result_country TEXT;
    confidence_text TEXT;
    confidence_score DOUBLE PRECISION;
    result_address TEXT;
    result_city TEXT;
    source_address TEXT;
    source_city TEXT;
    source_country TEXT;
    precision_label TEXT;
    disclosure TEXT;
    review_state TEXT;
    matched_profile TEXT;
    viable_match_count INTEGER;
BEGIN
    IF NEW.provider_id <> 'geoapify' OR NEW.status <> 'accepted'
       OR NEW.result IS NULL OR NEW.response IS NULL THEN
        RETURN NEW;
    END IF;

    SELECT profile.profile_id, profile.country_code::text,
           target.candidate_id,
           COALESCE(private_location.location_evidence->'address_lines'->>0,
                    private_location.location_evidence->>'address'),
           COALESCE(private_location.location_evidence->>'city', candidate.city),
           private_location.location_evidence->>'country_code',
           feature->'properties'
      INTO matched_profile, profile_country, matched_candidate, source_address,
           source_city, source_country, properties
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
       AND (private_location.location_evidence->>'country_code' IS NULL
            OR private_location.location_evidence->>'country_code' = profile.country_code)
       AND (target.source_id, target.snapshot_sha256) = (candidate.source_id, candidate.snapshot_sha256)
       AND candidate.snapshot_sha256 = COALESCE(
           (SELECT run.snapshot_sha256 FROM real_preview.source_preview_runs run
            WHERE run.source_id = candidate.source_id
            ORDER BY run.created_at DESC,run.run_id DESC LIMIT 1),
           (SELECT manifest.snapshot_sha256 FROM real_preview.source_manifests manifest
            WHERE manifest.source_id = candidate.source_id
            ORDER BY manifest.retrieved_at DESC,manifest.snapshot_sha256 DESC LIMIT 1)
       )
       AND NOT EXISTS (SELECT 1 FROM uec.public_access_restricted restricted
                       WHERE restricted.source_record_id = NEW.source_record_id)
     ORDER BY target.created_at DESC
     LIMIT 1;
    IF matched_candidate IS NULL OR properties IS NULL THEN
        RETURN NEW;
    END IF;

    result_type := properties->>'result_type';
    result_country := upper(properties->>'country_code');
    confidence_text := properties#>>'{rank,confidence}';
    IF COALESCE(confidence_text, '') !~ '^[0-9]+([.][0-9]+)?$' THEN RETURN NEW; END IF;
    confidence_score := confidence_text::DOUBLE PRECISION;
    IF result_country <> profile_country OR confidence_score < 0.90 OR confidence_score > 1 THEN RETURN NEW; END IF;

    SELECT count(*)::integer INTO viable_match_count
      FROM jsonb_array_elements(NEW.response->'features') AS features(candidate_feature)
      CROSS JOIN LATERAL (SELECT candidate_feature->'properties' AS candidate_properties) item
     WHERE lower(candidate_properties->>'country_code') = lower(profile_country)
       AND COALESCE(candidate_properties#>>'{rank,confidence}', '') ~ '^[0-9]+([.][0-9]+)?$'
       AND (candidate_properties#>>'{rank,confidence}')::DOUBLE PRECISION >= 0.90
       AND (candidate_properties#>>'{rank,confidence}')::DOUBLE PRECISION <= 1
       AND (
           (candidate_properties->>'result_type' IN ('building','amenity')
            AND NULLIF(trim(source_address),'') IS NOT NULL
            AND lower(regexp_replace(trim(COALESCE(candidate_properties->>'address_line1',
                CASE WHEN candidate_properties->>'housenumber' IS NOT NULL AND candidate_properties->>'street' IS NOT NULL
                     THEN (candidate_properties->>'housenumber') || ' ' || (candidate_properties->>'street') END)),
                '[^[:alnum:]]+', ' ', 'g'))
              = lower(regexp_replace(trim(source_address), '[^[:alnum:]]+', ' ', 'g')))
           OR (candidate_properties->>'result_type' = 'city'
               AND NULLIF(trim(source_city),'') IS NOT NULL
               AND lower(regexp_replace(trim(candidate_properties->>'city'), '[^[:alnum:]]+', ' ', 'g'))
                   = lower(regexp_replace(trim(source_city), '[^[:alnum:]]+', ' ', 'g')))
       );
    IF viable_match_count <> 1 THEN RETURN NEW; END IF;

    IF result_type IN ('building', 'amenity') THEN
        result_address := COALESCE(properties->>'address_line1',
            CASE WHEN properties->>'housenumber' IS NOT NULL AND properties->>'street' IS NOT NULL
                 THEN (properties->>'housenumber') || ' ' || (properties->>'street') END);
        IF NULLIF(trim(source_address), '') IS NULL OR NULLIF(trim(result_address), '') IS NULL
           OR lower(regexp_replace(trim(source_address), '[^[:alnum:]]+', ' ', 'g'))
              <> lower(regexp_replace(trim(result_address), '[^[:alnum:]]+', ' ', 'g')) THEN RETURN NEW; END IF;
        precision_label := 'provider_address_point_high_confidence';
        disclosure := 'Geoapify; rank confidence >= 0.90 heuristic and normalized source-address line match; private preview only';
        review_state := 'automated_high_confidence_private_display';
    ELSIF result_type = 'city' THEN
        result_city := lower(regexp_replace(trim(properties->>'city'), '[^[:alnum:]]+', ' ', 'g'));
        IF result_city = '' OR NULLIF(trim(source_city), '') IS NULL
           OR lower(regexp_replace(trim(source_city), '[^[:alnum:]]+', ' ', 'g')) <> result_city THEN RETURN NEW; END IF;
        precision_label := 'provider_locality_approximate';
        disclosure := 'Geoapify; rank confidence >= 0.90 heuristic and source locality match; approximate city point, not facility coordinates; private preview only';
        review_state := 'approximate_provider_locality_private_display';
    ELSE
        RETURN NEW;
    END IF;

    INSERT INTO real_preview.geocode_display_evidence
        (candidate_id, geocode_result_id, display_latitude, display_longitude,
         display_precision, display_geometry_source, coordinate_review_status,
         match_confidence, match_confidence_band)
    VALUES (matched_candidate, NEW.geocode_result_id,
            ST_Y(NEW.result::geometry), ST_X(NEW.result::geometry),
            precision_label, disclosure, review_state, confidence_score, 'high_heuristic')
    ON CONFLICT (candidate_id, geocode_result_id) DO NOTHING;
    RETURN NEW;
END;
$$;

COMMENT ON TABLE real_preview.private_geocoding_source_profiles IS
    'Explicit source/country allowlist for private Geoapify processing; never grants project approval or publication.';
