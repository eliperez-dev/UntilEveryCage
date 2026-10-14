-- Add a narrowly scoped private APHIS mailing-locality Geoapify profile.
-- This grants neither an operating-site assertion nor publication eligibility.
ALTER TABLE real_preview.private_geocoding_source_profiles
    DROP CONSTRAINT IF EXISTS private_geocoding_source_profiles_country_code_check;
ALTER TABLE real_preview.private_geocoding_source_profiles
    ADD CONSTRAINT private_geocoding_source_profiles_country_code_check
    CHECK (country_code IN ('GB','DK','NL','US'));

INSERT INTO real_preview.private_geocoding_source_profiles
    (profile_id, source_id, country_code, enabled, source_scope)
VALUES
    ('geoapify-us-aphis-mailing-locality', 'us.aphis', 'US', true,
     'Active-register mailing city/state only; accepted city result is approximate mailing locality, never operating-site or facility coordinates')
ON CONFLICT (profile_id) DO UPDATE SET
    source_id=EXCLUDED.source_id,
    country_code=EXCLUDED.country_code,
    source_scope=EXCLUDED.source_scope,
    enabled=true;

COMMENT ON TABLE real_preview.private_geocoding_source_profiles IS
    'Explicit source/country allowlist for private Geoapify processing; APHIS US is mailing-locality-only and never establishes an operating site, project approval, or publication.';
