-- Add a narrowly scoped private APHIS mailing-locality Geoapify profile.
-- This grants neither an operating-site assertion nor publication eligibility.
ALTER TABLE real_preview.private_geocoding_source_profiles
    DROP CONSTRAINT IF EXISTS private_geocoding_source_profiles_country_code_check;
ALTER TABLE real_preview.private_geocoding_source_profiles
    ADD CONSTRAINT private_geocoding_source_profiles_country_code_check
    CHECK (country_code IN ('GB','DK','NL','US'));

INSERT INTO real_preview.private_geocoding_source_profiles
    (profile_id, source_id, country_code, enabled, source_scope)
VALUES
    ('geoapify-us-aphis-mailing-locality', 'us.aphis', 'US', true,
     'Active-register mailing city/state only; accepted city result is approximate mailing locality, never operating-site or facility coordinates')
ON CONFLICT (profile_id) DO UPDATE SET
    source_id=EXCLUDED.source_id,
    country_code=EXCLUDED.country_code,
    source_scope=EXCLUDED.source_scope,
    enabled=true;

COMMENT ON TABLE real_preview.private_geocoding_source_profiles IS
    'Explicit source/country allowlist for private Geoapify processing; APHIS US is mailing-locality-only and never establishes an operating site, project approval, or publication.';

-- The historical shared trigger deliberately selects one target.  APHIS jobs
-- are locality-deduplicated and can have many targets, so insert an explicit
-- APHIS evidence row for every current eligible target first.  The existing
-- shared trigger then sees its normal uniqueness conflicts and preserves its
-- behaviour for all other profiles and the AU lane.
CREATE OR REPLACE FUNCTION real_preview.capture_aphis_mailing_locality_display()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    selected_properties JSONB;
    selected_country TEXT;
    selected_city TEXT;
    selected_state TEXT;
    confidence_text TEXT;
    confidence_score DOUBLE PRECISION;
    viable_count INTEGER;
    target_row record;
BEGIN
    IF NEW.provider_id <> 'geoapify' OR NEW.status <> 'accepted'
       OR NEW.result IS NULL OR NEW.response IS NULL
       OR NOT EXISTS (
           SELECT 1 FROM uec.geocode_jobs job
           JOIN uec.geocode_job_events queued ON queued.job_id=job.job_id
           WHERE job.source_record_id=NEW.source_record_id
             AND job.provider_id=NEW.provider_id AND job.query=NEW.query
             AND queued.event_type='queued'
             AND queued.details->>'processing_mode'='private_geoapify_source_profile'
             AND queued.details->>'profile_id'='geoapify-us-aphis-mailing-locality'
       ) THEN
        RETURN NEW;
    END IF;
    SELECT feature->'properties' INTO selected_properties
      FROM (SELECT NEW.response->'features'->
          CASE WHEN COALESCE(NEW.response->>'_uec_selected_feature_index','') ~ '^[0-9]+$'
               THEN (NEW.response->>'_uec_selected_feature_index')::integer ELSE 0 END AS feature) selected;
    IF selected_properties IS NULL OR selected_properties->>'result_type' <> 'city' THEN RETURN NEW; END IF;
    selected_country := upper(selected_properties->>'country_code');
    selected_city := lower(regexp_replace(trim(selected_properties->>'city'), '[^[:alnum:]]+', ' ', 'g'));
    selected_state := lower(regexp_replace(trim(COALESCE(selected_properties->>'state_code', selected_properties->>'state')), '[^[:alnum:]]+', ' ', 'g'));
    confidence_text := selected_properties#>>'{rank,confidence}';
    IF selected_country <> 'US' OR COALESCE(confidence_text,'') !~ '^[0-9]+([.][0-9]+)?$' THEN RETURN NEW; END IF;
    confidence_score := confidence_text::DOUBLE PRECISION;
    IF confidence_score < .90 OR confidence_score > 1 THEN RETURN NEW; END IF;
    FOR target_row IN
        SELECT target.candidate_id,target.snapshot_sha256,target.source_id,target.source_record_key,
               lower(regexp_replace(trim(location.location_evidence->>'city'), '[^[:alnum:]]+', ' ', 'g')) AS city,
               lower(regexp_replace(trim(location.location_evidence->>'region'), '[^[:alnum:]]+', ' ', 'g')) AS state
          FROM uec.geocode_jobs job
          JOIN real_preview.geocode_targets target ON target.job_id=job.job_id
          JOIN real_preview.candidates candidate ON candidate.candidate_id=target.candidate_id
          JOIN real_preview.candidate_private_location_evidence location ON location.candidate_id=candidate.candidate_id
         WHERE job.source_record_id=NEW.source_record_id AND job.provider_id=NEW.provider_id AND job.query=NEW.query
           AND target.source_id='us.aphis' AND candidate.source_id='us.aphis'
           AND candidate.country_code='US' AND target.snapshot_sha256=candidate.snapshot_sha256
           AND candidate.snapshot_sha256=(SELECT run.snapshot_sha256 FROM real_preview.source_preview_runs run WHERE run.source_id='us.aphis' ORDER BY run.created_at DESC,run.run_id DESC LIMIT 1)
           AND NOT EXISTS (SELECT 1 FROM uec.public_access_restricted restricted WHERE restricted.source_record_id=NEW.source_record_id)
    LOOP
        IF target_row.city <> selected_city OR target_row.state <> selected_state THEN CONTINUE; END IF;
        SELECT count(*) INTO viable_count
          FROM jsonb_array_elements(NEW.response->'features') feature
         WHERE feature->'properties'->>'result_type'='city'
           AND upper(feature->'properties'->>'country_code')='US'
           AND lower(regexp_replace(trim(feature->'properties'->>'city'), '[^[:alnum:]]+', ' ', 'g'))=target_row.city
           AND lower(regexp_replace(trim(COALESCE(feature->'properties'->>'state_code',feature->'properties'->>'state')), '[^[:alnum:]]+', ' ', 'g'))=target_row.state
           AND COALESCE(feature->'properties'#>>'{rank,confidence}','') ~ '^[0-9]+([.][0-9]+)?$'
           AND (feature->'properties'#>>'{rank,confidence}')::double precision BETWEEN .90 AND 1;
        IF viable_count <> 1 THEN CONTINUE; END IF;
        INSERT INTO real_preview.geocode_display_evidence
            (candidate_id,geocode_result_id,display_latitude,display_longitude,display_precision,
             display_geometry_source,coordinate_review_status,match_confidence,match_confidence_band)
        VALUES (target_row.candidate_id,NEW.geocode_result_id,ST_Y(NEW.result::geometry),ST_X(NEW.result::geometry),
                'provider_locality_approximate',
                'Geoapify; exact APHIS mailing city/state match with rank confidence >= 0.90 heuristic; approximate mailing-locality point, not operating-site or facility coordinates; private preview only',
                'approximate_provider_locality_private_display',confidence_score,'high_heuristic')
        ON CONFLICT (candidate_id,geocode_result_id) DO NOTHING;
    END LOOP;
    RETURN NEW;
END;
$$;

CREATE TRIGGER aaa_aphis_mailing_locality_geoapify_display
    AFTER INSERT ON uec.geocode_results
    FOR EACH ROW EXECUTE FUNCTION real_preview.capture_aphis_mailing_locality_display();
