-- Use one live eligibility predicate for current and historical graph keys.
-- Preserve the current-only public-map facade and all review/restriction gates.
CREATE VIEW uec.public_discovery_release_eligible_rows AS
SELECT model.*,
       release.ruleset_version AS release_ruleset_version,
       release.created_at AS release_created_at,
       review.factual_review_status,
       review.privacy_screening_status,
       review.maintainer_approval,
       review.reviewer_role
FROM uec.public_discovery_read_model_rows model
JOIN uec.public_discovery_read_models metadata
  ON metadata.release_id=model.release_id
JOIN uec.releases release
  ON release.release_id=model.release_id AND release.profile IS NOT NULL
JOIN uec.release_manifests manifest
  ON manifest.release_id=model.release_id
 AND manifest.manifest_sha256=metadata.manifest_sha256
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
WHERE (release.status='promoted' OR (release.status='validated' AND EXISTS (
      SELECT 1 FROM uec.public_release_history history
      WHERE history.release_id=release.release_id AND history.profile=release.profile)))
  AND release.test_only IS NOT TRUE
  AND review.publication_eligible=true
  AND review.privacy_screening_status='passed'
  AND review.factual_review_status<>'rejected'
  AND (
      review.maintainer_approval='approved'
      OR (release.profile='community'
          AND model.provenance_origin_type='user_submitted'
          AND review.factual_review_status='unreviewed'
          AND review.maintainer_approval='pending')
  )
  AND NOT EXISTS (
      SELECT 1 FROM uec.public_access_restricted restricted
      WHERE restricted.source_record_id=model.source_record_id
  );

CREATE OR REPLACE VIEW uec.public_discovery_live_eligible_rows AS
SELECT eligible.*
FROM uec.public_discovery_release_eligible_rows eligible
JOIN uec.releases release ON release.release_id=eligible.release_id
WHERE release.status='promoted';

CREATE OR REPLACE VIEW uec.graph_public_live_facility_anchors_current AS
SELECT release_id,source_record_id,facility_id
FROM uec.public_discovery_release_eligible_rows;

COMMENT ON VIEW uec.public_discovery_release_eligible_rows IS
    'Shared manifest-bound eligibility for promoted and validated published historical releases, with current review and suppression.';

