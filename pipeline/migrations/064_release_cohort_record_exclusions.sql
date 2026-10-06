-- Store explicit record-level exceptions beside the immutable artifact scope.
-- Full release membership and its digest remain unchanged.
ALTER TABLE uec.release_cohort_review_scopes
    ADD COLUMN excluded_source_record_ids JSONB NOT NULL DEFAULT '[]'::jsonb
        CHECK (jsonb_typeof(excluded_source_record_ids) = 'array');

ALTER TABLE uec.release_cohort_review_scopes
    ADD CONSTRAINT release_cohort_review_scopes_record_exclusion_reason_check
        CHECK (jsonb_array_length(excluded_source_record_ids) = 0
               OR (btrim(COALESCE(exclusion_reason_category,'')) <> ''
                   AND btrim(COALESCE(exclusion_policy_reference,'')) <> ''));

-- Preserve every existing view column position and append the new field last.
CREATE OR REPLACE VIEW uec.release_cohort_review_current AS
SELECT scope.release_id, scope.source_id, scope.artifact_id, scope.artifact_sha256,
       scope.factual_review_status, scope.privacy_screening_status, scope.privacy_method,
       scope.privacy_evidence_reference, scope.maintainer_approval, scope.publication_eligible,
       scope.project_approval_method, scope.project_approval_evidence_reference,
       scope.redistribution_status, scope.rights_actor, scope.rights_reference,
       scope.rights_decided_at, scope.classification_interpretation_status,
       scope.classification_method, scope.classification_evidence_reference,
       scope.geometry_interpretation_status, scope.geometry_method,
       scope.geometry_evidence_reference, scope.taxonomy_version, scope.crosswalk_version,
       scope.classification_ruleset_version, scope.excluded_display_categories,
       scope.exclusion_reason_category, scope.exclusion_policy_reference,
       review.profile, review.ruleset_version, review.freeze_sha256, review.inventory_sha256,
       review.member_sha256, review.member_count, review.document_sha256,
       review.reviewer_actor, review.reviewer_role, review.reviewed_at,
       scope.excluded_source_record_ids
FROM uec.release_cohort_review_scopes scope
JOIN uec.release_cohort_review_documents review USING (release_id);

COMMENT ON COLUMN uec.release_cohort_review_scopes.excluded_source_record_ids IS
    'Canonical source_record UUIDs explicitly excluded within this immutable release/artifact review scope.';

CREATE OR REPLACE FUNCTION uec.validate_release_cohort_review_scope()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    artifact_digest CHAR(64);
    scope_profile TEXT;
BEGIN
    SELECT raw.sha256, release.profile INTO artifact_digest, scope_profile
      FROM uec.raw_artifacts raw
      JOIN uec.release_cohort_review_documents review ON review.release_id = NEW.release_id
      JOIN uec.releases release ON release.release_id = review.release_id
     WHERE raw.artifact_id = NEW.artifact_id;
    IF artifact_digest IS NULL OR artifact_digest IS DISTINCT FROM NEW.artifact_sha256 THEN
        RAISE EXCEPTION 'review scope artifact digest mismatch';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM uec.release_members member
        JOIN uec.observations observation ON observation.observation_id=member.observation_id
        JOIN uec.source_records record ON record.source_record_id=observation.source_record_id
        WHERE member.release_id=NEW.release_id AND record.source_id=NEW.source_id
          AND record.artifact_id=NEW.artifact_id
    ) THEN RAISE EXCEPTION 'review scope is outside candidate membership'; END IF;
    IF EXISTS (
        SELECT 1 FROM jsonb_array_elements_text(NEW.excluded_source_record_ids) excluded(source_record_id)
        WHERE excluded.source_record_id::uuid::text <> excluded.source_record_id
           OR NOT EXISTS (
               SELECT 1 FROM uec.release_members member
               JOIN uec.observations observation ON observation.observation_id=member.observation_id
               JOIN uec.source_records record ON record.source_record_id=observation.source_record_id
               WHERE member.release_id=NEW.release_id AND record.source_id=NEW.source_id
                 AND record.artifact_id=NEW.artifact_id
                 AND record.source_record_id=excluded.source_record_id::uuid
           )
    ) THEN RAISE EXCEPTION 'record exclusion is outside exact release source/artifact membership'; END IF;
    IF (SELECT count(*) FROM jsonb_array_elements_text(NEW.excluded_source_record_ids))
       <> (SELECT count(DISTINCT value) FROM jsonb_array_elements_text(NEW.excluded_source_record_ids))
    THEN RAISE EXCEPTION 'record exclusions must be unique'; END IF;
    IF NOT EXISTS (
        SELECT 1 FROM uec.taxonomy_crosswalks crosswalk
        WHERE crosswalk.source_id=NEW.source_id AND crosswalk.taxonomy_version=NEW.taxonomy_version
          AND crosswalk.crosswalk_version=NEW.crosswalk_version
          AND crosswalk.ruleset_version=NEW.classification_ruleset_version
    ) THEN RAISE EXCEPTION 'review scope taxonomy crosswalk is not registered'; END IF;
    RETURN NEW;
END $$;
