-- Versioned offline acceptance of retained LocationIQ responses. The original
-- provider result remains review_required and immutable; this is a derived row.
CREATE TABLE real_preview.germany_retained_geocode_reconciliations (
    parent_geocode_result_id UUID NOT NULL REFERENCES uec.geocode_results(geocode_result_id),
    derived_geocode_result_id UUID NOT NULL UNIQUE,
    candidate_id UUID NOT NULL REFERENCES real_preview.candidates(candidate_id),
    snapshot_sha256 CHAR(64) NOT NULL,
    ruleset_version TEXT NOT NULL CHECK (ruleset_version = 'german-street-spelling-v1'),
    selected_result_index SMALLINT NOT NULL CHECK (selected_result_index IN (0,1)),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY(parent_geocode_result_id,ruleset_version),
    FOREIGN KEY(derived_geocode_result_id)
        REFERENCES uec.geocode_results(geocode_result_id)
        DEFERRABLE INITIALLY DEFERRED
);
CREATE TRIGGER germany_retained_geocode_reconciliations_immutable
    BEFORE UPDATE OR DELETE ON real_preview.germany_retained_geocode_reconciliations
    FOR EACH ROW EXECUTE FUNCTION real_preview.reject_mutation();

CREATE FUNCTION real_preview.locationiq_retained_street_matches_v1(
    source_text TEXT, road TEXT, provider_house TEXT)
RETURNS BOOLEAN LANGUAGE plpgsql IMMUTABLE PARALLEL SAFE AS $$
DECLARE
    source_value TEXT := normalize(trim(COALESCE(source_text,'')), NFKC);
    road_value TEXT := normalize(trim(COALESCE(road,'')), NFKC);
    house_value TEXT := normalize(trim(COALESCE(provider_house,'')), NFKC);
    parts TEXT[];
    source_road TEXT;
    source_house TEXT;
    source_stem TEXT;
    road_stem TEXT;
BEGIN
    IF source_value = '' OR road_value = '' OR house_value = '' THEN RETURN false; END IF;
    parts := regexp_match(source_value, '^([[:digit:]]+[[:alnum:]_/-]*)[[:space:]]+(.+)$');
    IF parts IS NOT NULL THEN
        source_house := parts[1]; source_road := parts[2];
    ELSE
        parts := regexp_match(source_value, '^(.+?)[[:space:]]+([[:digit:]]+[[:alnum:]_/-]*)$');
        IF parts IS NULL THEN RETURN false; END IF;
        source_road := parts[1]; source_house := parts[2];
    END IF;
    IF lower(source_house) <> lower(house_value) THEN RETURN false; END IF;
    source_road := lower(trim(source_road));
    road_value := lower(trim(road_value));
    IF source_road !~* '(straße|strasse|str\.?)$' OR road_value !~* '(straße|strasse|str\.?)$' THEN
        RETURN false;
    END IF;
    source_stem := regexp_replace(source_road, '[[:space:]]*(straße|strasse|str\.?)$', '', 'i');
    road_stem := regexp_replace(road_value, '[[:space:]]*(straße|strasse|str\.?)$', '', 'i');
    source_stem := regexp_replace(replace(replace(replace(replace(source_stem,'ß','ss'),'ä','ae'),'ö','oe'),'ü','ue'), '[[:space:]]+', ' ', 'g');
    road_stem := regexp_replace(replace(replace(replace(replace(road_stem,'ß','ss'),'ä','ae'),'ö','oe'),'ü','ue'), '[[:space:]]+', ' ', 'g');
    RETURN source_stem <> '' AND source_stem = road_stem;
END;
$$;

CREATE FUNCTION real_preview.locationiq_germany_address_matches_retained_v1(
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
    road := address->>'road';
    house := address->>'house_number';
    result_city := COALESCE(address->>'city',address->>'town',address->>'municipality',address->>'village');
    IF NOT real_preview.locationiq_retained_street_matches_v1(street,road,house)
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

CREATE FUNCTION real_preview.capture_locationiq_retained_private_display()
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
    parent uec.geocode_results%ROWTYPE;
    reconciliation real_preview.germany_retained_geocode_reconciliations%ROWTYPE;
BEGIN
    IF NEW.match_method <> 'locationiq_retained_street_v1' THEN RETURN NEW; END IF;
    IF NEW.provider_id <> 'locationiq' OR NEW.status <> 'accepted'
       OR NEW.precision IS DISTINCT FROM 'locationiq_address_point'
       OR NEW.match_method <> 'locationiq_retained_street_v1' OR NEW.result IS NULL
       OR jsonb_typeof(NEW.response->'results') IS DISTINCT FROM 'array'
       OR jsonb_array_length(NEW.response->'results') NOT BETWEEN 1 AND 2
       OR NEW.response->>'_uec_ruleset_version' IS DISTINCT FROM 'german-street-spelling-v1'
       OR COALESCE(NEW.response->>'_uec_selected_result_index','') !~ '^[01]$'
    THEN RAISE EXCEPTION 'invalid retained geocode evaluation' USING ERRCODE='23514'; END IF;
    SELECT * INTO reconciliation FROM real_preview.germany_retained_geocode_reconciliations audit_link
     WHERE audit_link.derived_geocode_result_id=NEW.geocode_result_id
       AND audit_link.ruleset_version='german-street-spelling-v1'
       AND audit_link.selected_result_index=(NEW.response->>'_uec_selected_result_index')::SMALLINT;
    IF reconciliation.derived_geocode_result_id IS NULL
       OR NEW.response->>'_uec_parent_geocode_result_id' IS DISTINCT FROM reconciliation.parent_geocode_result_id::TEXT
    THEN RAISE EXCEPTION 'retained geocode lineage missing' USING ERRCODE='23514'; END IF;
    SELECT * INTO parent FROM uec.geocode_results source_result
     WHERE source_result.geocode_result_id=reconciliation.parent_geocode_result_id
       AND source_result.provider_id='locationiq' AND source_result.status='review_required'
       AND source_result.source_record_id=NEW.source_record_id AND source_result.query=NEW.query
       AND source_result.attempt_number=NEW.attempt_number AND source_result.queried_at=NEW.queried_at;
    IF parent.geocode_result_id IS NULL OR parent.response->'results' IS DISTINCT FROM NEW.response->'results'
    THEN RAISE EXCEPTION 'retained geocode parent mismatch' USING ERRCODE='23514'; END IF;
    selected := NEW.response->'results'->(NEW.response->>'_uec_selected_result_index')::INTEGER;
    SELECT candidate.candidate_id,candidate.snapshot_sha256,
            location.location_evidence->>'address',
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
       AND job.query IN (
           concat_ws(', ',trim(location.location_evidence->>'address'),
               COALESCE(location.location_evidence->>'postal_code',
                 (regexp_match(COALESCE(location.location_evidence->>'city',candidate.city),'^([0-9]{5})[[:space:]]+'))[1]),
               trim(regexp_replace(COALESCE(location.location_evidence->>'city',candidate.city),'^[0-9]{5}[[:space:]]+','')),
               NULLIF(trim(location.location_evidence->>'region'),''),'Germany'),
           concat_ws(', ',trim(location.location_evidence->>'address'),
               COALESCE(location.location_evidence->>'postal_code',
                 (regexp_match(COALESCE(location.location_evidence->>'city',candidate.city),'^([0-9]{5})[[:space:]]+'))[1]) || ' ' ||
               trim(regexp_replace(COALESCE(location.location_evidence->>'city',candidate.city),'^[0-9]{5}[[:space:]]+','')),
               NULLIF(trim(location.location_evidence->>'region'),''),'Germany'),
           CASE WHEN NULLIF(trim(location.location_evidence->>'region'),'') IS NULL THEN
               trim(location.location_evidence->>'address') || ', ' ||
               COALESCE(location.location_evidence->>'postal_code',
                 (regexp_match(COALESCE(location.location_evidence->>'city',candidate.city),'^([0-9]{5})[[:space:]]+'))[1]) || ' ' ||
               trim(regexp_replace(COALESCE(location.location_evidence->>'city',candidate.city),'^[0-9]{5}[[:space:]]+',''))
           END)
       AND candidate.candidate_id=reconciliation.candidate_id
       AND candidate.snapshot_sha256=reconciliation.snapshot_sha256
       AND candidate.source_id='de.locations' AND candidate.country_code='DE'
       AND target.source_id=candidate.source_id AND target.snapshot_sha256=candidate.snapshot_sha256
       AND candidate.snapshot_sha256=(SELECT run.snapshot_sha256 FROM real_preview.source_preview_runs run
           WHERE run.source_id=candidate.source_id ORDER BY run.created_at DESC,run.run_id DESC LIMIT 1)
       AND candidate.location_class <> 'numeric_source_coordinate'
       AND candidate.default_map_scope AND candidate.display_latitude IS NULL AND candidate.display_longitude IS NULL
       AND COALESCE(location.location_evidence->>'country_code','DE')='DE'
       AND EXISTS (SELECT 1 FROM uec.geocode_job_events queued WHERE queued.job_id=job.job_id
           AND queued.event_type='queued' AND queued.details->>'profile_id'='locationiq-de-bltu'
           AND queued.details->>'processing_mode'='private_locationiq_source_profile')
       AND NOT EXISTS (SELECT 1 FROM uec.public_access_restricted restricted WHERE restricted.source_record_id=NEW.source_record_id)
       AND NOT EXISTS (SELECT 1 FROM real_preview.enrichment_state_events state
           WHERE state.candidate_id=candidate.candidate_id AND state.state_code='restricted')
     LIMIT 1 FOR UPDATE OF candidate;
    IF candidate_key IS NULL THEN RAISE EXCEPTION 'retained geocode source context rejected' USING ERRCODE='23514'; END IF;
    SELECT count(*) INTO viable FROM jsonb_array_elements(NEW.response->'results') item
     WHERE real_preview.locationiq_germany_address_matches_retained_v1(item,street,postcode,locality,region);
    IF viable <> 1 OR NOT real_preview.locationiq_germany_address_matches_retained_v1(selected,street,postcode,locality,region)
       OR ST_Y(NEW.result::geometry) <> (selected->>'lat')::DOUBLE PRECISION
       OR ST_X(NEW.result::geometry) <> (selected->>'lon')::DOUBLE PRECISION
    THEN RAISE EXCEPTION 'retained geocode components rejected' USING ERRCODE='23514'; END IF;
    INSERT INTO real_preview.germany_geocode_context_audit(candidate_id,snapshot_sha256,geocode_result_id,outcome)
    VALUES(candidate_key,snapshot,NEW.geocode_result_id,'matched') ON CONFLICT DO NOTHING;
    INSERT INTO real_preview.geocode_display_evidence
        (candidate_id,geocode_result_id,display_latitude,display_longitude,display_precision,
         display_geometry_source,coordinate_review_status,match_confidence,match_confidence_band)
    VALUES(candidate_key,NEW.geocode_result_id,ST_Y(NEW.result::geometry),ST_X(NEW.result::geometry),
           'provider_address_point_high_confidence',
           'LocationIQ; retained response matched by german-street-spelling-v1 with exact house number, postcode, locality and state',
           'automated_high_confidence_private_display',NULL,'high_heuristic') ON CONFLICT DO NOTHING;
    RETURN NEW;
END;
$$;
CREATE TRIGGER geocode_results_locationiq_retained_private_display
    AFTER INSERT ON uec.geocode_results
    FOR EACH ROW EXECUTE FUNCTION real_preview.capture_locationiq_retained_private_display();
