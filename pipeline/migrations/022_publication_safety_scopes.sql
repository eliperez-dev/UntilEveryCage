-- Freeze publication decisions to the release present when they are recorded.
-- Earlier source-only decisions are carried forward only when their source
-- record belongs to exactly one release; ambiguous history needs new review.
ALTER TABLE uec.publication_review_events
    ADD COLUMN release_id TEXT REFERENCES uec.releases(release_id);

CREATE TABLE uec.publication_review_release_scopes (
    publication_review_event_id UUID NOT NULL REFERENCES uec.publication_review_events(publication_review_event_id),
    release_id TEXT NOT NULL REFERENCES uec.releases(release_id),
    PRIMARY KEY (publication_review_event_id, release_id)
);

INSERT INTO uec.publication_review_release_scopes (publication_review_event_id, release_id)
SELECT review.publication_review_event_id, min(member.release_id)
FROM uec.publication_review_events review
JOIN uec.observations observation ON observation.source_record_id = review.source_record_id
JOIN uec.release_members member ON member.observation_id = observation.observation_id
GROUP BY review.publication_review_event_id
HAVING count(DISTINCT member.release_id) = 1;

CREATE FUNCTION uec.scope_publication_review_event()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    inferred_release_id TEXT;
    release_count INTEGER;
BEGIN
    IF NEW.release_id IS NOT NULL THEN
        INSERT INTO uec.publication_review_release_scopes (publication_review_event_id, release_id)
        VALUES (NEW.publication_review_event_id, NEW.release_id);
        RETURN NEW;
    END IF;

    SELECT min(member.release_id), count(DISTINCT member.release_id)
    INTO inferred_release_id, release_count
    FROM uec.observations observation
    JOIN uec.release_members member ON member.observation_id = observation.observation_id
    WHERE observation.source_record_id = NEW.source_record_id;

    IF release_count > 1 AND NEW.publication_eligible THEN
        RAISE EXCEPTION 'publication decision for source record in multiple releases requires release_id';
    END IF;
    IF release_count = 1 THEN
        INSERT INTO uec.publication_review_release_scopes (publication_review_event_id, release_id)
        VALUES (NEW.publication_review_event_id, inferred_release_id);
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER publication_review_events_scope
    AFTER INSERT ON uec.publication_review_events
    FOR EACH ROW EXECUTE FUNCTION uec.scope_publication_review_event();

CREATE TRIGGER publication_review_release_scopes_append_only
    BEFORE UPDATE OR DELETE ON uec.publication_review_release_scopes
    FOR EACH ROW EXECUTE FUNCTION uec.reject_evidence_mutation();

CREATE OR REPLACE VIEW uec.publication_review_current AS
SELECT DISTINCT ON (review.source_record_id) review.source_record_id, review.factual_review_status,
       review.privacy_screening_status, review.maintainer_approval, review.publication_eligible,
       review.reviewer_role, review.reviewed_at, review.publication_review_event_id
FROM uec.publication_review_events review
LEFT JOIN uec.publication_review_release_scopes scope
  ON scope.publication_review_event_id = review.publication_review_event_id
LEFT JOIN uec.releases release ON release.release_id = scope.release_id
-- The existing API joins this source-keyed view without a release key. Prefer
-- a promoted release's decision so a candidate-only review does not relabel
-- or withdraw its still-promoted counterpart.
ORDER BY review.source_record_id,
         CASE WHEN release.status = 'promoted' THEN 0 ELSE 1 END,
         review.reviewed_at DESC, review.publication_review_event_id DESC;

CREATE VIEW uec.publication_review_release_current AS
SELECT DISTINCT ON (review.source_record_id, scope.release_id)
       review.source_record_id, scope.release_id, review.factual_review_status,
       review.privacy_screening_status, review.maintainer_approval,
       review.publication_eligible, review.reviewer_role, review.reviewed_at,
       review.publication_review_event_id
FROM uec.publication_review_events review
JOIN uec.publication_review_release_scopes scope
  ON scope.publication_review_event_id = review.publication_review_event_id
ORDER BY review.source_record_id, scope.release_id,
         review.reviewed_at DESC, review.publication_review_event_id DESC;

-- A facility reference must also reach an observation that has no separate
-- facility_source_links row. Restriction remains active for old releases.
CREATE OR REPLACE VIEW uec.public_access_restricted AS
SELECT source_record_id, reason_category, policy_version, occurred_at
FROM uec.record_access_current
WHERE action = 'public_access_revoked'
UNION
SELECT record.source_record_id, case_record.reason_category, case_record.policy_version, case_record.created_at
FROM uec.suppression_cases case_record
JOIN uec.suppression_references ref ON ref.case_id = case_record.case_id
JOIN uec.source_records record ON (
    ref.facility_id IS NOT NULL AND (
        EXISTS (SELECT 1 FROM uec.facility_source_links link
                WHERE link.facility_id = ref.facility_id AND link.source_record_id = record.source_record_id)
        OR EXISTS (SELECT 1 FROM uec.observations observation
                   WHERE observation.facility_id = ref.facility_id AND observation.source_record_id = record.source_record_id)
    )
    OR (ref.source_id = record.source_id AND ref.source_record_key = record.source_record_key)
)
WHERE case_record.status IN ('active', 'review', 'closed', 'expired');

-- A public count is about eligible observations in this release, not every
-- retained research observation attached to the facility.
CREATE VIEW uec.publication_release_eligible_observations AS
SELECT member.release_id, member.facility_id, observation.observation_id,
       observation.source_record_id, observation.first_observed_at, observation.observed_at
FROM uec.release_members member
JOIN uec.releases release ON release.release_id = member.release_id
JOIN uec.observations observation ON observation.observation_id = member.observation_id
JOIN uec.source_records record ON record.source_record_id = observation.source_record_id
JOIN uec.sources source ON source.source_id = record.source_id
JOIN uec.publication_review_release_current review
  ON review.source_record_id = observation.source_record_id
 AND review.release_id = member.release_id
WHERE release.status = 'promoted'
  AND member.default_visible = true
  AND review.publication_eligible = true
  AND review.privacy_screening_status = 'passed'
  AND review.factual_review_status <> 'rejected'
  AND (
      review.maintainer_approval = 'approved'
      OR (release.profile = 'community' AND source.origin_type = 'user_submitted'
          AND review.factual_review_status = 'unreviewed'
          AND review.maintainer_approval = 'pending')
  )
  AND NOT EXISTS (SELECT 1 FROM uec.public_access_restricted restricted
                  WHERE restricted.source_record_id = observation.source_record_id);

CREATE VIEW uec.public_facility_observation_summary AS
SELECT release_id, facility_id, min(first_observed_at) AS first_observed_at,
       max(observed_at) AS last_observed_at, count(*)::int AS observation_count
FROM uec.publication_release_eligible_observations
GROUP BY release_id, facility_id;

DROP VIEW uec.map_facilities_display_history;
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
JOIN uec.publication_release_eligible_observations eligible
  ON eligible.release_id = display.release_id AND eligible.observation_id = display.observation_id
JOIN uec.observations AS observation ON observation.observation_id = display.observation_id
JOIN uec.source_records AS record ON record.source_record_id = display.source_record_id
JOIN uec.sources AS source ON source.source_id = record.source_id
JOIN uec.release_members AS member ON member.release_id = display.release_id AND member.observation_id = display.observation_id
JOIN uec.releases AS release ON release.release_id = member.release_id
JOIN uec.raw_artifacts AS artifact ON artifact.artifact_id = record.artifact_id
JOIN uec.public_facility_observation_summary AS summary
  ON summary.release_id = display.release_id AND summary.facility_id = display.facility_id
LEFT JOIN uec.facility_lifecycle_current AS lifecycle ON lifecycle.facility_id = display.facility_id;

COMMENT ON VIEW uec.map_facilities_display_history IS
    'V2 public display history with current suppression, release-scoped publication decisions, and public-only lifecycle counts.';
