-- Keep the geometry interpretation that selected a display point visible to
-- public clients. This contains only allowlisted method and precision metadata.
ALTER TABLE uec.public_discovery_read_model_rows
    ADD COLUMN geometry_provenance JSONB NOT NULL DEFAULT '{"origin":"unmapped"}'::jsonb;

CREATE OR REPLACE VIEW uec.map_facilities_public_discovery_read_model AS
WITH eligible AS (
    SELECT model.*,
           release.ruleset_version AS release_ruleset_version,
           release.created_at AS release_created_at,
           review.factual_review_status,
           review.privacy_screening_status,
           review.maintainer_approval,
           review.reviewer_role
    FROM uec.public_discovery_read_model_rows model
    JOIN uec.public_discovery_read_models metadata
      ON metadata.release_id = model.release_id
    JOIN uec.releases release
      ON release.release_id = model.release_id
     AND release.profile IS NOT NULL
    JOIN uec.release_manifests manifest
      ON manifest.release_id = model.release_id
     AND manifest.manifest_sha256 = metadata.manifest_sha256
    JOIN uec.source_records record ON record.source_record_id=model.source_record_id
    JOIN LATERAL (
        SELECT decision.factual_review_status, decision.privacy_screening_status,
               decision.maintainer_approval, decision.reviewer_role,
               decision.publication_eligible
        FROM (
            SELECT event.factual_review_status, event.privacy_screening_status,
                   event.maintainer_approval, event.reviewer_role,
                   event.publication_eligible, event.reviewed_at AS decided_at,
                   event.publication_review_event_id::text AS tie_break
            FROM uec.publication_review_events event
            JOIN uec.publication_review_release_scopes event_scope
              ON event_scope.publication_review_event_id=event.publication_review_event_id
             AND event_scope.release_id=model.release_id
            WHERE event.source_record_id=model.source_record_id
              AND release.summary->>'candidate_only' IS DISTINCT FROM 'true'
            UNION ALL
            SELECT cohort.factual_review_status, cohort.privacy_screening_status,
                   cohort.maintainer_approval, cohort.reviewer_role,
                   cohort.publication_eligible, cohort.reviewed_at AS decided_at,
                   cohort.document_sha256 AS tie_break
            FROM uec.release_cohort_review_current cohort
            WHERE cohort.release_id=model.release_id
              AND cohort.source_id=record.source_id
              AND cohort.artifact_id=record.artifact_id
              AND release.summary->>'candidate_only'='true'
        ) decision
        ORDER BY decision.decided_at DESC, decision.tie_break DESC
        LIMIT 1
    ) review ON true
    WHERE release.status = 'promoted'
      AND release.test_only IS NOT TRUE
      AND review.publication_eligible = true
      AND review.privacy_screening_status = 'passed'
      AND review.factual_review_status <> 'rejected'
      AND (
          review.maintainer_approval = 'approved'
          OR (release.profile = 'community'
              AND model.provenance_origin_type = 'user_submitted'
              AND review.factual_review_status = 'unreviewed'
              AND review.maintainer_approval = 'pending')
      )
      AND NOT EXISTS (
          SELECT 1 FROM uec.record_access_current access
          WHERE access.source_record_id = model.source_record_id
            AND access.action = 'public_access_revoked'
      )
      AND NOT EXISTS (
          SELECT 1
          FROM uec.suppression_case_current current_case
          JOIN uec.suppression_cases case_record ON case_record.case_id = current_case.case_id
          JOIN uec.suppression_references ref ON ref.case_id = case_record.case_id
          JOIN uec.source_records record ON (
              (ref.facility_id IS NOT NULL AND (
                  EXISTS (SELECT 1 FROM uec.facility_source_links link
                          WHERE link.facility_id = ref.facility_id
                            AND link.source_record_id = record.source_record_id)
                  OR EXISTS (SELECT 1 FROM uec.observations observation
                             WHERE observation.facility_id = ref.facility_id
                               AND observation.source_record_id = record.source_record_id)
              ))
              OR (ref.source_id = record.source_id
                  AND ref.source_record_key = record.source_record_key)
          )
          WHERE current_case.event_type = 'suppressed'
            AND case_record.status IN ('active', 'review', 'closed', 'expired')
            AND record.source_record_id = model.source_record_id
      )
)
SELECT eligible.release_id,
       'promoted'::text AS release_status,
       true AS release_visible,
       eligible.observation_id,
       eligible.facility_id,
       eligible.source_record_id,
       eligible.canonical_name,
       eligible.country_code,
       NULL::text AS street_address,
       eligible.postal_code,
       eligible.city,
       eligible.display_location,
       eligible.display_precision,
       eligible.display_label,
       eligible.geocoding_status,
       eligible.geocoder_provider,
       eligible.geocoded_at,
       eligible.classification_category,
       min(eligible.first_observed_at) OVER facility_history AS first_observed_at,
       max(eligible.observed_at) OVER facility_history AS last_observed_at,
       (count(*) OVER facility_history)::int AS observation_count,
       COALESCE(lifecycle.status, 'status_unknown') AS lifecycle_status,
       lifecycle.effective_at AS lifecycle_effective_at,
       lifecycle.source_record_id AS lifecycle_source_record_id,
       eligible.release_ruleset_version,
       eligible.release_created_at,
       eligible.provenance_origin_type,
       eligible.provenance_source_id,
       eligible.provenance_source_name,
       eligible.provenance_source_url,
       eligible.provenance_retrieved_at,
       eligible.source_rights_status,
       eligible.factual_review_status,
       eligible.privacy_screening_status,
       eligible.maintainer_approval,
       eligible.reviewer_role,
       eligible.geometry_provenance
FROM eligible
LEFT JOIN uec.facility_lifecycle_current lifecycle
  ON lifecycle.facility_id = eligible.facility_id
WINDOW facility_history AS (PARTITION BY eligible.release_id, eligible.facility_id);

COMMENT ON COLUMN uec.public_discovery_read_model_rows.geometry_provenance IS
    'Allowlisted display geometry origin, method, and source precision; excludes source addresses, provider queries, and raw responses.';
