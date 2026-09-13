-- Lifecycle is separate from observations; disappearance never implies closure.
CREATE TABLE IF NOT EXISTS uec.facility_lifecycle_events (
    lifecycle_event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    facility_id UUID NOT NULL REFERENCES uec.facilities(facility_id),
    status TEXT NOT NULL CHECK (status IN ('active_observed', 'explicitly_closed', 'not_seen_recently', 'status_unknown')),
    effective_at TIMESTAMPTZ,
    source_record_id UUID REFERENCES uec.source_records(source_record_id),
    evidence_note TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS facility_lifecycle_current_lookup
    ON uec.facility_lifecycle_events (facility_id, created_at DESC, lifecycle_event_id DESC);

CREATE OR REPLACE VIEW uec.facility_observation_summary AS
SELECT facility_id, min(first_observed_at) AS first_observed_at,
       max(observed_at) AS last_observed_at, count(*)::int AS observation_count
FROM uec.observations
GROUP BY facility_id;

CREATE OR REPLACE VIEW uec.facility_lifecycle_current AS
SELECT DISTINCT ON (facility_id) facility_id, status, effective_at,
       source_record_id, evidence_note, created_at
FROM uec.facility_lifecycle_events
ORDER BY facility_id, created_at DESC, lifecycle_event_id DESC;

DROP TRIGGER IF EXISTS facility_lifecycle_events_append_only ON uec.facility_lifecycle_events;
CREATE TRIGGER facility_lifecycle_events_append_only
    BEFORE UPDATE OR DELETE ON uec.facility_lifecycle_events
    FOR EACH STATEMENT EXECUTE FUNCTION uec.reject_evidence_mutation();
