-- Release-scoped source redistribution decisions.
--
-- This is deliberately separate from acquisition metadata and from the
-- source.attribution presentation field.  A decision is attributable evidence
-- that an authorized owner/maintainer reviewed one immutable source artifact
-- for one canonical source/profile/release scope.  The actor string records
-- attribution; application authorization must be enforced by the operator
-- boundary and is not inferred from this value.
CREATE TABLE uec.source_rights_decisions (
    source_rights_decision_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id TEXT NOT NULL REFERENCES uec.sources(source_id),
    profile TEXT NOT NULL CHECK (profile IN ('official', 'secondary', 'community')),
    release_id TEXT NOT NULL REFERENCES uec.releases(release_id),
    artifact_id UUID NOT NULL REFERENCES uec.raw_artifacts(artifact_id),
    artifact_sha256 CHAR(64) NOT NULL CHECK (artifact_sha256 ~ '^[0-9a-f]{64}$'),
    redistribution_status TEXT NOT NULL CHECK (redistribution_status IN ('cleared', 'unknown', 'restricted')),
    decision_actor TEXT NOT NULL CHECK (btrim(decision_actor) <> ''),
    decision_reference TEXT NOT NULL CHECK (btrim(decision_reference) <> ''),
    decided_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX source_rights_decisions_scope_idx
    ON uec.source_rights_decisions
       (source_id, profile, release_id, artifact_id, decided_at DESC,
        source_rights_decision_id DESC);

CREATE FUNCTION uec.validate_source_rights_decision()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    release_profile TEXT;
    artifact_digest CHAR(64);
BEGIN
    SELECT profile INTO release_profile
    FROM uec.releases
    WHERE release_id = NEW.release_id;
    IF release_profile IS NULL THEN
        RAISE EXCEPTION 'rights decision release does not exist: %', NEW.release_id;
    END IF;
    IF release_profile IS DISTINCT FROM NEW.profile THEN
        RAISE EXCEPTION 'rights decision profile does not match release profile';
    END IF;

    SELECT sha256 INTO artifact_digest
    FROM uec.raw_artifacts
    WHERE artifact_id = NEW.artifact_id;
    IF artifact_digest IS NULL THEN
        RAISE EXCEPTION 'rights decision artifact does not exist: %', NEW.artifact_id;
    END IF;
    IF artifact_digest IS DISTINCT FROM NEW.artifact_sha256 THEN
        RAISE EXCEPTION 'rights decision artifact digest does not match immutable artifact';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER source_rights_decisions_scope_guard
    BEFORE INSERT ON uec.source_rights_decisions
    FOR EACH ROW EXECUTE FUNCTION uec.validate_source_rights_decision();

CREATE TRIGGER source_rights_decisions_append_only
    BEFORE UPDATE OR DELETE ON uec.source_rights_decisions
    FOR EACH ROW EXECUTE FUNCTION uec.reject_evidence_mutation();

COMMENT ON TABLE uec.source_rights_decisions IS
    'Append-only attributable redistribution decisions; acquisition permission, attribution, and operator authorization remain separate.';
COMMENT ON COLUMN uec.source_rights_decisions.artifact_sha256 IS
    'Immutable source-version digest. Every contributing artifact needs its own exact decision.';
COMMENT ON COLUMN uec.source_rights_decisions.decision_actor IS
    'Attributable actor reference only; trusted operator authorization is enforced outside this ledger.';
