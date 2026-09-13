-- Durable, payload-free suppression references survive source reimports.
CREATE TABLE IF NOT EXISTS uec.suppression_cases (
    case_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    reason_category TEXT NOT NULL CHECK (reason_category IN ('privacy', 'safety', 'legal', 'other')),
    status TEXT NOT NULL CHECK (status IN ('active', 'review', 'closed', 'expired')),
    policy_version TEXT NOT NULL,
    actor TEXT NOT NULL,
    decision TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    review_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    note TEXT
);

CREATE TABLE IF NOT EXISTS uec.suppression_references (
    reference_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id UUID NOT NULL REFERENCES uec.suppression_cases(case_id),
    facility_id UUID REFERENCES uec.facilities(facility_id),
    source_id TEXT REFERENCES uec.sources(source_id),
    source_record_key TEXT,
    scope TEXT NOT NULL CHECK (scope IN ('address', 'coordinates', 'whole_record')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (facility_id IS NOT NULL OR (source_id IS NOT NULL AND source_record_key IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS suppression_references_facility_idx ON uec.suppression_references (facility_id);
CREATE INDEX IF NOT EXISTS suppression_references_source_key_idx ON uec.suppression_references (source_id, source_record_key);
CREATE INDEX IF NOT EXISTS suppression_cases_active_idx ON uec.suppression_cases (status, expires_at);

CREATE TRIGGER suppression_cases_append_only
    BEFORE UPDATE OR DELETE ON uec.suppression_cases
    FOR EACH ROW EXECUTE FUNCTION uec.reject_evidence_mutation();
CREATE TRIGGER suppression_references_append_only
    BEFORE UPDATE OR DELETE ON uec.suppression_references
    FOR EACH ROW EXECUTE FUNCTION uec.reject_evidence_mutation();

-- Public projections treat active/review suppression as revoked. Closed/expired
-- references remain auditable but do not automatically restore publication.
CREATE OR REPLACE VIEW uec.public_access_restricted AS
SELECT source_record_id, reason_category, policy_version, occurred_at
FROM uec.record_access_current
WHERE action = 'public_access_revoked'
UNION
SELECT record.source_record_id, case_record.reason_category, case_record.policy_version, case_record.created_at
FROM uec.suppression_cases case_record
JOIN uec.suppression_references ref ON ref.case_id = case_record.case_id
JOIN uec.source_records record ON (
    ref.facility_id IS NOT NULL AND EXISTS (
        SELECT 1 FROM uec.facility_source_links link
        WHERE link.facility_id = ref.facility_id AND link.source_record_id = record.source_record_id
    )
    OR (ref.source_id = record.source_id AND ref.source_record_key = record.source_record_key)
)
WHERE case_record.status IN ('active', 'review')
  AND (case_record.expires_at IS NULL OR case_record.expires_at > now());
