-- Let one preview candidate retain its original placeholder job while also
-- acquiring a separately targeted, immutable provider job. Existing job
-- identities and target history are preserved.
ALTER TABLE real_preview.geocode_targets
    DROP CONSTRAINT IF EXISTS geocode_targets_candidate_id_key;

ALTER TABLE real_preview.geocode_display_evidence
    DROP CONSTRAINT IF EXISTS geocode_display_evidence_coordinate_review_status_check,
    ADD COLUMN match_confidence DOUBLE PRECISION,
    ADD COLUMN match_confidence_band TEXT,
    ADD CONSTRAINT geocode_display_evidence_match_confidence_check
        CHECK (match_confidence IS NULL OR match_confidence BETWEEN 0 AND 1),
    ADD CONSTRAINT geocode_display_evidence_match_confidence_band_check
        CHECK (match_confidence_band IS NULL OR match_confidence_band = 'high_heuristic'),
    ADD CONSTRAINT geocode_display_evidence_coordinate_review_status_check
        CHECK (coordinate_review_status IN (
            'pending_human_review',
            'automated_high_confidence_private_display',
            'approximate_provider_locality_private_display'
        ));

-- Extend the compatibility-cache exception introduced for local references.
-- Cache writes remain possible only when a matching immutable evidence row
-- already exists in this transaction.
CREATE OR REPLACE FUNCTION real_preview.reject_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_TABLE_SCHEMA = 'real_preview' AND TG_TABLE_NAME = 'candidates'
       AND TG_OP = 'UPDATE'
       AND (to_jsonb(OLD) - ARRAY[
            'display_latitude','display_longitude','display_geometry_source',
            'coordinate_method','coordinate_provider','coordinate_confidence',
            'coordinate_confidence_band'
       ]) = (to_jsonb(NEW) - ARRAY[
            'display_latitude','display_longitude','display_geometry_source',
            'coordinate_method','coordinate_provider','coordinate_confidence',
            'coordinate_confidence_band'
       ])
       AND (
           EXISTS (
               SELECT 1 FROM real_preview.local_reference_display_evidence evidence
               WHERE evidence.candidate_id = NEW.candidate_id
                 AND evidence.reference_latitude = NEW.display_latitude
                 AND evidence.reference_longitude = NEW.display_longitude
                 AND evidence.display_geometry_source = NEW.display_geometry_source
                 AND NEW.coordinate_method IS NOT DISTINCT FROM OLD.coordinate_method
                 AND NEW.coordinate_provider IS NOT DISTINCT FROM OLD.coordinate_provider
                 AND NEW.coordinate_confidence IS NOT DISTINCT FROM OLD.coordinate_confidence
                 AND NEW.coordinate_confidence_band IS NOT DISTINCT FROM OLD.coordinate_confidence_band
           ) OR EXISTS (
               SELECT 1 FROM real_preview.geocode_display_evidence evidence
               WHERE evidence.candidate_id = NEW.candidate_id
                 AND evidence.display_latitude = NEW.display_latitude
                 AND evidence.display_longitude = NEW.display_longitude
                 AND evidence.display_geometry_source = NEW.display_geometry_source
                 AND NEW.coordinate_method = 'geoapify_forward'
                 AND NEW.coordinate_provider = 'Geoapify'
                 AND NEW.coordinate_confidence = evidence.match_confidence
                 AND NEW.coordinate_confidence_band = 'high'
           )
       ) THEN
        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'real preview evidence is append-only';
END;
$$;

CREATE FUNCTION real_preview.capture_geoapify_private_display()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    matched_candidate UUID;
    properties JSONB;
    result_type TEXT;
    result_country TEXT;
    confidence_text TEXT;
    confidence_score DOUBLE PRECISION;
    result_address TEXT;
    result_city TEXT;
    source_address TEXT;
    source_city TEXT;
    precision_label TEXT;
    disclosure TEXT;
    review_state TEXT;
BEGIN
    IF NEW.provider_id <> 'geoapify' OR NEW.status <> 'accepted'
       OR NEW.result IS NULL OR NEW.response IS NULL THEN
        RETURN NEW;
    END IF;

    SELECT target.candidate_id, feature->'properties',
           private_location.location_evidence->>'address',
           COALESCE(private_location.location_evidence->>'city', candidate.city)
      INTO matched_candidate, properties, source_address, source_city
      FROM uec.geocode_jobs job
      JOIN real_preview.geocode_targets target ON target.job_id = job.job_id
      JOIN real_preview.candidates candidate ON candidate.candidate_id = target.candidate_id
      JOIN real_preview.candidate_private_location_evidence private_location
        ON private_location.candidate_id = candidate.candidate_id
      CROSS JOIN LATERAL (SELECT NEW.response->'features'->0 AS feature) item
     WHERE job.source_record_id = NEW.source_record_id
       AND job.provider_id = NEW.provider_id
       AND job.query = NEW.query
       AND candidate.source_id = 'au.npi.facilities'
       AND candidate.country_code = 'AU'
       AND candidate.location_class = 'city_postal'
       AND candidate.default_map_scope = true
       AND EXISTS (SELECT 1 FROM uec.geocode_job_events event
                   WHERE event.job_id = job.job_id
                     AND event.details->>'processing_mode' = 'private_au_preview_pilot')
       AND NOT EXISTS (SELECT 1 FROM uec.public_access_restricted restricted
                       WHERE restricted.source_record_id = NEW.source_record_id)
     ORDER BY target.created_at DESC
     LIMIT 1;
    IF matched_candidate IS NULL OR properties IS NULL THEN
        RETURN NEW;
    END IF;

    result_type := properties->>'result_type';
    result_country := lower(properties->>'country_code');
    confidence_text := properties#>>'{rank,confidence}';
    IF COALESCE(confidence_text, '') !~ '^[0-9]+([.][0-9]+)?$' THEN
        RETURN NEW;
    END IF;
    confidence_score := confidence_text::DOUBLE PRECISION;
    IF result_country <> 'au' OR confidence_score < 0.90 OR confidence_score > 1 THEN
        RETURN NEW;
    END IF;

    IF result_type IN ('building', 'amenity') THEN
        SELECT COALESCE(properties->>'address_line1',
               CASE WHEN properties->>'housenumber' IS NOT NULL AND properties->>'street' IS NOT NULL
                    THEN (properties->>'housenumber') || ' ' || (properties->>'street') END)
          INTO result_address
          FROM uec.geocode_jobs job
          JOIN real_preview.geocode_targets target ON target.job_id = job.job_id
         WHERE target.candidate_id = matched_candidate AND job.job_id IN (
             SELECT geocode_job.job_id FROM uec.geocode_jobs geocode_job
             WHERE geocode_job.source_record_id = NEW.source_record_id
               AND geocode_job.provider_id = NEW.provider_id AND geocode_job.query = NEW.query
         )
         ORDER BY target.created_at DESC LIMIT 1;
        IF NULLIF(trim(source_address), '') IS NULL OR NULLIF(trim(result_address), '') IS NULL
           OR lower(regexp_replace(trim(source_address), '[^[:alnum:]]+', ' ', 'g'))
           <> lower(regexp_replace(trim(result_address), '[^[:alnum:]]+', ' ', 'g')) THEN
            RETURN NEW;
        END IF;
        precision_label := 'provider_address_point_high_confidence';
        disclosure := 'Geoapify; high rank confidence heuristic and normalized source-address line match; private preview only';
        review_state := 'automated_high_confidence_private_display';
    ELSIF result_type = 'city' THEN
        result_city := lower(regexp_replace(trim(properties->>'city'), '[^[:alnum:]]+', ' ', 'g'));
        IF result_city = '' OR NULLIF(trim(source_city), '') IS NULL
           OR lower(regexp_replace(trim(source_city), '[^[:alnum:]]+', ' ', 'g')) <> result_city THEN
            RETURN NEW;
        END IF;
        precision_label := 'provider_locality_approximate';
        disclosure := 'Geoapify; high rank confidence locality and Australia match; approximate city point, not facility coordinates; private preview only';
        review_state := 'approximate_provider_locality_private_display';
    ELSE
        RETURN NEW;
    END IF;

    INSERT INTO real_preview.geocode_display_evidence
        (candidate_id, geocode_result_id, display_latitude, display_longitude,
         display_precision, display_geometry_source, coordinate_review_status,
         match_confidence, match_confidence_band)
    VALUES (
        matched_candidate, NEW.geocode_result_id,
        ST_Y(NEW.result::geometry), ST_X(NEW.result::geometry),
        precision_label, disclosure, review_state, confidence_score, 'high_heuristic'
    ) ON CONFLICT (candidate_id, geocode_result_id) DO NOTHING;
    RETURN NEW;
END;
$$;
CREATE TRIGGER geocode_results_geoapify_preview_display
    AFTER INSERT ON uec.geocode_results
    FOR EACH ROW EXECUTE FUNCTION real_preview.capture_geoapify_private_display();

-- Display enrichment is append-only but can change map-visible output without
-- changing the source snapshot. Include its latest-snapshot evidence revision
-- in the existing private map cache identity.
CREATE OR REPLACE FUNCTION real_preview.display_evidence_revision()
RETURNS TEXT LANGUAGE sql STABLE AS $$
WITH sources AS (
    SELECT source_id FROM real_preview.source_preview_runs
    UNION
    SELECT source_id FROM real_preview.source_manifests
), latest AS (
    SELECT sources.source_id,
           COALESCE(
               (SELECT run.snapshot_sha256 FROM real_preview.source_preview_runs run
                WHERE run.source_id=sources.source_id
                ORDER BY run.created_at DESC,run.run_id DESC LIMIT 1),
               (SELECT manifest.snapshot_sha256 FROM real_preview.source_manifests manifest
                WHERE manifest.source_id=sources.source_id
                ORDER BY manifest.retrieved_at DESC,manifest.snapshot_sha256 DESC LIMIT 1)
           ) AS snapshot_sha256
    FROM sources
), revisions AS (
    SELECT latest.source_id, latest.snapshot_sha256,
           (SELECT count(*)::text || ':' || COALESCE(max(evidence.created_at)::text,'-')
            FROM real_preview.geocode_display_evidence evidence
            JOIN real_preview.candidates candidate USING (candidate_id)
            WHERE candidate.source_id=latest.source_id
              AND candidate.snapshot_sha256=latest.snapshot_sha256) AS geocode_revision,
           (SELECT count(*)::text || ':' || COALESCE(max(evidence.created_at)::text,'-')
            FROM real_preview.local_reference_display_evidence evidence
            JOIN real_preview.candidates candidate USING (candidate_id)
            WHERE candidate.source_id=latest.source_id
              AND candidate.snapshot_sha256=latest.snapshot_sha256) AS local_reference_revision
    FROM latest
)
SELECT COALESCE(string_agg(
           source_id || ':' || snapshot_sha256 || ':g' || geocode_revision || ':l' || local_reference_revision,
           ',' ORDER BY source_id), 'no-snapshots')
FROM revisions;
$$;

COMMENT ON FUNCTION real_preview.display_evidence_revision() IS
    'Row-free append-only evidence revision for invalidating the private map projection cache.';

CREATE FUNCTION real_preview.sync_geoapify_private_display()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    UPDATE real_preview.candidates
       SET display_latitude = NEW.display_latitude,
           display_longitude = NEW.display_longitude,
           display_geometry_source = NEW.display_geometry_source,
           coordinate_method = 'geoapify_forward',
           coordinate_provider = 'Geoapify',
           coordinate_confidence = NEW.match_confidence,
           coordinate_confidence_band = 'high'
     WHERE candidate_id = NEW.candidate_id;
    RETURN NEW;
END;
$$;
CREATE TRIGGER real_preview_geocode_provider_display_sync
    AFTER INSERT ON real_preview.geocode_display_evidence
    FOR EACH ROW EXECUTE FUNCTION real_preview.sync_geoapify_private_display();

COMMENT ON TABLE real_preview.geocode_display_evidence IS
    'Private immutable Geoapify-derived display geometry; high confidence is a documented heuristic, locality points remain approximate, and no row grants publication eligibility.';
