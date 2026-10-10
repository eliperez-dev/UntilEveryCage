-- Release-built, allowlisted detail is deliberately separate from raw evidence.
-- It is used only after the existing live release/review/suppression gates.
ALTER TABLE uec.public_discovery_read_model_rows
    ADD COLUMN public_detail JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN public_search_text TEXT NOT NULL DEFAULT '';

CREATE INDEX public_discovery_read_model_search_idx
    ON uec.public_discovery_read_model_rows USING GIN (public_search_text gin_trgm_ops);

CREATE OR REPLACE FUNCTION uec.public_discovery_detail_from_observation(observation JSONB)
RETURNS JSONB LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE
    names JSONB := '[]'::jsonb;
    volumes JSONB := '[]'::jsonb;
    detail JSONB;
    value JSONB;
BEGIN
    -- The observation is normalized input, but never returned wholesale.  Keep
    -- only the explicitly documented source-native fields; addresses, contacts,
    -- source_values, and every unknown key remain private.
    IF jsonb_typeof(observation->'alternate_names') = 'array' THEN
        names := observation->'alternate_names';
    ELSIF jsonb_typeof(observation->'dba_names') = 'array' THEN
        names := observation->'dba_names';
    ELSIF jsonb_typeof(observation->'dba_names') = 'string' AND btrim(observation->>'dba_names') <> '' THEN
        names := jsonb_build_array(observation->>'dba_names');
    ELSIF jsonb_typeof(observation->'dbas') = 'array' THEN
        names := observation->'dbas';
    END IF;
    IF jsonb_typeof(observation->'source_volume_categories') = 'array' THEN
        volumes := observation->'source_volume_categories';
    ELSIF jsonb_typeof(observation->'activity_volume_codes') = 'object' THEN
        SELECT COALESCE(jsonb_agg(jsonb_build_object('code', code,
            'provenance', jsonb_build_object('source_field', 'activity_volume_codes', 'method', 'source_native')) ORDER BY code), '[]'::jsonb)
          INTO volumes FROM jsonb_object_keys(observation->'activity_volume_codes') AS code;
    ELSIF jsonb_typeof(observation->'processing_volume_category') = 'string' THEN
        volumes := jsonb_build_array(jsonb_build_object('code', observation->>'processing_volume_category',
            'provenance', jsonb_build_object('source_field', 'processing_volume_category', 'method', 'source_native')));
    END IF;
    detail := jsonb_strip_nulls(jsonb_build_object(
        'alternate_names', names,
        'species_slaughtered', CASE WHEN jsonb_typeof(observation->'species_slaughtered')='object' THEN observation->'species_slaughtered' END,
        'processing_activities', CASE WHEN jsonb_typeof(observation->'processing_activities')='object' THEN observation->'processing_activities' END,
        'source_volume_categories', volumes,
        'establishment_id', observation->>'establishment_id',
        'establishment_number', observation->>'establishment_number',
        'grant_date', observation->>'grant_date',
        'native_activity_code', COALESCE(observation->>'activity_code', observation->>'source_activity_code'),
        'native_activity_label', COALESCE(observation->>'activity_label', observation->>'source_activity_label')
    ));
    -- Do not publish empty optional fields; an absent value means unknown.
    IF names = '[]'::jsonb THEN detail := detail - 'alternate_names'; END IF;
    IF volumes = '[]'::jsonb THEN detail := detail - 'source_volume_categories'; END IF;
    RETURN detail;
END;
$$;

COMMENT ON COLUMN uec.public_discovery_read_model_rows.public_detail IS
    'Release-built allowlisted native detail; excludes raw fields, contacts, and street addresses.';
COMMENT ON COLUMN uec.public_discovery_read_model_rows.public_search_text IS
    'Release-built allowlisted literal search text; existing immutable model rows retain an empty value and use the safe query fallback.';

-- The compatibility view resolves a candidate-cohort decision through a
-- per-row UNION/LATERAL lookup.  The cohort scope is already keyed by this
-- release, source and artifact, so this API-only projection is equivalent but
-- avoids rebuilding that same immutable decision for every facility.  It
-- retains the live release, manifest, event-review, access and suppression
-- predicates; it is not a cache and never changes model rows.
CREATE OR REPLACE VIEW uec.public_discovery_api_read_model AS
WITH base AS MATERIALIZED (
  SELECT model.*, release.ruleset_version AS release_ruleset_version,
         release.created_at AS release_created_at, release.profile, release.summary
    FROM uec.public_discovery_read_model_rows model
    JOIN uec.public_discovery_read_models metadata ON metadata.release_id=model.release_id
    JOIN uec.releases release ON release.release_id=model.release_id AND release.profile IS NOT NULL
    JOIN uec.release_manifests manifest ON manifest.release_id=model.release_id AND manifest.manifest_sha256=metadata.manifest_sha256
   WHERE release.status='promoted' AND release.test_only IS NOT TRUE
     AND NOT EXISTS (SELECT 1 FROM uec.record_access_current access
                      WHERE access.source_record_id=model.source_record_id AND access.action='public_access_revoked')
     AND NOT EXISTS (
       SELECT 1 FROM uec.suppression_case_current current_case
       JOIN uec.suppression_cases case_record ON case_record.case_id=current_case.case_id
       JOIN uec.suppression_references ref ON ref.case_id=case_record.case_id
       JOIN uec.source_records suppressed ON ((ref.facility_id IS NOT NULL AND
            (EXISTS (SELECT 1 FROM uec.facility_source_links link WHERE link.facility_id=ref.facility_id AND link.source_record_id=suppressed.source_record_id)
             OR EXISTS (SELECT 1 FROM uec.observations observation WHERE observation.facility_id=ref.facility_id AND observation.source_record_id=suppressed.source_record_id)))
            OR (ref.source_id=suppressed.source_id AND ref.source_record_key=suppressed.source_record_key))
       WHERE current_case.event_type='suppressed' AND case_record.status IN ('active','review','closed','expired')
         AND suppressed.source_record_id=model.source_record_id)
), candidate_reviews AS MATERIALIZED (
  SELECT cohort.release_id, cohort.source_id, cohort.artifact_id,
         cohort.factual_review_status, cohort.privacy_screening_status,
         cohort.maintainer_approval, cohort_document.reviewer_role,
         cohort.publication_eligible
    FROM uec.release_cohort_review_scopes cohort
    LEFT JOIN uec.release_cohort_review_documents cohort_document
      ON cohort_document.release_id=cohort.release_id
   WHERE cohort.publication_eligible=true
     AND cohort.privacy_screening_status='passed'
     AND cohort.factual_review_status<>'rejected'
), candidate_review_records AS MATERIALIZED (
  SELECT record.source_record_id, cohort.release_id,
         cohort.factual_review_status, cohort.privacy_screening_status,
         cohort.maintainer_approval, cohort.reviewer_role, cohort.publication_eligible
    FROM candidate_reviews cohort
    JOIN uec.source_records record
      ON record.source_id=cohort.source_id AND record.artifact_id=cohort.artifact_id
), eligible AS (
  SELECT base.*, cohort.factual_review_status, cohort.privacy_screening_status,
         cohort.maintainer_approval, cohort.reviewer_role, cohort.publication_eligible
    FROM base
    JOIN candidate_review_records cohort
      ON cohort.release_id=base.release_id AND cohort.source_record_id=base.source_record_id
   WHERE base.summary->>'candidate_only'='true'
     AND (cohort.maintainer_approval='approved'
          OR (base.profile='community' AND base.provenance_origin_type='user_submitted'
              AND cohort.factual_review_status='unreviewed' AND cohort.maintainer_approval='pending'))
  UNION ALL
  SELECT base.*, event_review.factual_review_status, event_review.privacy_screening_status,
         event_review.maintainer_approval, event_review.reviewer_role,
         event_review.publication_eligible
    FROM base
    JOIN LATERAL (
      SELECT event.factual_review_status, event.privacy_screening_status, event.maintainer_approval,
             event.reviewer_role, event.publication_eligible
        FROM uec.publication_review_events event
        JOIN uec.publication_review_release_scopes scope
          ON scope.publication_review_event_id=event.publication_review_event_id AND scope.release_id=base.release_id
       WHERE event.source_record_id=base.source_record_id
       ORDER BY event.reviewed_at DESC, event.publication_review_event_id DESC LIMIT 1
    ) event_review ON true
   WHERE base.summary->>'candidate_only' IS DISTINCT FROM 'true'
     AND event_review.publication_eligible=true
     AND event_review.privacy_screening_status='passed'
     AND event_review.factual_review_status<>'rejected'
     AND (event_review.maintainer_approval='approved'
          OR (base.profile='community' AND base.provenance_origin_type='user_submitted'
              AND event_review.factual_review_status='unreviewed' AND event_review.maintainer_approval='pending'))
)
SELECT eligible.*,
       max(eligible.observed_at) OVER (PARTITION BY eligible.release_id, eligible.facility_id) AS last_observed_at,
       (count(*) OVER (PARTITION BY eligible.release_id, eligible.facility_id))::int AS observation_count,
       COALESCE(lifecycle.status,'status_unknown') AS lifecycle_status,
       lifecycle.effective_at AS lifecycle_effective_at, lifecycle.source_record_id AS lifecycle_source_record_id
  FROM eligible LEFT JOIN uec.facility_lifecycle_current lifecycle ON lifecycle.facility_id=eligible.facility_id;

COMMENT ON VIEW uec.public_discovery_api_read_model IS
  'API-only manifest-bound public read projection with live gates and direct candidate-cohort review lookup.';
