-- Append-only, private evidence for AESAN registration-number lookups that
-- verified a municipality. Original candidate address evidence is unchanged.
DO $migration$
BEGIN
    IF to_regnamespace('real_preview') IS NULL
       OR to_regclass('real_preview.candidates') IS NULL
       OR to_regprocedure('real_preview.reject_mutation()') IS NULL THEN
        RETURN;
    END IF;

    CREATE TABLE IF NOT EXISTS real_preview.spain_verified_locality_evidence (
        evidence_event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        event_sha256 CHAR(64) NOT NULL UNIQUE
            CHECK (event_sha256 ~ '^[0-9a-f]{64}$'),
        source_id TEXT NOT NULL CHECK (source_id = 'es.locations'),
        candidate_id UUID NOT NULL,
        snapshot_sha256 CHAR(64) NOT NULL,
        lookup_hash CHAR(64) NOT NULL CHECK (lookup_hash ~ '^[0-9a-f]{64}$'),
        source_record_key_hash CHAR(64) NOT NULL
            CHECK (source_record_key_hash ~ '^[0-9a-f]{64}$'),
        lookup_source_id TEXT NOT NULL
            CHECK (lookup_source_id = 'es.locations.aesan-rgseaa-public-finder'),
        lookup_method_version TEXT NOT NULL,
        lookup_url TEXT NOT NULL
            CHECK (lookup_url LIKE 'https://rgsa-web-aesan.mscbs.es/rgsa/%'),
        lookup_request_url TEXT NOT NULL
            CHECK (lookup_request_url LIKE 'https://rgsa-web-aesan.mscbs.es/rgsa/%'),
        retrieved_at TIMESTAMPTZ NOT NULL,
        municipality TEXT NOT NULL CHECK (length(btrim(municipality)) BETWEEN 1 AND 160),
        province TEXT NOT NULL CHECK (length(btrim(province)) BETWEEN 1 AND 120),
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        FOREIGN KEY (snapshot_sha256, source_id, candidate_id)
            REFERENCES real_preview.candidates(snapshot_sha256, source_id, candidate_id),
        CHECK (lookup_method_version = 'es-aesan-rgseaa-locality-v1')
    );

    CREATE INDEX IF NOT EXISTS spain_verified_locality_evidence_candidate_latest_idx
        ON real_preview.spain_verified_locality_evidence
           (candidate_id, retrieved_at DESC, evidence_event_id DESC);

    DROP TRIGGER IF EXISTS spain_verified_locality_evidence_immutable
        ON real_preview.spain_verified_locality_evidence;
    CREATE TRIGGER spain_verified_locality_evidence_immutable
        BEFORE UPDATE OR DELETE ON real_preview.spain_verified_locality_evidence
        FOR EACH ROW EXECUTE FUNCTION real_preview.reject_mutation();

    COMMENT ON TABLE real_preview.spain_verified_locality_evidence IS
        'Private append-only AESAN registration-key lookup evidence; municipality context only, not a source-address rewrite or publication authorization.';
END
$migration$;
