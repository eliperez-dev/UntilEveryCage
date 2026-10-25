-- Add the BLtU private Geoapify profile without changing existing profiles or
-- the shared result handler. The existing source-scoped handler rechecks the
-- latest snapshot, country, restrictions, confidence, and exact address.
DO $migration$
BEGIN
    IF to_regnamespace('real_preview') IS NULL
       OR to_regclass('real_preview.private_geocoding_source_profiles') IS NULL THEN
        RETURN;
    END IF;

    ALTER TABLE real_preview.private_geocoding_source_profiles
        DROP CONSTRAINT IF EXISTS private_geocoding_source_profiles_country_code_check;
    ALTER TABLE real_preview.private_geocoding_source_profiles
        ADD CONSTRAINT private_geocoding_source_profiles_country_code_check
        CHECK (country_code IN ('GB','DK','NL','US','ES','DE'));

    INSERT INTO real_preview.private_geocoding_source_profiles
        (profile_id, source_id, country_code, enabled, source_scope)
    VALUES
        ('geoapify-de-bltu', 'de.locations', 'DE', true,
         'Current-snapshot BLtU business street-address candidates with locality; street, locality, country only; no establishment names; private processing only')
    ON CONFLICT (profile_id) DO UPDATE SET
        source_id=EXCLUDED.source_id,
        country_code=EXCLUDED.country_code,
        source_scope=EXCLUDED.source_scope,
        enabled=true;
END
$migration$;
