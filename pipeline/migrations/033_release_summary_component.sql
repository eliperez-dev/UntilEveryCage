-- Prototype only: immutable release-bound observation membership facts. This
-- is not a public surface by itself; candidate reads below keep current
-- review, profile, and suppression gates live.
CREATE TABLE uec.release_summary_components (
    release_id TEXT PRIMARY KEY REFERENCES uec.releases(release_id),
    manifest_sha256 CHAR(64) NOT NULL CHECK (manifest_sha256 ~ '^[0-9a-f]{64}$'),
    content_sha256 CHAR(64) NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
    member_count INTEGER NOT NULL CHECK (member_count >= 0),
    built_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE uec.release_summary_component_rows (
    release_id TEXT NOT NULL REFERENCES uec.releases(release_id),
    facility_id UUID NOT NULL REFERENCES uec.facilities(facility_id),
    observation_id UUID NOT NULL REFERENCES uec.observations(observation_id),
    source_record_id UUID NOT NULL REFERENCES uec.source_records(source_record_id),
    first_observed_at TIMESTAMPTZ NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    classification_category TEXT NOT NULL,
    PRIMARY KEY (release_id, facility_id, observation_id)
);

CREATE INDEX release_summary_component_rows_order_idx
    ON uec.release_summary_component_rows (release_id, facility_id, observation_id);

CREATE TRIGGER release_summary_components_append_only
    BEFORE UPDATE OR DELETE ON uec.release_summary_components
    FOR EACH ROW EXECUTE FUNCTION uec.reject_evidence_mutation();

CREATE TRIGGER release_summary_component_rows_append_only
    BEFORE UPDATE OR DELETE ON uec.release_summary_component_rows
    FOR EACH ROW EXECUTE FUNCTION uec.reject_evidence_mutation();

-- Candidate summary: the immutable rows reduce repeated release-member and
-- observation joins, but all current public eligibility remains live. The
-- manifest join prevents an older or mismatched component from serving as the
-- current release summary; missing metadata therefore fails closed to empty.
CREATE OR REPLACE VIEW uec.public_facility_observation_summary_component_candidate AS
SELECT component.release_id,
       component.facility_id,
       min(component.first_observed_at) AS first_observed_at,
       max(component.observed_at) AS last_observed_at,
       count(*)::int AS observation_count
FROM uec.release_summary_component_rows component
JOIN uec.release_summary_components component_meta
  ON component_meta.release_id = component.release_id
JOIN uec.releases release
  ON release.release_id = component.release_id
JOIN uec.release_manifests manifest
  ON manifest.release_id = component.release_id
 AND manifest.manifest_sha256 = component_meta.manifest_sha256
JOIN uec.source_records record
  ON record.source_record_id = component.source_record_id
JOIN uec.sources source
  ON source.source_id = record.source_id
JOIN uec.publication_review_release_current review
  ON review.source_record_id = component.source_record_id
 AND review.release_id = component.release_id
WHERE release.status = 'promoted'
  AND release.test_only IS NOT TRUE
  AND review.publication_eligible = true
  AND review.privacy_screening_status = 'passed'
  AND review.factual_review_status <> 'rejected'
  AND (review.maintainer_approval = 'approved'
       OR (release.profile = 'community'
           AND source.origin_type = 'user_submitted'
           AND review.factual_review_status = 'unreviewed'
           AND review.maintainer_approval = 'pending'))
  AND NOT EXISTS (
      SELECT 1
      FROM uec.public_access_restricted restricted
      WHERE restricted.source_record_id = component.source_record_id
  )
GROUP BY component.release_id, component.facility_id;

COMMENT ON VIEW uec.public_facility_observation_summary_component_candidate IS
    'Prototype only: manifest-bound immutable release rows aggregated through live review, profile, and suppression gates; not wired to the API.';
