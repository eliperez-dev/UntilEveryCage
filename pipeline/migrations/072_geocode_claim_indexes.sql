-- The source-profile worker repeatedly reads the latest event per job and
-- verifies its immutable queued profile marker while claiming work.  These
-- indexes keep that private scheduling path bounded without changing any
-- lease, restriction, reservation, or result semantics.
CREATE INDEX IF NOT EXISTS geocode_job_events_current_order_idx
    ON uec.geocode_job_events (job_id, occurred_at DESC, event_id DESC);

CREATE INDEX IF NOT EXISTS geocode_job_events_private_profile_queue_idx
    ON uec.geocode_job_events (job_id)
    WHERE event_type = 'queued'
      AND details->>'processing_mode' = 'private_geoapify_source_profile'
      AND details->>'profile_id' = 'geoapify-us-aphis-mailing-locality';
