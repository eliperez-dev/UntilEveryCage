-- A monotonic generation token for caches of public release projections.
-- Every append-only event that can revoke, restore, or change publication
-- eligibility advances the token. Tile clients must compare it with the
-- current manifest response before rendering persisted bytes.
LOCK TABLE uec.record_access_events, uec.suppression_case_events,
           uec.publication_review_events, uec.source_rights_decisions,
           uec.geocode_results IN SHARE ROW EXCLUSIVE MODE;

CREATE TABLE uec.public_suppression_generation (
    singleton BOOLEAN PRIMARY KEY DEFAULT true CHECK (singleton),
    generation BIGINT NOT NULL CHECK (generation >= 0)
);

INSERT INTO uec.public_suppression_generation(singleton, generation)
SELECT true, (
    (SELECT count(*) FROM uec.record_access_events)
  + (SELECT count(*) FROM uec.suppression_case_events)
  + (SELECT count(*) FROM uec.publication_review_events)
  + (SELECT count(*) FROM uec.source_rights_decisions)
  + (SELECT count(*) FROM uec.geocode_results)
);

CREATE OR REPLACE FUNCTION uec.bump_public_suppression_generation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    UPDATE uec.public_suppression_generation
       SET generation = generation + 1
     WHERE singleton = true;
    RETURN NEW;
END;
$$;

CREATE TRIGGER record_access_generation
    AFTER INSERT ON uec.record_access_events
    FOR EACH ROW EXECUTE FUNCTION uec.bump_public_suppression_generation();
CREATE TRIGGER suppression_event_generation
    AFTER INSERT ON uec.suppression_case_events
    FOR EACH ROW EXECUTE FUNCTION uec.bump_public_suppression_generation();
CREATE TRIGGER publication_review_generation
    AFTER INSERT ON uec.publication_review_events
    FOR EACH ROW EXECUTE FUNCTION uec.bump_public_suppression_generation();
CREATE TRIGGER source_rights_generation
    AFTER INSERT ON uec.source_rights_decisions
    FOR EACH ROW EXECUTE FUNCTION uec.bump_public_suppression_generation();
CREATE TRIGGER geocode_generation
    AFTER INSERT OR UPDATE ON uec.geocode_results
    FOR EACH ROW EXECUTE FUNCTION uec.bump_public_suppression_generation();

COMMENT ON TABLE uec.public_suppression_generation IS
    'Monotonic invalidation generation for release caches; increments when access, suppression, publication review, source-rights, or geocoding decisions change.';
