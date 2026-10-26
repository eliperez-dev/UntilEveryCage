-- Project an effective private enrichment state from append-only source events,
-- the current candidate display, and the indexed current target/job event.
-- This view changes no evidence and preserves its existing API columns.
CREATE OR REPLACE VIEW real_preview.candidate_enrichment_reconciliation AS
WITH latest AS (
    SELECT DISTINCT ON (source_id) source_id, snapshot_sha256
    FROM real_preview.source_preview_runs
    ORDER BY source_id, created_at DESC, run_id DESC
), accepted AS (
    SELECT candidate.*
    FROM real_preview.candidates candidate
    JOIN latest USING (source_id, snapshot_sha256)
)
SELECT candidate.candidate_id, candidate.source_id, candidate.snapshot_sha256,
       CASE
         WHEN COALESCE(state.state_code = 'restricted', false) OR COALESCE(work.is_restricted, false)
           THEN 'restricted'
         WHEN candidate.location_class = 'numeric_source_coordinate'
              OR state.state_code = 'source_coordinate' THEN 'source_coordinate'
         WHEN display.display_latitude BETWEEN -90 AND 90
              AND display.display_longitude BETWEEN -180 AND 180
              AND (display.display_latitude <> 0 OR display.display_longitude <> 0) THEN 'resolved'
         WHEN work.event_type IN ('accepted', 'review_required') THEN 'conflict'
         WHEN work.event_type = 'unresolved' OR work.event_type = 'cancelled' THEN 'unresolved'
         WHEN work.event_type = 'failed' AND work.retryable THEN 'retryable'
         WHEN work.event_type = 'failed' THEN 'provider_blocked'
         WHEN work.event_type IN ('queued', 'started') THEN 'queued'
         WHEN state.state_code IS NOT NULL THEN state.state_code
         WHEN candidate.location_class = 'city_postal' THEN 'unresolved'
         ELSE 'insufficient'
       END AS state_code,
       CASE
         WHEN COALESCE(state.state_code = 'restricted', false) THEN state.reason_code
         WHEN COALESCE(work.is_restricted, false) THEN 'source_record_restricted'
         WHEN candidate.location_class = 'numeric_source_coordinate'
              OR state.state_code = 'source_coordinate'
           THEN 'source_coordinate_present'
         WHEN display.display_latitude BETWEEN -90 AND 90
              AND display.display_longitude BETWEEN -180 AND 180
              AND (display.display_latitude <> 0 OR display.display_longitude <> 0)
           THEN 'display_geometry_available'
         WHEN work.event_type = 'accepted' THEN 'provider_result_not_displayable'
         WHEN work.event_type = 'review_required' THEN 'provider_review_required'
         WHEN work.event_type = 'unresolved' THEN 'provider_unresolved'
         WHEN work.event_type = 'cancelled' THEN 'provider_job_cancelled'
         WHEN work.event_type = 'failed' AND work.retryable THEN 'provider_retryable_failure'
         WHEN work.event_type = 'failed' THEN 'provider_nonretryable_failure'
         WHEN work.event_type IN ('queued', 'started') THEN 'provider_job_active'
         WHEN state.reason_code IS NOT NULL THEN state.reason_code
         WHEN candidate.location_class = 'numeric_source_coordinate' THEN 'source_coordinate_present'
         WHEN candidate.location_class = 'city_postal' THEN 'enrichment_not_queued'
         ELSE 'no_usable_location_input'
       END AS reason_code
FROM accepted candidate
LEFT JOIN LATERAL (
    SELECT event.state_code, event.reason_code
    FROM real_preview.enrichment_state_events event
    WHERE event.candidate_id = candidate.candidate_id
      AND event.snapshot_sha256 = candidate.snapshot_sha256
    ORDER BY event.occurred_at DESC, event.event_id DESC
    LIMIT 1
) state ON true
LEFT JOIN real_preview.candidate_display display
  ON display.candidate_id = candidate.candidate_id
 AND display.snapshot_sha256 = candidate.snapshot_sha256
LEFT JOIN LATERAL (
    SELECT current_event.event_type, current_event.retryable,
           EXISTS (
               SELECT 1 FROM uec.public_access_restricted restricted
               WHERE restricted.source_record_id = job.source_record_id
           ) AS is_restricted
    FROM real_preview.geocode_targets target
    JOIN uec.geocode_jobs job ON job.job_id = target.job_id
    LEFT JOIN LATERAL (
        SELECT event.event_type, event.retryable
        FROM uec.geocode_job_events event
        WHERE event.job_id = job.job_id
        ORDER BY event.occurred_at DESC, event.event_id DESC
        LIMIT 1
    ) current_event ON true
    WHERE target.candidate_id = candidate.candidate_id
      AND target.snapshot_sha256 = candidate.snapshot_sha256
    ORDER BY target.created_at DESC, target.job_id DESC
    LIMIT 1
) work ON true;
