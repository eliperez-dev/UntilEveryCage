-- Time passing or administrative closure must not restore publication. Only an
-- explicit, append-only lifted case decision can do so.
ALTER TABLE uec.suppression_cases DROP CONSTRAINT IF EXISTS suppression_cases_status_check;
ALTER TABLE uec.suppression_cases ADD CONSTRAINT suppression_cases_status_check
    CHECK (status IN ('active', 'review', 'closed', 'expired', 'lifted'));

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
WHERE case_record.status IN ('active', 'review', 'closed', 'expired');
