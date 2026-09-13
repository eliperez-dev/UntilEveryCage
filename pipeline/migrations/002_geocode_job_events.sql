-- Add event-sourced geocoding scheduling to an existing V2 database.
-- Safe to run after 001_initial.sql without deleting or rewriting evidence.

CREATE TABLE IF NOT EXISTS uec.geocode_jobs (
    job_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_record_id UUID NOT NULL REFERENCES uec.source_records(source_record_id),
    provider_id TEXT NOT NULL,
    query TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source_record_id, provider_id, query)
);

CREATE TABLE IF NOT EXISTS uec.geocode_job_events (
    event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES uec.geocode_jobs(job_id),
    event_type TEXT NOT NULL CHECK (event_type IN ('queued', 'started', 'accepted', 'review_required', 'unresolved', 'failed', 'cancelled')),
    attempt_number INTEGER NOT NULL DEFAULT 1 CHECK (attempt_number >= 1),
    retryable BOOLEAN NOT NULL DEFAULT false,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    worker_id TEXT,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE OR REPLACE VIEW uec.geocode_job_current AS
SELECT DISTINCT ON (job.job_id)
    job.job_id, job.source_record_id, job.provider_id, job.query,
    event.event_type, event.attempt_number, event.retryable, event.details,
    event.worker_id, event.occurred_at
FROM uec.geocode_jobs AS job
JOIN uec.geocode_job_events AS event ON event.job_id = job.job_id
ORDER BY job.job_id, event.occurred_at DESC, event.event_id DESC;

CREATE INDEX IF NOT EXISTS geocode_job_events_job_idx ON uec.geocode_job_events (job_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS geocode_job_events_status_idx ON uec.geocode_job_events (event_type, occurred_at DESC);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'geocode_jobs_append_only' AND tgrelid = 'uec.geocode_jobs'::regclass) THEN
        CREATE TRIGGER geocode_jobs_append_only BEFORE UPDATE OR DELETE ON uec.geocode_jobs FOR EACH ROW EXECUTE FUNCTION uec.reject_evidence_mutation();
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'geocode_job_events_append_only' AND tgrelid = 'uec.geocode_job_events'::regclass) THEN
        CREATE TRIGGER geocode_job_events_append_only BEFORE UPDATE OR DELETE ON uec.geocode_job_events FOR EACH ROW EXECUTE FUNCTION uec.reject_evidence_mutation();
    END IF;
END;
$$;
