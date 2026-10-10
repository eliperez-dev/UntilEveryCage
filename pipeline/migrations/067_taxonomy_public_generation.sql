-- Taxonomy is part of the public map projection.  Its append-only changes
-- must invalidate every process/browser cache just like a suppression or
-- review change.  Statement-level triggers deliberately bump once per import
-- statement rather than once per taxonomy row.
CREATE OR REPLACE FUNCTION uec.bump_taxonomy_public_generation_statement()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    changed_count BIGINT;
BEGIN
    SELECT count(*) INTO changed_count FROM new_taxonomy_rows;
    UPDATE uec.public_suppression_generation
       SET generation = generation + 1
     WHERE singleton = true AND changed_count > 0;
    RETURN NULL;
END;
$$;

CREATE TRIGGER observation_taxonomy_assignment_sets_public_generation
    AFTER INSERT ON uec.observation_taxonomy_assignment_sets
    REFERENCING NEW TABLE AS new_taxonomy_rows
    FOR EACH STATEMENT EXECUTE FUNCTION uec.bump_taxonomy_public_generation_statement();

CREATE TRIGGER observation_taxonomy_assignments_public_generation
    AFTER INSERT ON uec.observation_taxonomy_assignments
    REFERENCING NEW TABLE AS new_taxonomy_rows
    FOR EACH STATEMENT EXECUTE FUNCTION uec.bump_taxonomy_public_generation_statement();

COMMENT ON FUNCTION uec.bump_taxonomy_public_generation_statement IS
    'Statement-level invalidation for public projections whose category display derives from append-only taxonomy rows.';
