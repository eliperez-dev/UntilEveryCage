ALTER TABLE uec.releases
    ADD COLUMN IF NOT EXISTS test_only BOOLEAN NOT NULL DEFAULT false;

COMMENT ON COLUMN uec.releases.test_only IS
    'True only for disposable development/test releases; never eligible for public V2 selection.';

CREATE OR REPLACE FUNCTION uec.reject_test_only_release_transition()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.test_only AND NEW.status <> 'candidate' THEN
        RAISE EXCEPTION 'test-only releases cannot leave candidate state';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS releases_test_only_transition ON uec.releases;
CREATE TRIGGER releases_test_only_transition
    BEFORE INSERT OR UPDATE OF status, test_only ON uec.releases
    FOR EACH ROW EXECUTE FUNCTION uec.reject_test_only_release_transition();
