-- V2 maintained data schema. Raw artifacts remain in data/object storage.
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE SCHEMA IF NOT EXISTS uec;

CREATE TABLE uec.sources (
    source_id TEXT PRIMARY KEY,
    country_code CHAR(2) NOT NULL,
    name TEXT NOT NULL,
    official_url TEXT NOT NULL,
    access_method TEXT NOT NULL,
    cadence TEXT,
    status TEXT NOT NULL DEFAULT 'source_candidate' CHECK (status IN ('source_candidate', 'active', 'blocked', 'retired')),
    attribution TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE uec.acquisition_runs (
    run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id TEXT NOT NULL REFERENCES uec.sources(source_id),
    checked_at TIMESTAMPTZ NOT NULL,
    retrieved_at TIMESTAMPTZ,
    ingested_at TIMESTAMPTZ,
    status TEXT NOT NULL CHECK (status IN ('unchanged', 'changed', 'failed', 'review_required')),
    source_url TEXT NOT NULL,
    code_version TEXT,
    config_version TEXT,
    error_summary TEXT
);

CREATE TABLE uec.raw_artifacts (
    artifact_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    storage_key TEXT NOT NULL,
    sha256 CHAR(64) NOT NULL,
    byte_size BIGINT NOT NULL CHECK (byte_size >= 0),
    media_type TEXT,
    retrieved_at TIMESTAMPTZ NOT NULL,
    publication_date DATE,
    UNIQUE (sha256)
);

CREATE TABLE uec.acquisition_run_artifacts (
    run_id UUID NOT NULL REFERENCES uec.acquisition_runs(run_id),
    artifact_id UUID NOT NULL REFERENCES uec.raw_artifacts(artifact_id),
    PRIMARY KEY (run_id, artifact_id)
);

CREATE TABLE uec.source_records (
    source_record_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id TEXT NOT NULL REFERENCES uec.sources(source_id),
    source_record_key TEXT NOT NULL,
    artifact_id UUID NOT NULL REFERENCES uec.raw_artifacts(artifact_id),
    raw_fields JSONB NOT NULL,
    parsed_at TIMESTAMPTZ NOT NULL,
    source_state TEXT NOT NULL DEFAULT 'present' CHECK (source_state IN ('present', 'not_observed', 'rejected', 'superseded')),
    UNIQUE (source_id, source_record_key, artifact_id)
);

CREATE TABLE uec.facilities (
    facility_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    canonical_name TEXT,
    country_code CHAR(2) NOT NULL,
    street_address TEXT,
    postal_code TEXT,
    city TEXT,
    location GEOGRAPHY(Point, 4326),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE uec.facility_source_links (
    facility_id UUID NOT NULL REFERENCES uec.facilities(facility_id),
    source_record_id UUID NOT NULL REFERENCES uec.source_records(source_record_id),
    match_method TEXT NOT NULL,
    review_status TEXT NOT NULL CHECK (review_status IN ('automatic', 'reviewed', 'review_required')),
    decided_at TIMESTAMPTZ,
    PRIMARY KEY (facility_id, source_record_id)
);

CREATE TABLE uec.identity_decisions (
    identity_decision_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_record_id UUID NOT NULL REFERENCES uec.source_records(source_record_id),
    candidate_facility_id UUID REFERENCES uec.facilities(facility_id),
    decision TEXT NOT NULL CHECK (decision IN ('matched', 'new_facility', 'rejected', 'merge', 'split', 'review_required')),
    method TEXT NOT NULL,
    reason TEXT,
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    decided_by TEXT,
    decided_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE uec.observations (
    observation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    facility_id UUID NOT NULL REFERENCES uec.facilities(facility_id),
    source_record_id UUID NOT NULL REFERENCES uec.source_records(source_record_id),
    observed_at TIMESTAMPTZ NOT NULL,
    observation JSONB NOT NULL,
    classification JSONB NOT NULL,
    ruleset_id TEXT NOT NULL,
    rule_id TEXT NOT NULL,
    classification_category TEXT NOT NULL,
    classification_review_status TEXT NOT NULL CHECK (classification_review_status IN ('approved', 'review_required')),
    default_visible BOOLEAN NOT NULL DEFAULT false,
    optional_filter TEXT,
    coordinate GEOGRAPHY(Point, 4326),
    coordinate_method TEXT,
    coordinate_precision TEXT,
    coordinate_review_status TEXT,
    first_observed_at TIMESTAMPTZ NOT NULL,
    UNIQUE (facility_id, source_record_id, observed_at)
);

CREATE TABLE uec.geocode_results (
    geocode_result_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_record_id UUID NOT NULL REFERENCES uec.source_records(source_record_id),
    provider_id TEXT NOT NULL,
    provider_version TEXT,
    query TEXT NOT NULL,
    provider_address_id TEXT,
    result GEOGRAPHY(Point, 4326),
    precision TEXT,
    match_method TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('accepted', 'review_required', 'unresolved', 'failed')),
    attempt_number INTEGER NOT NULL DEFAULT 1 CHECK (attempt_number >= 1),
    retryable BOOLEAN NOT NULL DEFAULT false,
    response JSONB,
    queried_at TIMESTAMPTZ NOT NULL
);

-- A stable job identity separates scheduling from geocoder evidence. Job state
-- lives in the append-only event table below, not in a mutable status column.
CREATE TABLE uec.geocode_jobs (
    job_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_record_id UUID NOT NULL REFERENCES uec.source_records(source_record_id),
    provider_id TEXT NOT NULL,
    query TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source_record_id, provider_id, query)
);

CREATE TABLE uec.geocode_job_events (
    event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES uec.geocode_jobs(job_id),
    event_type TEXT NOT NULL CHECK (event_type IN ('queued', 'started', 'accepted', 'review_required', 'unresolved', 'failed', 'cancelled')),
    attempt_number INTEGER NOT NULL DEFAULT 1 CHECK (attempt_number >= 1),
    retryable BOOLEAN NOT NULL DEFAULT false,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    worker_id TEXT,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE VIEW uec.geocode_job_current AS
SELECT DISTINCT ON (job.job_id)
    job.job_id,
    job.source_record_id,
    job.provider_id,
    job.query,
    event.event_type,
    event.attempt_number,
    event.retryable,
    event.details,
    event.worker_id,
    event.occurred_at
FROM uec.geocode_jobs AS job
JOIN uec.geocode_job_events AS event ON event.job_id = job.job_id
ORDER BY job.job_id, event.occurred_at DESC, event.event_id DESC;

CREATE TABLE uec.validation_findings (
    finding_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_record_id UUID REFERENCES uec.source_records(source_record_id),
    run_id UUID REFERENCES uec.acquisition_runs(run_id),
    severity TEXT NOT NULL CHECK (severity IN ('warning', 'error', 'review')),
    code TEXT NOT NULL,
    details JSONB NOT NULL,
    resolved_at TIMESTAMPTZ
);

CREATE TABLE uec.releases (
    release_id TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    status TEXT NOT NULL CHECK (status IN ('candidate', 'validated', 'promoted', 'rejected')),
    ruleset_version TEXT NOT NULL,
    summary JSONB NOT NULL
);

CREATE TABLE uec.release_members (
    release_id TEXT NOT NULL REFERENCES uec.releases(release_id),
    facility_id UUID NOT NULL REFERENCES uec.facilities(facility_id),
    observation_id UUID NOT NULL REFERENCES uec.observations(observation_id),
    default_visible BOOLEAN NOT NULL,
    PRIMARY KEY (release_id, facility_id)
);

CREATE INDEX facilities_location_gix ON uec.facilities USING GIST (location);
CREATE INDEX observations_coordinate_gix ON uec.observations USING GIST (coordinate);
CREATE INDEX source_records_key_idx ON uec.source_records (source_id, source_record_key);
CREATE INDEX observations_facility_idx ON uec.observations (facility_id, observed_at DESC);
CREATE INDEX source_records_state_idx ON uec.source_records (source_id, source_state);
CREATE INDEX observations_visibility_idx ON uec.observations (default_visible, classification_category);
CREATE INDEX validation_findings_open_idx ON uec.validation_findings (severity) WHERE resolved_at IS NULL;
CREATE INDEX geocode_job_events_job_idx ON uec.geocode_job_events (job_id, occurred_at DESC);
CREATE INDEX geocode_job_current_status_idx ON uec.geocode_job_events (event_type, occurred_at DESC);

-- Evidence is append-only. Corrections and new interpretations are represented by
-- new rows linked to earlier evidence, never by mutation of historical rows.
CREATE OR REPLACE FUNCTION uec.reject_evidence_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'append-only table %.% rejects %; add a new version/event instead',
        TG_TABLE_SCHEMA, TG_TABLE_NAME, TG_OP
        USING ERRCODE = '55006';
END;
$$;

CREATE TRIGGER source_records_append_only
    BEFORE UPDATE OR DELETE ON uec.source_records
    FOR EACH ROW EXECUTE FUNCTION uec.reject_evidence_mutation();

CREATE TRIGGER raw_artifacts_append_only
    BEFORE UPDATE OR DELETE ON uec.raw_artifacts
    FOR EACH ROW EXECUTE FUNCTION uec.reject_evidence_mutation();

CREATE TRIGGER acquisition_run_artifacts_append_only
    BEFORE UPDATE OR DELETE ON uec.acquisition_run_artifacts
    FOR EACH ROW EXECUTE FUNCTION uec.reject_evidence_mutation();

CREATE TRIGGER facility_source_links_append_only
    BEFORE UPDATE OR DELETE ON uec.facility_source_links
    FOR EACH ROW EXECUTE FUNCTION uec.reject_evidence_mutation();

CREATE TRIGGER identity_decisions_append_only
    BEFORE UPDATE OR DELETE ON uec.identity_decisions
    FOR EACH ROW EXECUTE FUNCTION uec.reject_evidence_mutation();

CREATE TRIGGER observations_append_only
    BEFORE UPDATE OR DELETE ON uec.observations
    FOR EACH ROW EXECUTE FUNCTION uec.reject_evidence_mutation();

CREATE TRIGGER geocode_results_append_only
    BEFORE UPDATE OR DELETE ON uec.geocode_results
    FOR EACH ROW EXECUTE FUNCTION uec.reject_evidence_mutation();

CREATE TRIGGER geocode_jobs_append_only
    BEFORE UPDATE OR DELETE ON uec.geocode_jobs
    FOR EACH ROW EXECUTE FUNCTION uec.reject_evidence_mutation();

CREATE TRIGGER geocode_job_events_append_only
    BEFORE UPDATE OR DELETE ON uec.geocode_job_events
    FOR EACH ROW EXECUTE FUNCTION uec.reject_evidence_mutation();

CREATE TRIGGER validation_findings_append_only
    BEFORE UPDATE OR DELETE ON uec.validation_findings
    FOR EACH ROW EXECUTE FUNCTION uec.reject_evidence_mutation();

CREATE TRIGGER release_members_append_only
    BEFORE UPDATE OR DELETE ON uec.release_members
    FOR EACH ROW EXECUTE FUNCTION uec.reject_evidence_mutation();
