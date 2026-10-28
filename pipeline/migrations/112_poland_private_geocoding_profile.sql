-- GIW address enrichment is private and remains separate from release approval.
ALTER TABLE real_preview.private_geocoding_source_profiles
    DROP CONSTRAINT IF EXISTS private_geocoding_source_profiles_country_code_check;
ALTER TABLE real_preview.private_geocoding_source_profiles
    ADD CONSTRAINT private_geocoding_source_profiles_country_code_check
    CHECK (country_code IN ('GB','DK','NL','US','ES','DE','NZ','PL'));

INSERT INTO real_preview.private_geocoding_source_profiles
    (profile_id,source_id,country_code,enabled,source_scope,provider_id)
VALUES ('geoapify-pl-giw-approved-food','pl.giw.approved-food','PL',true,
        'GIW business-site address evidence only; no names/contacts sent; WNI grouping; private display with source-address match and Polish bounds',
        'geoapify')
ON CONFLICT (profile_id) DO NOTHING;

-- Keep the verified generic matching logic. Add a Poland-only geographic guard
-- before display evidence is stored, without modifying any other country.
CREATE FUNCTION real_preview.guard_poland_geocode_display()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    candidate_source TEXT;
    candidate_country TEXT;
BEGIN
    SELECT source_id,country_code INTO candidate_source,candidate_country
      FROM real_preview.candidates WHERE candidate_id=NEW.candidate_id;
    IF candidate_source <> 'pl.giw.approved-food' THEN RETURN NEW; END IF;
    IF candidate_country <> 'PL' OR NOT (
        NEW.display_longitude BETWEEN 13.8 AND 24.3 AND
        NEW.display_latitude BETWEEN 48.8 AND 55.2
    ) THEN RETURN NULL; END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER guard_poland_geocode_display
    BEFORE INSERT ON real_preview.geocode_display_evidence
    FOR EACH ROW EXECUTE FUNCTION real_preview.guard_poland_geocode_display();
