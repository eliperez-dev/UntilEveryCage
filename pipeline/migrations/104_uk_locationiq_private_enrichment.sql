-- Private UK address matching. Source X/Y with undocumented CRS are not used.
INSERT INTO real_preview.private_geocoding_source_profiles
    (profile_id,source_id,country_code,enabled,source_scope,provider_id)
VALUES
 ('locationiq-gb-fsa-approved-establishments','fsa_approved_establishments','GB',true,
  'Explicit source town, postcode and numbered street; withheld addresses excluded','locationiq'),
 ('locationiq-gb-fss-approved-establishments','fss_approved_establishments','GB',true,
  'Explicit source locality, postcode and numbered street only; no inferred locality','locationiq')
ON CONFLICT (profile_id) DO NOTHING;

CREATE FUNCTION real_preview.locationiq_uk_source_query(location JSONB)
RETURNS TEXT LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE
    line JSONB;
    part TEXT;
    matched TEXT[];
    road TEXT;
    house TEXT;
    street TEXT;
    selected_street TEXT;
    town TEXT := trim(regexp_replace(coalesce(location->>'city',''),'\s+',' ','g'));
    postcode TEXT := upper(regexp_replace(coalesce(location->>'postal_code',''),'\s+','','g'));
    -- Noncapturing groups keep road/house positions unambiguous.
    house_pattern TEXT := '[0-9]+[A-Za-z]?(?:[-/][0-9]+[A-Za-z]?)?';
    road_pattern TEXT := '[[:alnum:]_''’.\-]+(?:\s+[[:alnum:]_''’.\-]+)*\s+(?:street|st|road|rd|avenue|ave|lane|ln|drive|dr|way|close|crescent|cres|court|ct|terrace|ter|place|pl|square|sq|gardens?|grove|green|hill|row|walk|mews|wharf|parade|high street|high road)';
BEGIN
    IF jsonb_typeof(location) IS DISTINCT FROM 'object'
       OR coalesce(location->>'country_code','') <> 'GB'
       OR jsonb_typeof(location->'address_lines') IS DISTINCT FROM 'array'
       OR town='' OR length(town)>200 OR town LIKE '%,%'
       OR postcode !~ '^(GIR0AA|[A-Z]{1,2}[0-9][A-Z0-9]?[0-9][A-Z]{2})$'
    THEN RETURN NULL; END IF;
    postcode := left(postcode,length(postcode)-3)||' '||right(postcode,3);
    FOR line IN SELECT value FROM jsonb_array_elements(location->'address_lines') LOOP
        IF jsonb_typeof(line) IS DISTINCT FROM 'string' THEN RETURN NULL; END IF;
        FOR part IN SELECT trim(regexp_replace(value,'\s+',' ','g'))
                      FROM regexp_split_to_table(line #>> '{}',',') value LOOP
            IF length(part)>500 THEN RETURN NULL; END IF;
            matched := regexp_match(part,'^('||house_pattern||')\s+('||road_pattern||')$','i');
            IF matched IS NOT NULL THEN house:=matched[1];road:=matched[2];
            ELSE
                matched := regexp_match(part,'^('||road_pattern||')\s+('||house_pattern||')$','i');
                IF matched IS NULL THEN CONTINUE; END IF;
                road:=matched[1];house:=matched[2];
            END IF;
            street := house||' '||road;
            IF selected_street IS NOT NULL
               AND real_preview.normalize_new_zealand_geocode_text(selected_street)
                   <> real_preview.normalize_new_zealand_geocode_text(street)
            THEN RETURN NULL; END IF;
            selected_street:=street;
        END LOOP;
    END LOOP;
    IF selected_street IS NULL THEN RETURN NULL; END IF;
    RETURN selected_street||', '||town||', '||postcode||', United Kingdom';
END;
$$;

CREATE FUNCTION real_preview.locationiq_uk_address_matches(item JSONB, source_query TEXT)
RETURNS BOOLEAN LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE
    address JSONB := item->'address';
    parts TEXT[] := string_to_array(source_query,', ');
    latitude DOUBLE PRECISION;
    longitude DOUBLE PRECISION;
    source_street TEXT;
    road TEXT;
    house TEXT;
BEGIN
    IF array_length(parts,1) IS DISTINCT FROM 4 OR parts[4]<>'United Kingdom'
       OR jsonb_typeof(item) IS DISTINCT FROM 'object'
       OR jsonb_typeof(address) IS DISTINCT FROM 'object'
       OR jsonb_typeof(item->'lat') IS DISTINCT FROM 'string'
       OR jsonb_typeof(item->'lon') IS DISTINCT FROM 'string'
       OR lower(coalesce(address->>'country_code',''))<>'gb'
       OR nullif(trim(address->>'road'),'') IS NULL
       OR nullif(trim(address->>'house_number'),'') IS NULL
       OR (item->>'class' IN ('highway','boundary','place','landuse')
           AND NOT (item->>'class'='place' AND item->>'type'='house'
                    AND coalesce(item->>'addresstype','') IN ('','house','building')))
       OR item->>'type' IN ('houses','road','city','town','village','municipality','postcode')
       OR item->>'addresstype' IN ('houses','road','city','town','village','municipality','postcode')
       OR upper(regexp_replace(coalesce(address->>'postcode',''),'\s+','','g'))
          <> upper(replace(parts[3],' ',''))
    THEN RETURN false; END IF;
    BEGIN
        latitude:=(item->>'lat')::DOUBLE PRECISION;
        longitude:=(item->>'lon')::DOUBLE PRECISION;
    EXCEPTION WHEN invalid_text_representation OR numeric_value_out_of_range THEN RETURN false;
    END;
    IF NOT (latitude BETWEEN 49.8 AND 60.9 AND longitude BETWEEN -8.7 AND 2.0)
    THEN RETURN false; END IF;
    source_street:=real_preview.normalize_new_zealand_geocode_text(parts[1]);
    road:=real_preview.normalize_new_zealand_geocode_text(address->>'road');
    house:=real_preview.normalize_new_zealand_geocode_text(address->>'house_number');
    RETURN source_street=house||' '||road
       AND real_preview.normalize_new_zealand_geocode_text(parts[2]) IN (
           real_preview.normalize_new_zealand_geocode_text(address->>'city'),
           real_preview.normalize_new_zealand_geocode_text(address->>'town'),
           real_preview.normalize_new_zealand_geocode_text(address->>'municipality'),
           real_preview.normalize_new_zealand_geocode_text(address->>'village'),
           real_preview.normalize_new_zealand_geocode_text(address->>'suburb'));
END;
$$;

CREATE TABLE real_preview.uk_locationiq_context_audit (
    candidate_id UUID NOT NULL REFERENCES real_preview.candidates(candidate_id),
    snapshot_sha256 CHAR(64) NOT NULL,
    geocode_result_id UUID NOT NULL REFERENCES uec.geocode_results(geocode_result_id),
    outcome TEXT NOT NULL CHECK (outcome='matched'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY(candidate_id,geocode_result_id)
);
CREATE TRIGGER uk_locationiq_context_audit_immutable
    BEFORE UPDATE OR DELETE ON real_preview.uk_locationiq_context_audit
    FOR EACH ROW EXECUTE FUNCTION real_preview.reject_mutation();

CREATE FUNCTION real_preview.capture_uk_locationiq_private_display()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    context RECORD;
    context_count INTEGER:=0;
    candidate_key UUID;
    snapshot CHAR(64);
    selected JSONB;
    viable INTEGER;
BEGIN
    IF NEW.provider_id<>'locationiq' OR NEW.status<>'accepted'
       OR NEW.precision<>'locationiq_address_point' OR NEW.match_method<>'locationiq_forward'
       OR NEW.result IS NULL OR jsonb_typeof(NEW.response->'results') IS DISTINCT FROM 'array'
       OR jsonb_array_length(NEW.response->'results') NOT BETWEEN 1 AND 2
       OR coalesce(NEW.response->>'_uec_selected_result_index','') !~ '^[01]$'
    THEN RETURN NEW; END IF;
    FOR context IN
      SELECT candidate.candidate_id,candidate.snapshot_sha256
      FROM uec.geocode_jobs job
      JOIN real_preview.geocode_targets target ON target.job_id=job.job_id
      JOIN real_preview.candidates candidate ON candidate.candidate_id=target.candidate_id
      JOIN real_preview.candidate_private_location_evidence location
        ON location.candidate_id=candidate.candidate_id
       AND location.snapshot_sha256=candidate.snapshot_sha256 AND location.source_id=candidate.source_id
      JOIN real_preview.private_geocoding_source_profiles profile
        ON profile.source_id=candidate.source_id AND profile.country_code='GB'
       AND profile.provider_id=NEW.provider_id AND profile.enabled
       AND profile.profile_id IN ('locationiq-gb-fsa-approved-establishments','locationiq-gb-fss-approved-establishments')
      WHERE job.source_record_id=NEW.source_record_id AND job.query=NEW.query AND job.provider_id=NEW.provider_id
        AND candidate.source_id IN ('fsa_approved_establishments','fss_approved_establishments')
        AND candidate.country_code='GB' AND candidate.snapshot_sha256=target.snapshot_sha256
        AND candidate.snapshot_sha256=(SELECT run.snapshot_sha256 FROM real_preview.source_preview_runs run
            WHERE run.source_id=candidate.source_id ORDER BY run.created_at DESC,run.run_id DESC LIMIT 1)
        AND candidate.default_map_scope AND candidate.display_latitude IS NULL AND candidate.display_longitude IS NULL
        AND real_preview.locationiq_uk_source_query(location.location_evidence)=NEW.query
        AND EXISTS (SELECT 1 FROM uec.geocode_job_events queued WHERE queued.job_id=job.job_id
            AND queued.event_type='queued' AND queued.details->>'profile_id'=profile.profile_id
            AND queued.details->>'processing_mode'='private_locationiq_source_profile')
        AND NOT EXISTS (SELECT 1 FROM uec.public_access_restricted restricted
            WHERE restricted.source_record_id=NEW.source_record_id)
        AND NOT EXISTS (SELECT 1 FROM real_preview.enrichment_state_events state
            WHERE state.candidate_id=candidate.candidate_id AND state.state_code='restricted')
      LIMIT 2 FOR UPDATE OF candidate
    LOOP
        context_count:=context_count+1;
        candidate_key:=context.candidate_id;snapshot:=context.snapshot_sha256;
    END LOOP;
    IF context_count<>1 THEN RETURN NEW; END IF;
    selected:=NEW.response->'results'->(NEW.response->>'_uec_selected_result_index')::INTEGER;
    SELECT count(*) INTO viable FROM jsonb_array_elements(NEW.response->'results') item
        WHERE real_preview.locationiq_uk_address_matches(item,NEW.query);
    IF viable<>1 OR NOT real_preview.locationiq_uk_address_matches(selected,NEW.query)
       OR ST_Y(NEW.result::geometry)<>(selected->>'lat')::DOUBLE PRECISION
       OR ST_X(NEW.result::geometry)<>(selected->>'lon')::DOUBLE PRECISION
    THEN RETURN NEW; END IF;
    INSERT INTO real_preview.uk_locationiq_context_audit(candidate_id,snapshot_sha256,geocode_result_id,outcome)
        VALUES(candidate_key,snapshot,NEW.geocode_result_id,'matched') ON CONFLICT DO NOTHING;
    INSERT INTO real_preview.geocode_display_evidence
        (candidate_id,geocode_result_id,display_latitude,display_longitude,display_precision,
         display_geometry_source,coordinate_review_status,match_confidence,match_confidence_band)
    VALUES(candidate_key,NEW.geocode_result_id,ST_Y(NEW.result::geometry),ST_X(NEW.result::geometry),
           'provider_address_point_high_confidence',
           'LocationIQ; retained UK numbered street, source town and postcode matched',
           'automated_high_confidence_private_display',NULL,'high_heuristic') ON CONFLICT DO NOTHING;
    RETURN NEW;
END;
$$;
CREATE TRIGGER geocode_results_uk_locationiq_private_display
    AFTER INSERT ON uec.geocode_results
    FOR EACH ROW EXECUTE FUNCTION real_preview.capture_uk_locationiq_private_display();

DO $$
DECLARE
    definition TEXT:=pg_get_functiondef('real_preview.reject_mutation()'::regprocedure);
    marker TEXT:='    RAISE EXCEPTION ''real preview evidence is append-only'';';
    addition TEXT:=$guard$
    IF TG_TABLE_SCHEMA='real_preview' AND TG_TABLE_NAME='candidates' AND TG_OP='UPDATE'
       AND (to_jsonb(OLD)-ARRAY['display_latitude','display_longitude','display_geometry_source',
           'coordinate_method','coordinate_provider','coordinate_confidence','coordinate_confidence_band'])
         = (to_jsonb(NEW)-ARRAY['display_latitude','display_longitude','display_geometry_source',
           'coordinate_method','coordinate_provider','coordinate_confidence','coordinate_confidence_band'])
       AND NEW.source_id IN ('fsa_approved_establishments','fss_approved_establishments') AND NEW.country_code='GB'
       AND NEW.coordinate_method='locationiq_forward' AND NEW.coordinate_provider='LocationIQ'
       AND NEW.coordinate_confidence IS NULL AND NEW.coordinate_confidence_band='high'
       AND EXISTS (SELECT 1 FROM real_preview.geocode_display_evidence evidence
           JOIN uec.geocode_results result USING(geocode_result_id)
           JOIN real_preview.uk_locationiq_context_audit audit
             ON audit.candidate_id=evidence.candidate_id AND audit.geocode_result_id=evidence.geocode_result_id
            AND audit.snapshot_sha256=NEW.snapshot_sha256 AND audit.outcome='matched'
           WHERE evidence.candidate_id=NEW.candidate_id AND result.provider_id='locationiq'
             AND result.status='accepted' AND evidence.display_latitude=NEW.display_latitude
             AND evidence.display_longitude=NEW.display_longitude
             AND evidence.display_geometry_source=NEW.display_geometry_source)
    THEN RETURN NEW; END IF;
    $guard$;
BEGIN
    IF length(definition)-length(replace(definition,marker,''))<>length(marker)
    THEN RAISE EXCEPTION 'UK candidate cache guard prerequisites are missing'; END IF;
    EXECUTE replace(definition,marker,addition||E'\n'||marker);
END;
$$;
