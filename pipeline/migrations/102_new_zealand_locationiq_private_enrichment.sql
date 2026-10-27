-- Private-only NZ LocationIQ enrichment for a single MPI RMP-associated site.
-- Missing source postcode is permitted; when supplied it must match exactly.
ALTER TABLE real_preview.private_geocoding_source_profiles
    DROP CONSTRAINT IF EXISTS private_geocoding_source_profiles_country_code_check;
ALTER TABLE real_preview.private_geocoding_source_profiles
    ADD CONSTRAINT private_geocoding_source_profiles_country_code_check
    CHECK (country_code IN ('GB','DK','NL','US','ES','DE','NZ'));

INSERT INTO real_preview.private_geocoding_source_profiles
    (profile_id,source_id,country_code,enabled,source_scope,provider_id)
VALUES ('locationiq-nz-mpi-rmp','nz.locations','NZ',true,
        'MPI RMP private physical address evidence; raw native Number of Locations must equal 1; exact road, house and town; supplied postcode must match; New Zealand main-island bounds only',
        'locationiq')
ON CONFLICT (profile_id) DO UPDATE SET
    source_id=EXCLUDED.source_id,country_code=EXCLUDED.country_code,
    enabled=true,source_scope=EXCLUDED.source_scope,provider_id=EXCLUDED.provider_id;

-- Keep the exact native cardinality value available for an independent SQL
-- decision; it must not be reconstructed from a normalized candidate field.
ALTER TABLE real_preview.candidate_private_location_evidence
    DROP CONSTRAINT IF EXISTS candidate_private_location_evidence_allowed_keys,
    ADD CONSTRAINT candidate_private_location_evidence_allowed_keys CHECK (
        location_evidence - ARRAY[
            'address','address_lines','city','postal_code','region','country_code','coordinates',
            'municipality_code','comarca_code','department_number','region_code','province',
            'source_administrative_location',
            'number_of_locations','location_count'
        ] = '{}'::jsonb
    ),
    ADD CONSTRAINT candidate_private_location_evidence_nz_cardinality_scope CHECK (
        (source_id='nz.locations' OR NOT (location_evidence ?| ARRAY['number_of_locations','location_count']))
        AND (NOT (location_evidence ? 'number_of_locations')
             OR jsonb_typeof(location_evidence->'number_of_locations') IN ('string','null'))
        AND (NOT (location_evidence ? 'location_count')
             OR jsonb_typeof(location_evidence->'location_count') IN ('number','null'))
    );

CREATE FUNCTION real_preview.normalize_new_zealand_geocode_text(input_text TEXT)
RETURNS TEXT LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    SELECT trim(regexp_replace(
        translate(lower(coalesce(input_text,'')),
            'āēīōūĀĒĪŌŪ', 'aeiouaeiou'),
        '[^[:alnum:]]+', ' ', 'g'))
$$;

CREATE FUNCTION real_preview.locationiq_new_zealand_address_matches(
    item JSONB, source_address TEXT, postcode TEXT, town TEXT)
RETURNS BOOLEAN LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE
    address JSONB := item->'address';
    latitude DOUBLE PRECISION;
    longitude DOUBLE PRECISION;
    road TEXT;
    house TEXT;
    result_locality_match BOOLEAN;
BEGIN
    IF jsonb_typeof(item) IS DISTINCT FROM 'object'
       OR jsonb_typeof(address) IS DISTINCT FROM 'object'
       OR jsonb_typeof(item->'lat') IS DISTINCT FROM 'string'
       OR jsonb_typeof(item->'lon') IS DISTINCT FROM 'string'
       OR lower(coalesce(address->>'country_code','')) <> 'nz'
       OR nullif(trim(source_address),'') IS NULL
       OR nullif(trim(town),'') IS NULL
       OR nullif(trim(address->>'road'),'') IS NULL
       OR nullif(trim(address->>'house_number'),'') IS NULL
       OR item->>'class' IN ('highway','boundary','place','landuse')
       OR item->>'addresstype' IN ('road','city','town','village','municipality','postcode')
       OR item->>'type' IN ('road','city','town','village','municipality','postcode')
       OR (nullif(trim(postcode),'') IS NOT NULL
           AND coalesce(address->>'postcode','') <> trim(postcode))
    THEN RETURN false; END IF;
    BEGIN
        latitude := (item->>'lat')::DOUBLE PRECISION;
        longitude := (item->>'lon')::DOUBLE PRECISION;
    EXCEPTION WHEN invalid_text_representation OR numeric_value_out_of_range THEN
        RETURN false;
    END;
    -- Continental North and South Islands only; exclude offshore islands.
    IF NOT (latitude BETWEEN -47.5 AND -34.0 AND longitude BETWEEN 166 AND 179.9) THEN
        RETURN false;
    END IF;
    road := real_preview.normalize_new_zealand_geocode_text(address->>'road');
    house := real_preview.normalize_new_zealand_geocode_text(address->>'house_number');
    result_locality_match :=
        real_preview.normalize_new_zealand_geocode_text(town) IN (
            real_preview.normalize_new_zealand_geocode_text(address->>'city'),
            real_preview.normalize_new_zealand_geocode_text(address->>'town'),
            real_preview.normalize_new_zealand_geocode_text(address->>'municipality'),
            real_preview.normalize_new_zealand_geocode_text(address->>'village'),
            real_preview.normalize_new_zealand_geocode_text(address->>'suburb'));
    IF real_preview.normalize_new_zealand_geocode_text(source_address)
           NOT IN (road || ' ' || house,house || ' ' || road)
       OR NOT result_locality_match
    THEN RETURN false; END IF;
    RETURN true;
END;
$$;

CREATE TABLE real_preview.new_zealand_locationiq_context_audit (
    candidate_id UUID NOT NULL REFERENCES real_preview.candidates(candidate_id),
    snapshot_sha256 CHAR(64) NOT NULL,
    geocode_result_id UUID NOT NULL REFERENCES uec.geocode_results(geocode_result_id),
    outcome TEXT NOT NULL CHECK (outcome IN ('matched')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (candidate_id,geocode_result_id)
);
CREATE TRIGGER new_zealand_locationiq_context_audit_immutable
    BEFORE UPDATE OR DELETE ON real_preview.new_zealand_locationiq_context_audit
    FOR EACH ROW EXECUTE FUNCTION real_preview.reject_mutation();

CREATE FUNCTION real_preview.capture_new_zealand_locationiq_private_display()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    candidate_key UUID;
    snapshot CHAR(64);
    source_address TEXT;
    postcode TEXT;
    town TEXT;
    selected JSONB;
    viable INTEGER;
    contexts INTEGER;
BEGIN
    IF NEW.provider_id <> 'locationiq' OR NEW.status <> 'accepted'
       OR NEW.precision <> 'locationiq_address_point'
       OR NEW.match_method <> 'locationiq_forward' OR NEW.result IS NULL
       OR jsonb_typeof(NEW.response->'results') IS DISTINCT FROM 'array'
       OR jsonb_array_length(NEW.response->'results') NOT BETWEEN 1 AND 2
       OR coalesce(NEW.response->>'_uec_selected_result_index','') !~ '^[01]$'
    THEN RETURN NEW; END IF;
    selected := NEW.response->'results'->(NEW.response->>'_uec_selected_result_index')::INTEGER;

    SELECT count(*) INTO contexts
      FROM uec.geocode_jobs job
      JOIN real_preview.geocode_targets target ON target.job_id=job.job_id
      JOIN real_preview.candidates candidate ON candidate.candidate_id=target.candidate_id
      JOIN real_preview.candidate_private_location_evidence location
        ON location.candidate_id=candidate.candidate_id
       AND location.snapshot_sha256=candidate.snapshot_sha256
       AND location.source_id=candidate.source_id
      JOIN real_preview.private_geocoding_source_profiles profile
        ON profile.profile_id='locationiq-nz-mpi-rmp' AND profile.provider_id=NEW.provider_id
       AND profile.source_id=candidate.source_id AND profile.country_code=candidate.country_code AND profile.enabled
     WHERE job.source_record_id=NEW.source_record_id AND job.query=NEW.query AND job.provider_id=NEW.provider_id
       AND candidate.source_id='nz.locations' AND candidate.country_code='NZ'
       AND candidate.snapshot_sha256=target.snapshot_sha256
       AND candidate.snapshot_sha256=(SELECT run.snapshot_sha256 FROM real_preview.source_preview_runs run
           WHERE run.source_id='nz.locations' ORDER BY run.created_at DESC,run.run_id DESC LIMIT 1)
       AND candidate.location_class <> 'numeric_source_coordinate'
       AND candidate.default_map_scope AND candidate.display_latitude IS NULL AND candidate.display_longitude IS NULL
       AND location.location_evidence->>'country_code'='NZ'
       AND trim(coalesce(location.location_evidence->>'number_of_locations',''))='1'
       AND jsonb_typeof(location.location_evidence->'location_count')='number'
       AND location.location_evidence->>'location_count'='1'
       AND nullif(trim(location.location_evidence->>'address'),'') IS NOT NULL
       AND nullif(trim(location.location_evidence->>'city'),'') IS NOT NULL
       AND (nullif(trim(location.location_evidence->>'postal_code'),'') IS NULL
            OR location.location_evidence->>'postal_code' ~ '^[0-9]{4}$')
       AND EXISTS (SELECT 1 FROM uec.geocode_job_events queued WHERE queued.job_id=job.job_id
           AND queued.event_type='queued' AND queued.details->>'profile_id'=profile.profile_id
           AND queued.details->>'processing_mode'='private_locationiq_source_profile')
       AND NOT EXISTS (SELECT 1 FROM uec.public_access_restricted restricted
           WHERE restricted.source_record_id=NEW.source_record_id)
       AND NOT EXISTS (SELECT 1 FROM real_preview.enrichment_state_events state
           WHERE state.candidate_id=candidate.candidate_id AND state.state_code='restricted');
    IF contexts <> 1 THEN RETURN NEW; END IF;

    SELECT candidate.candidate_id,candidate.snapshot_sha256,
           location.location_evidence->>'address',location.location_evidence->>'postal_code',
           location.location_evidence->>'city'
      INTO candidate_key,snapshot,source_address,postcode,town
      FROM uec.geocode_jobs job
      JOIN real_preview.geocode_targets target ON target.job_id=job.job_id
      JOIN real_preview.candidates candidate ON candidate.candidate_id=target.candidate_id
      JOIN real_preview.candidate_private_location_evidence location
        ON location.candidate_id=candidate.candidate_id
       AND location.snapshot_sha256=candidate.snapshot_sha256
       AND location.source_id=candidate.source_id
     WHERE job.source_record_id=NEW.source_record_id AND job.query=NEW.query AND job.provider_id=NEW.provider_id
       AND candidate.source_id='nz.locations' AND candidate.country_code='NZ'
       AND candidate.snapshot_sha256=target.snapshot_sha256
       AND candidate.snapshot_sha256=(SELECT run.snapshot_sha256 FROM real_preview.source_preview_runs run
           WHERE run.source_id='nz.locations' ORDER BY run.created_at DESC,run.run_id DESC LIMIT 1)
       AND candidate.default_map_scope AND candidate.display_latitude IS NULL AND candidate.display_longitude IS NULL
       AND location.location_evidence->>'country_code'='NZ'
       AND trim(coalesce(location.location_evidence->>'number_of_locations',''))='1'
       AND jsonb_typeof(location.location_evidence->'location_count')='number'
       AND location.location_evidence->>'location_count'='1'
       AND EXISTS (SELECT 1 FROM real_preview.private_geocoding_source_profiles profile
           WHERE profile.profile_id='locationiq-nz-mpi-rmp' AND profile.provider_id=NEW.provider_id
             AND profile.source_id=candidate.source_id AND profile.country_code=candidate.country_code AND profile.enabled)
       AND EXISTS (SELECT 1 FROM uec.geocode_job_events queued WHERE queued.job_id=job.job_id
           AND queued.event_type='queued' AND queued.details->>'profile_id'='locationiq-nz-mpi-rmp'
           AND queued.details->>'processing_mode'='private_locationiq_source_profile')
       AND NOT EXISTS (SELECT 1 FROM uec.public_access_restricted restricted
           WHERE restricted.source_record_id=NEW.source_record_id)
       AND NOT EXISTS (SELECT 1 FROM real_preview.enrichment_state_events state
           WHERE state.candidate_id=candidate.candidate_id AND state.state_code='restricted')
     LIMIT 1 FOR UPDATE OF candidate;
    IF candidate_key IS NULL THEN RETURN NEW; END IF;

    SELECT count(*) INTO viable FROM jsonb_array_elements(NEW.response->'results') item
     WHERE real_preview.locationiq_new_zealand_address_matches(item,source_address,postcode,town);
    IF viable <> 1
       OR NOT real_preview.locationiq_new_zealand_address_matches(selected,source_address,postcode,town)
       OR ST_Y(NEW.result::geometry) <> (selected->>'lat')::DOUBLE PRECISION
       OR ST_X(NEW.result::geometry) <> (selected->>'lon')::DOUBLE PRECISION
    THEN RETURN NEW; END IF;

    INSERT INTO real_preview.new_zealand_locationiq_context_audit
        (candidate_id,snapshot_sha256,geocode_result_id,outcome)
    VALUES(candidate_key,snapshot,NEW.geocode_result_id,'matched') ON CONFLICT DO NOTHING;
    INSERT INTO real_preview.geocode_display_evidence
        (candidate_id,geocode_result_id,display_latitude,display_longitude,display_precision,
         display_geometry_source,coordinate_review_status,match_confidence,match_confidence_band)
    VALUES(candidate_key,NEW.geocode_result_id,ST_Y(NEW.result::geometry),ST_X(NEW.result::geometry),
           'provider_address_point_high_confidence',
           'LocationIQ; retained MPI RMP physical address matched by exact road, house, town and any supplied postcode within mainland New Zealand bounds',
           'automated_high_confidence_private_display',NULL,'high_heuristic') ON CONFLICT DO NOTHING;
    RETURN NEW;
END;
$$;
CREATE TRIGGER geocode_results_new_zealand_locationiq_private_display
    AFTER INSERT ON uec.geocode_results
    FOR EACH ROW EXECUTE FUNCTION real_preview.capture_new_zealand_locationiq_private_display();

-- Permit cache propagation only when the exact NZ coordinate tuple has this
-- matching, immutable private audit. The public release tables are untouched.
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
       AND NEW.source_id='nz.locations' AND NEW.country_code='NZ'
       AND NEW.coordinate_method='locationiq_forward' AND NEW.coordinate_provider='LocationIQ'
       AND NEW.coordinate_confidence IS NULL AND NEW.coordinate_confidence_band='high'
       AND EXISTS (SELECT 1 FROM real_preview.geocode_display_evidence evidence
           JOIN uec.geocode_results result USING(geocode_result_id)
           JOIN real_preview.new_zealand_locationiq_context_audit audit
             ON audit.candidate_id=evidence.candidate_id AND audit.geocode_result_id=evidence.geocode_result_id
            AND audit.snapshot_sha256=NEW.snapshot_sha256 AND audit.outcome='matched'
           WHERE evidence.candidate_id=NEW.candidate_id AND result.provider_id='locationiq'
             AND result.status='accepted' AND evidence.display_latitude=NEW.display_latitude
             AND evidence.display_longitude=NEW.display_longitude
             AND evidence.display_geometry_source=NEW.display_geometry_source)
    THEN RETURN NEW; END IF;
    $guard$;
BEGIN
    IF to_regprocedure('real_preview.reject_mutation()') IS NULL
       OR to_regclass('real_preview.geocode_display_evidence') IS NULL
       OR length(definition)-length(replace(definition,marker,'')) <> length(marker) THEN
        RAISE EXCEPTION 'NZ candidate cache guard prerequisites are missing';
    END IF;
    EXECUTE replace(definition,marker,addition || E'\n' || marker);
END;
$$;
