-- Preserve the live-gated projection while allowing an API release_id filter
-- to constrain candidate review scopes before source-record expansion.
CREATE OR REPLACE VIEW uec.public_discovery_api_read_model AS
WITH base AS NOT MATERIALIZED (
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
), candidate_reviews AS NOT MATERIALIZED (
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
), candidate_review_records AS NOT MATERIALIZED (
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
  'API-only manifest-bound public read projection with live gates and release-filter pushdown for candidate cohort review.';
