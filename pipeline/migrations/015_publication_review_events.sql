-- Publication decisions are control-plane events; source evidence is untouched.
CREATE TABLE IF NOT EXISTS uec.publication_review_events (
    publication_review_event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_record_id UUID NOT NULL REFERENCES uec.source_records(source_record_id),
    factual_review_status TEXT NOT NULL CHECK (factual_review_status IN ('unreviewed', 'reviewed', 'rejected')),
    privacy_screening_status TEXT NOT NULL CHECK (privacy_screening_status IN ('pending', 'passed', 'failed')),
    maintainer_approval TEXT NOT NULL CHECK (maintainer_approval IN ('pending', 'approved', 'denied')),
    publication_eligible BOOLEAN NOT NULL DEFAULT false,
    reviewer_role TEXT,
    note TEXT,
    reviewed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS publication_review_events_current_lookup
    ON uec.publication_review_events (source_record_id, reviewed_at DESC, publication_review_event_id DESC);
CREATE TRIGGER publication_review_events_append_only
    BEFORE UPDATE OR DELETE ON uec.publication_review_events
    FOR EACH ROW EXECUTE FUNCTION uec.reject_evidence_mutation();
CREATE OR REPLACE VIEW uec.publication_review_current AS
SELECT DISTINCT ON (source_record_id) source_record_id, factual_review_status,
       privacy_screening_status, maintainer_approval, publication_eligible, reviewer_role, reviewed_at
FROM uec.publication_review_events
ORDER BY source_record_id, reviewed_at DESC, publication_review_event_id DESC;

DROP VIEW IF EXISTS uec.map_facilities_display_history;
CREATE VIEW uec.map_facilities_display_history AS
SELECT display.*, observation.classification_category,
       summary.first_observed_at, summary.last_observed_at, summary.observation_count,
       COALESCE(lifecycle.status, 'status_unknown') AS lifecycle_status,
       lifecycle.effective_at AS lifecycle_effective_at, lifecycle.source_record_id AS lifecycle_source_record_id,
       release.ruleset_version AS release_ruleset_version, release.created_at AS release_created_at,
       source.origin_type AS provenance_origin_type, source.source_id AS provenance_source_id,
       source.name AS provenance_source_name, source.official_url AS provenance_source_url,
       artifact.retrieved_at AS provenance_retrieved_at
FROM uec.map_facilities_display AS display
JOIN uec.observations AS observation ON observation.observation_id = display.observation_id
JOIN uec.source_records AS record ON record.source_record_id = display.source_record_id
JOIN uec.sources AS source ON source.source_id = record.source_id
JOIN uec.release_members AS member ON member.release_id = display.release_id AND member.observation_id = display.observation_id
JOIN uec.releases AS release ON release.release_id = member.release_id
JOIN uec.raw_artifacts AS artifact ON artifact.artifact_id = record.artifact_id
LEFT JOIN uec.facility_observation_summary AS summary ON summary.facility_id = display.facility_id
LEFT JOIN uec.facility_lifecycle_current AS lifecycle ON lifecycle.facility_id = display.facility_id
LEFT JOIN uec.publication_review_current AS review ON review.source_record_id = display.source_record_id
WHERE source.origin_type = 'official' OR review.publication_eligible = true;
