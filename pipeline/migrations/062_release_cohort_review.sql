-- One immutable operator-authored review document binds one whole candidate
-- cohort. The source/artifact scope rows are compact and never copy source facts.
CREATE TABLE uec.release_cohort_review_documents (
    release_id TEXT PRIMARY KEY REFERENCES uec.releases(release_id),
    profile TEXT NOT NULL CHECK (profile IN ('official','secondary','community')),
    ruleset_version TEXT NOT NULL CHECK (btrim(ruleset_version) <> ''),
    freeze_sha256 CHAR(64) NOT NULL CHECK (freeze_sha256 ~ '^[0-9a-f]{64}$'),
    inventory_sha256 CHAR(64) NOT NULL CHECK (inventory_sha256 ~ '^[0-9a-f]{64}$'),
    member_sha256 CHAR(64) NOT NULL CHECK (member_sha256 ~ '^[0-9a-f]{64}$'),
    member_count BIGINT NOT NULL CHECK (member_count > 0),
    document_sha256 CHAR(64) NOT NULL CHECK (document_sha256 ~ '^[0-9a-f]{64}$'),
    reviewer_actor TEXT NOT NULL CHECK (btrim(reviewer_actor) <> ''),
    reviewer_role TEXT NOT NULL CHECK (btrim(reviewer_role) <> ''),
    reviewed_at TIMESTAMPTZ NOT NULL,
    review_method TEXT NOT NULL CHECK (btrim(review_method) <> ''),
    review_evidence_reference TEXT NOT NULL CHECK (btrim(review_evidence_reference) <> ''),
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE uec.release_cohort_review_scopes (
    release_id TEXT NOT NULL REFERENCES uec.release_cohort_review_documents(release_id),
    source_id TEXT NOT NULL REFERENCES uec.sources(source_id),
    artifact_id UUID NOT NULL REFERENCES uec.raw_artifacts(artifact_id),
    artifact_sha256 CHAR(64) NOT NULL CHECK (artifact_sha256 ~ '^[0-9a-f]{64}$'),
    factual_review_status TEXT NOT NULL CHECK (factual_review_status IN ('unreviewed','reviewed','rejected')),
    privacy_screening_status TEXT NOT NULL CHECK (privacy_screening_status IN ('pending','passed','failed')),
    privacy_method TEXT NOT NULL CHECK (btrim(privacy_method) <> ''),
    privacy_evidence_reference TEXT NOT NULL CHECK (btrim(privacy_evidence_reference) <> ''),
    maintainer_approval TEXT NOT NULL CHECK (maintainer_approval IN ('pending','approved','denied')),
    publication_eligible BOOLEAN NOT NULL,
    project_approval_method TEXT NOT NULL CHECK (btrim(project_approval_method) <> ''),
    project_approval_evidence_reference TEXT NOT NULL CHECK (btrim(project_approval_evidence_reference) <> ''),
    redistribution_status TEXT NOT NULL CHECK (redistribution_status IN ('cleared','unknown','restricted')),
    rights_actor TEXT NOT NULL CHECK (btrim(rights_actor) <> ''),
    rights_reference TEXT NOT NULL CHECK (btrim(rights_reference) <> ''),
    rights_decided_at TIMESTAMPTZ NOT NULL,
    classification_interpretation_status TEXT NOT NULL CHECK (classification_interpretation_status IN ('approved','unreviewed','rejected')),
    classification_method TEXT NOT NULL CHECK (btrim(classification_method) <> ''),
    classification_evidence_reference TEXT NOT NULL CHECK (btrim(classification_evidence_reference) <> ''),
    geometry_interpretation_status TEXT NOT NULL CHECK (geometry_interpretation_status IN ('approved','unreviewed','rejected')),
    geometry_method TEXT NOT NULL CHECK (btrim(geometry_method) <> ''),
    geometry_evidence_reference TEXT NOT NULL CHECK (btrim(geometry_evidence_reference) <> ''),
    taxonomy_version TEXT NOT NULL CHECK (taxonomy_version = 'uec-taxonomy-v1'),
    crosswalk_version TEXT NOT NULL CHECK (btrim(crosswalk_version) <> ''),
    classification_ruleset_version TEXT NOT NULL CHECK (btrim(classification_ruleset_version) <> ''),
    excluded_display_categories JSONB NOT NULL DEFAULT '[]'::jsonb
        CHECK (jsonb_typeof(excluded_display_categories) = 'array'),
    exclusion_reason_category TEXT,
    exclusion_policy_reference TEXT,
    PRIMARY KEY (release_id, source_id, artifact_id),
    CHECK (jsonb_array_length(excluded_display_categories) = 0 OR
           (btrim(COALESCE(exclusion_reason_category,'')) <> '' AND btrim(COALESCE(exclusion_policy_reference,'')) <> ''))
);

CREATE INDEX release_cohort_review_scope_geometry_idx
    ON uec.release_cohort_review_scopes (release_id, source_id, artifact_id)
    WHERE geometry_interpretation_status = 'approved';

CREATE FUNCTION uec.validate_release_cohort_review_document()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    release_status TEXT;
    release_profile TEXT;
    release_test_only BOOLEAN;
    release_ruleset TEXT;
    release_summary JSONB;
BEGIN
    SELECT status, profile, test_only, ruleset_version, summary
      INTO release_status, release_profile, release_test_only, release_ruleset, release_summary
      FROM uec.releases WHERE release_id = NEW.release_id FOR UPDATE;
    IF release_status IS DISTINCT FROM 'candidate' OR release_test_only IS DISTINCT FROM false THEN
        RAISE EXCEPTION 'cohort review requires a non-test candidate release';
    END IF;
    IF release_profile IS DISTINCT FROM NEW.profile OR release_ruleset IS DISTINCT FROM NEW.ruleset_version THEN
        RAISE EXCEPTION 'cohort review profile or ruleset does not match release';
    END IF;
    IF release_summary->>'candidate_only' IS DISTINCT FROM 'true'
       OR release_summary->>'freeze_sha256' IS DISTINCT FROM NEW.freeze_sha256
       OR release_summary->>'inventory_sha256' IS DISTINCT FROM NEW.inventory_sha256 THEN
        RAISE EXCEPTION 'cohort review freeze or inventory does not match candidate control summary';
    END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER release_cohort_review_document_guard
    BEFORE INSERT ON uec.release_cohort_review_documents
    FOR EACH ROW EXECUTE FUNCTION uec.validate_release_cohort_review_document();

CREATE FUNCTION uec.validate_release_cohort_review_scope()
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
    IF NOT EXISTS (
        SELECT 1 FROM uec.taxonomy_crosswalks crosswalk
        WHERE crosswalk.source_id=NEW.source_id AND crosswalk.taxonomy_version=NEW.taxonomy_version
          AND crosswalk.crosswalk_version=NEW.crosswalk_version
          AND crosswalk.ruleset_version=NEW.classification_ruleset_version
    ) THEN RAISE EXCEPTION 'review scope taxonomy crosswalk is not registered'; END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER release_cohort_review_scope_guard
    BEFORE INSERT ON uec.release_cohort_review_scopes
    FOR EACH ROW EXECUTE FUNCTION uec.validate_release_cohort_review_scope();

CREATE TRIGGER release_cohort_review_documents_append_only
    BEFORE UPDATE OR DELETE ON uec.release_cohort_review_documents
    FOR EACH ROW EXECUTE FUNCTION uec.reject_evidence_mutation();
CREATE TRIGGER release_cohort_review_scopes_append_only
    BEFORE UPDATE OR DELETE ON uec.release_cohort_review_scopes
    FOR EACH ROW EXECUTE FUNCTION uec.reject_evidence_mutation();

CREATE VIEW uec.release_cohort_review_current AS
SELECT scope.*, review.profile, review.ruleset_version,
       review.freeze_sha256, review.inventory_sha256,
       review.member_sha256, review.member_count, review.document_sha256,
       review.reviewer_actor, review.reviewer_role, review.reviewed_at
FROM uec.release_cohort_review_scopes scope
JOIN uec.release_cohort_review_documents review USING (release_id);

-- A reviewed membership is frozen. Only the workflow may change visibility;
-- all identity and interpretation fields remain immutable.
CREATE FUNCTION uec.guard_release_member_cohort_review()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF EXISTS (SELECT 1 FROM uec.release_cohort_review_documents WHERE release_id=NEW.release_id) THEN
            RAISE EXCEPTION 'release membership cannot grow after cohort review';
        END IF;
        RETURN NEW;
    END IF;
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'release membership cannot be deleted';
    END IF;
    IF (to_jsonb(NEW) - 'default_visible') IS DISTINCT FROM (to_jsonb(OLD) - 'default_visible') THEN
        RAISE EXCEPTION 'cohort review may change only release member visibility';
    END IF;
    IF NEW.default_visible IS DISTINCT FROM OLD.default_visible
       AND NOT EXISTS (SELECT 1 FROM uec.release_cohort_review_documents WHERE release_id=NEW.release_id) THEN
        RAISE EXCEPTION 'visibility change requires an exact cohort review';
    END IF;
    RETURN NEW;
END $$;

DROP TRIGGER release_members_append_only ON uec.release_members;
CREATE TRIGGER release_members_cohort_guard
    BEFORE INSERT OR UPDATE OR DELETE ON uec.release_members
    FOR EACH ROW EXECUTE FUNCTION uec.guard_release_member_cohort_review();

COMMENT ON TABLE uec.release_cohort_review_documents IS
    'Immutable whole-cohort operator review bound to candidate freeze, inventory and deterministic member/taxonomy digest; not proof that checks occurred.';
COMMENT ON TABLE uec.release_cohort_review_scopes IS
    'Append-only source/artifact decisions for factual review, privacy eligibility, project approval, rights, and approved derived interpretation.';
