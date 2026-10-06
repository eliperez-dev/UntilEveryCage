-- A cohort approval can append many publication events in one statement.
-- Bump the shared cache token once per statement while preserving its exact
-- per-event delta, avoiding one singleton-row update per inserted event.
DROP TRIGGER publication_review_generation ON uec.publication_review_events;

CREATE OR REPLACE FUNCTION uec.bump_publication_review_generation_statement()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    inserted_count BIGINT;
BEGIN
    SELECT count(*) INTO inserted_count FROM inserted_publication_reviews;
    UPDATE uec.public_suppression_generation
       SET generation = generation + inserted_count
     WHERE singleton = true AND inserted_count > 0;
    RETURN NULL;
END;
$$;

CREATE TRIGGER publication_review_generation
    AFTER INSERT ON uec.publication_review_events
    REFERENCING NEW TABLE AS inserted_publication_reviews
    FOR EACH STATEMENT
    EXECUTE FUNCTION uec.bump_publication_review_generation_statement();
