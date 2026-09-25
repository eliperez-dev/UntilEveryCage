-- Link ordinary durable geocode jobs to source-scoped preview candidates.
-- The provider worker remains the single owner of claims, leases, reservations,
-- retries, and result persistence. This table supplies only target identity.
CREATE TABLE IF NOT EXISTS real_preview.geocode_targets (
    job_id UUID PRIMARY KEY REFERENCES uec.geocode_jobs(job_id),
    candidate_id UUID NOT NULL UNIQUE REFERENCES real_preview.candidates(candidate_id),
    snapshot_sha256 CHAR(64) NOT NULL,
    source_id TEXT NOT NULL,
    source_record_key TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    FOREIGN KEY (snapshot_sha256, source_id, source_record_key)
        REFERENCES real_preview.candidates(snapshot_sha256, source_id, source_group_key),
    UNIQUE (candidate_id, job_id)
);

-- Keep target identity unambiguous and immutable after enqueue.
CREATE OR REPLACE FUNCTION real_preview.reject_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'real preview evidence is append-only';
END;
$$;
CREATE TRIGGER real_preview_geocode_targets_immutable
    BEFORE UPDATE OR DELETE ON real_preview.geocode_targets
    FOR EACH ROW EXECUTE FUNCTION real_preview.reject_mutation();

CREATE TABLE IF NOT EXISTS real_preview.enrichment_state_events (
    event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id UUID NOT NULL REFERENCES real_preview.candidates(candidate_id),
    snapshot_sha256 CHAR(64) NOT NULL,
    source_id TEXT NOT NULL,
    source_record_key TEXT NOT NULL,
    state_code TEXT NOT NULL CHECK (state_code IN (
        'source_coordinate', 'coarse_eligible', 'exact_eligible', 'queued',
        'resolved', 'insufficient', 'restricted', 'provider_blocked',
        'retryable', 'unresolved', 'conflict'
    )),
    reason_code TEXT NOT NULL CHECK (reason_code ~ '^[a-z][a-z0-9_]{1,63}$'),
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    FOREIGN KEY (snapshot_sha256, source_id, source_record_key)
        REFERENCES real_preview.candidates(snapshot_sha256, source_id, source_group_key)
);
CREATE INDEX IF NOT EXISTS real_preview_enrichment_latest_idx
    ON real_preview.enrichment_state_events(candidate_id, occurred_at DESC, event_id DESC);
CREATE TRIGGER real_preview_enrichment_state_events_immutable
    BEFORE UPDATE OR DELETE ON real_preview.enrichment_state_events
    FOR EACH ROW EXECUTE FUNCTION real_preview.reject_mutation();

CREATE TABLE IF NOT EXISTS real_preview.geocode_display_evidence (
    evidence_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id UUID NOT NULL REFERENCES real_preview.candidates(candidate_id),
    geocode_result_id UUID NOT NULL REFERENCES uec.geocode_results(geocode_result_id),
    display_latitude DOUBLE PRECISION NOT NULL,
    display_longitude DOUBLE PRECISION NOT NULL,
    display_precision TEXT NOT NULL,
    display_geometry_source TEXT NOT NULL,
    coordinate_review_status TEXT NOT NULL DEFAULT 'pending_human_review'
        CHECK (coordinate_review_status = 'pending_human_review'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (display_latitude BETWEEN -90 AND 90),
    CHECK (display_longitude BETWEEN -180 AND 180),
    CHECK (display_latitude <> 0 OR display_longitude <> 0),
    UNIQUE (candidate_id, geocode_result_id)
);
CREATE INDEX IF NOT EXISTS real_preview_geocode_display_latest_idx
    ON real_preview.geocode_display_evidence(candidate_id, created_at DESC, evidence_id DESC);
CREATE TRIGGER real_preview_geocode_display_evidence_immutable
    BEFORE UPDATE OR DELETE ON real_preview.geocode_display_evidence
    FOR EACH ROW EXECUTE FUNCTION real_preview.reject_mutation();

CREATE OR REPLACE VIEW real_preview.enrichment_state_current AS
SELECT DISTINCT ON (event.candidate_id)
       event.candidate_id, event.snapshot_sha256, event.source_id,
       event.source_record_key, event.state_code, event.reason_code,
       event.occurred_at
FROM real_preview.enrichment_state_events event
ORDER BY event.candidate_id, event.occurred_at DESC, event.event_id DESC;

-- Exactly one current reconciliation state for each accepted candidate in the
-- latest source snapshot, including candidates not yet initialized by a source
-- lane. This is private operator data, not a display or publication view.
CREATE OR REPLACE VIEW real_preview.candidate_enrichment_reconciliation AS
WITH latest AS (
    SELECT DISTINCT ON (source_id) source_id, snapshot_sha256
    FROM real_preview.source_preview_runs
    ORDER BY source_id, created_at DESC, run_id DESC
), accepted AS (
    SELECT candidate.*
    FROM real_preview.candidates candidate
    JOIN latest USING (source_id, snapshot_sha256)
), current_state AS (
    SELECT DISTINCT ON (candidate_id) candidate_id, state_code, reason_code
    FROM real_preview.enrichment_state_events
    ORDER BY candidate_id, occurred_at DESC, event_id DESC
)
SELECT candidate.candidate_id, candidate.source_id, candidate.snapshot_sha256,
       CASE
         WHEN state.state_code IS NOT NULL THEN state.state_code
         WHEN candidate.location_class = 'numeric_source_coordinate' THEN 'source_coordinate'
         WHEN candidate.location_class = 'city_postal' THEN 'unresolved'
         ELSE 'insufficient'
       END AS state_code,
       COALESCE(state.reason_code,
         CASE WHEN candidate.location_class = 'numeric_source_coordinate' THEN 'source_coordinate_present'
              WHEN candidate.location_class = 'city_postal' THEN 'enrichment_not_queued'
              ELSE 'no_usable_location_input' END) AS reason_code
FROM accepted candidate
LEFT JOIN current_state state USING (candidate_id);

COMMENT ON TABLE real_preview.geocode_targets IS
    'Append-only association from the shared leased geocode worker queue to a stable, source-scoped real-preview candidate.';
COMMENT ON TABLE real_preview.enrichment_state_events IS
    'Private candidate geospatial state and reason history; aggregate-only operator reporting.';
COMMENT ON TABLE real_preview.geocode_display_evidence IS
    'Private provider-derived display geometry with provenance; remains approximate and pending human review.';
