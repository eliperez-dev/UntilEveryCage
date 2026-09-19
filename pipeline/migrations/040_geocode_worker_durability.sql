-- Durable worker leases and conservative provider-request accounting.
-- This migration only adds tables/columns; existing event and result history is
-- retained. A request reservation is committed before the provider call.

ALTER TABLE uec.geocode_job_events
    ADD COLUMN IF NOT EXISTS lease_token UUID;

CREATE TABLE IF NOT EXISTS uec.geocode_provider_budgets (
    provider_id TEXT NOT NULL,
    budget_date DATE NOT NULL,
    daily_limit INTEGER NOT NULL CHECK (daily_limit >= 1),
    reserved_requests INTEGER NOT NULL DEFAULT 0
        CHECK (reserved_requests >= 0 AND reserved_requests <= daily_limit),
    last_reserved_at TIMESTAMPTZ,
    PRIMARY KEY (provider_id, budget_date)
);

-- One row represents one provider request, including a retry. It is deliberately
-- append-only so an operator can reconcile the counter with outbound attempts.
CREATE TABLE IF NOT EXISTS uec.geocode_request_reservations (
    reservation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    provider_id TEXT NOT NULL,
    budget_date DATE NOT NULL,
    job_id UUID NOT NULL REFERENCES uec.geocode_jobs(job_id),
    attempt_number INTEGER NOT NULL CHECK (attempt_number >= 1),
    retry_number INTEGER NOT NULL CHECK (retry_number >= 1),
    reserved_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (job_id, attempt_number, retry_number),
    FOREIGN KEY (provider_id, budget_date)
        REFERENCES uec.geocode_provider_budgets(provider_id, budget_date)
);

CREATE INDEX IF NOT EXISTS geocode_request_reservations_provider_day_idx
    ON uec.geocode_request_reservations (provider_id, budget_date, reserved_at);

CREATE OR REPLACE VIEW uec.geocode_job_current AS
SELECT DISTINCT ON (job.job_id)
    job.job_id, job.source_record_id, job.provider_id, job.query,
    event.event_type, event.attempt_number, event.retryable, event.details,
    event.worker_id, event.occurred_at, event.lease_token
FROM uec.geocode_jobs AS job
JOIN uec.geocode_job_events AS event ON event.job_id = job.job_id
ORDER BY job.job_id, event.occurred_at DESC, event.event_id DESC;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'geocode_request_reservations_append_only'
          AND tgrelid = 'uec.geocode_request_reservations'::regclass
    ) THEN
        CREATE TRIGGER geocode_request_reservations_append_only
            BEFORE UPDATE OR DELETE ON uec.geocode_request_reservations
            FOR EACH ROW EXECUTE FUNCTION uec.reject_evidence_mutation();
    END IF;
END;
$$;
