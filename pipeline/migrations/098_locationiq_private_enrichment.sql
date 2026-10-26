-- Add a provider-scoped fallback without changing existing jobs or releases.
ALTER TABLE real_preview.private_geocoding_source_profiles
    ADD COLUMN provider_id TEXT NOT NULL DEFAULT 'geoapify'
        CHECK (provider_id IN ('geoapify','locationiq'));
DROP INDEX real_preview.private_geocoding_source_profiles_one_non_es_profile;
CREATE UNIQUE INDEX private_geocoding_source_profiles_one_provider_source
    ON real_preview.private_geocoding_source_profiles(source_id,provider_id)
    WHERE source_id <> 'es.locations';
INSERT INTO real_preview.private_geocoding_source_profiles
    (profile_id,source_id,country_code,enabled,source_scope,provider_id)
VALUES ('locationiq-de-bltu','de.locations','DE',true,
        'Current unmapped BVL business addresses; operator-selected fallback; private evidence only',
        'locationiq');

CREATE FUNCTION real_preview.locationiq_germany_address_matches(
    item JSONB, street TEXT, postcode TEXT, locality TEXT, region TEXT)
RETURNS BOOLEAN LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE
    address JSONB := item->'address';
    latitude DOUBLE PRECISION;
    longitude DOUBLE PRECISION;
    road TEXT;
    house TEXT;
    result_city TEXT;
BEGIN
    IF jsonb_typeof(item) IS DISTINCT FROM 'object'
       OR jsonb_typeof(address) IS DISTINCT FROM 'object'
       OR jsonb_typeof(item->'lat') IS DISTINCT FROM 'string'
       OR jsonb_typeof(item->'lon') IS DISTINCT FROM 'string'
       OR lower(COALESCE(address->>'country_code','')) <> 'de'
       OR COALESCE(postcode,'') !~ '^[0-9]{5}$'
       OR COALESCE(address->>'postcode','') <> postcode
       OR item->>'class' IN ('highway','boundary','place','landuse')
       OR item->>'addresstype' IN ('road','city','town','village','municipality','postcode')
       OR item->>'type' IN ('road','city','town','village','municipality','postcode')
       OR NULLIF(trim(address->>'road'),'') IS NULL
       OR NULLIF(trim(address->>'house_number'),'') IS NULL
       OR NULLIF(trim(street),'') IS NULL OR NULLIF(trim(locality),'') IS NULL
    THEN RETURN false; END IF;
    BEGIN
        latitude := (item->>'lat')::DOUBLE PRECISION;
        longitude := (item->>'lon')::DOUBLE PRECISION;
    EXCEPTION WHEN invalid_text_representation OR numeric_value_out_of_range THEN
        RETURN false;
    END;
    IF NOT (latitude BETWEEN 47 AND 56 AND longitude BETWEEN 5 AND 16) THEN RETURN false; END IF;
    road := real_preview.normalize_germany_geocode_text(address->>'road');
    house := real_preview.normalize_germany_geocode_text(address->>'house_number');
    result_city := COALESCE(address->>'city',address->>'town',address->>'municipality',address->>'village');
    IF real_preview.normalize_germany_geocode_text(street) NOT IN (road || ' ' || house,house || ' ' || road)
       OR real_preview.normalize_germany_geocode_text(result_city)
          <> real_preview.normalize_germany_geocode_text(regexp_replace(locality,'^[0-9]{5}[[:space:]]+',''))
       OR NULLIF(trim(result_city),'') IS NULL THEN RETURN false; END IF;
    IF NULLIF(trim(region),'') IS NOT NULL AND (
        (NULLIF(trim(address->>'state_code'),'') IS NULL AND NULLIF(trim(address->>'state'),'') IS NULL)
        OR (NULLIF(trim(address->>'state_code'),'') IS NOT NULL
            AND real_preview.normalize_germany_state(address->>'state_code') <> real_preview.normalize_germany_state(region))
        OR (NULLIF(trim(address->>'state'),'') IS NOT NULL
            AND real_preview.normalize_germany_state(address->>'state') <> real_preview.normalize_germany_state(region))
    ) THEN RETURN false; END IF;
    RETURN true;
END;
$$;

CREATE FUNCTION real_preview.capture_locationiq_private_display()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    candidate_key UUID;
    snapshot CHAR(64);
    street TEXT;
    postcode TEXT;
    locality TEXT;
    region TEXT;
    selected JSONB;
    viable INTEGER;
BEGIN
    IF NEW.provider_id <> 'locationiq' OR NEW.status <> 'accepted'
       OR NEW.precision <> 'locationiq_address_point'
       OR NEW.match_method <> 'locationiq_forward' OR NEW.result IS NULL
       OR jsonb_typeof(NEW.response->'results') IS DISTINCT FROM 'array'
       OR jsonb_array_length(NEW.response->'results') NOT BETWEEN 1 AND 2
       OR COALESCE(NEW.response->>'_uec_selected_result_index','') !~ '^[01]$'
    THEN RETURN NEW; END IF;
    selected := NEW.response->'results'->(NEW.response->>'_uec_selected_result_index')::INTEGER;
    SELECT candidate.candidate_id,candidate.snapshot_sha256,
           COALESCE(location.location_evidence->'address_lines'->>0,location.location_evidence->>'address'),
           COALESCE(location.location_evidence->>'postal_code',
               (regexp_match(COALESCE(location.location_evidence->>'city',candidate.city),'^([0-9]{5})[[:space:]]+'))[1]),
           COALESCE(location.location_evidence->>'city',candidate.city),location.location_evidence->>'region'
      INTO candidate_key,snapshot,street,postcode,locality,region
      FROM uec.geocode_jobs job
      JOIN real_preview.geocode_targets target ON target.job_id=job.job_id
      JOIN real_preview.candidates candidate ON candidate.candidate_id=target.candidate_id
      JOIN real_preview.candidate_private_location_evidence location ON location.candidate_id=candidate.candidate_id
      JOIN real_preview.private_geocoding_source_profiles profile
        ON profile.profile_id='locationiq-de-bltu' AND profile.provider_id=NEW.provider_id
       AND profile.source_id=candidate.source_id AND profile.country_code=candidate.country_code AND profile.enabled
     WHERE job.source_record_id=NEW.source_record_id AND job.query=NEW.query AND job.provider_id=NEW.provider_id
       AND candidate.source_id='de.locations' AND candidate.country_code='DE'
       AND target.source_id=candidate.source_id AND target.snapshot_sha256=candidate.snapshot_sha256
       AND candidate.snapshot_sha256=(SELECT run.snapshot_sha256 FROM real_preview.source_preview_runs run
           WHERE run.source_id=candidate.source_id ORDER BY run.created_at DESC,run.run_id DESC LIMIT 1)
       AND candidate.location_class <> 'numeric_source_coordinate'
       AND candidate.default_map_scope AND candidate.display_latitude IS NULL AND candidate.display_longitude IS NULL
       AND COALESCE(location.location_evidence->>'country_code','DE')='DE'
       AND EXISTS (SELECT 1 FROM uec.geocode_job_events queued WHERE queued.job_id=job.job_id
           AND queued.event_type='queued' AND queued.details->>'profile_id'=profile.profile_id
           AND queued.details->>'processing_mode'='private_locationiq_source_profile')
       AND NOT EXISTS (SELECT 1 FROM uec.public_access_restricted restricted WHERE restricted.source_record_id=NEW.source_record_id)
     LIMIT 1 FOR UPDATE OF candidate;
    IF candidate_key IS NULL THEN RETURN NEW; END IF;
    SELECT count(*) INTO viable FROM jsonb_array_elements(NEW.response->'results') item
     WHERE real_preview.locationiq_germany_address_matches(item,street,postcode,locality,region);
    IF viable <> 1 OR NOT real_preview.locationiq_germany_address_matches(selected,street,postcode,locality,region)
       OR ST_Y(NEW.result::geometry) <> (selected->>'lat')::DOUBLE PRECISION
       OR ST_X(NEW.result::geometry) <> (selected->>'lon')::DOUBLE PRECISION THEN RETURN NEW; END IF;
    INSERT INTO real_preview.germany_geocode_context_audit(candidate_id,snapshot_sha256,geocode_result_id,outcome)
    VALUES(candidate_key,snapshot,NEW.geocode_result_id,'matched') ON CONFLICT DO NOTHING;
    INSERT INTO real_preview.geocode_display_evidence
        (candidate_id,geocode_result_id,display_latitude,display_longitude,display_precision,
         display_geometry_source,coordinate_review_status,match_confidence,match_confidence_band)
    VALUES(candidate_key,NEW.geocode_result_id,ST_Y(NEW.result::geometry),ST_X(NEW.result::geometry),
           'provider_address_point_high_confidence',
           'LocationIQ; matching source street, house number, postcode, locality and state',
           'automated_high_confidence_private_display',NULL,'high_heuristic') ON CONFLICT DO NOTHING;
    RETURN NEW;
END;
$$;
CREATE TRIGGER geocode_results_locationiq_private_display AFTER INSERT ON uec.geocode_results
    FOR EACH ROW EXECUTE FUNCTION real_preview.capture_locationiq_private_display();

-- Keep existing append-only exceptions; allow only audited LocationIQ cache writes.
DO $$
DECLARE
    definition TEXT := pg_get_functiondef('real_preview.reject_mutation()'::regprocedure);
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
           JOIN real_preview.germany_geocode_context_audit audit
             ON audit.candidate_id=evidence.candidate_id AND audit.geocode_result_id=evidence.geocode_result_id
            AND audit.snapshot_sha256=NEW.snapshot_sha256 AND audit.outcome='matched'
           WHERE evidence.candidate_id=NEW.candidate_id AND result.provider_id='locationiq' AND result.status='accepted'
             AND evidence.display_latitude=NEW.display_latitude AND evidence.display_longitude=NEW.display_longitude
             AND evidence.display_geometry_source=NEW.display_geometry_source)
    THEN RETURN NEW; END IF;
    $guard$;
BEGIN
    IF length(definition)-length(replace(definition,marker,'')) <> length(marker) THEN
        RAISE EXCEPTION 'candidate mutation guard marker is not unique';
    END IF;
    EXECUTE replace(definition,marker,addition || E'\n' || marker);
END;
$$;

CREATE OR REPLACE FUNCTION real_preview.sync_geoapify_private_display()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE provider TEXT;
BEGIN
    SELECT provider_id INTO provider FROM uec.geocode_results WHERE geocode_result_id=NEW.geocode_result_id;
    UPDATE real_preview.candidates SET display_latitude=NEW.display_latitude,display_longitude=NEW.display_longitude,
        display_geometry_source=NEW.display_geometry_source,
        coordinate_method=CASE WHEN provider='locationiq' THEN 'locationiq_forward' ELSE 'geoapify_forward' END,
        coordinate_provider=CASE WHEN provider='locationiq' THEN 'LocationIQ' ELSE 'Geoapify' END,
        coordinate_confidence=NEW.match_confidence,coordinate_confidence_band='high'
    WHERE candidate_id=NEW.candidate_id;
    RETURN NEW;
END;
$$;
