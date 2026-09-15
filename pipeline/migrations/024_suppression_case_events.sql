-- Append-only suppression decisions. A case row is immutable, so an explicit
-- lift is represented as a new event rather than mutating the original case.
CREATE TABLE IF NOT EXISTS uec.suppression_case_events (
    suppression_case_event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id UUID NOT NULL REFERENCES uec.suppression_cases(case_id),
    event_type TEXT NOT NULL CHECK (event_type IN ('suppressed', 'lifted')),
    reason_category TEXT NOT NULL CHECK (reason_category IN ('privacy', 'safety', 'legal', 'other')),
    policy_version TEXT NOT NULL,
    actor TEXT NOT NULL,
    decision TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    note TEXT
);

CREATE INDEX IF NOT EXISTS suppression_case_events_current_idx
    ON uec.suppression_case_events (case_id, occurred_at DESC, suppression_case_event_id DESC);

CREATE TRIGGER suppression_case_events_append_only
    BEFORE UPDATE OR DELETE ON uec.suppression_case_events
    FOR EACH ROW EXECUTE FUNCTION uec.reject_evidence_mutation();

-- Access revocations/restorations are also retained as append-only decisions;
-- current access is derived from their latest event.
DROP TRIGGER IF EXISTS record_access_events_append_only ON uec.record_access_events;
CREATE TRIGGER record_access_events_append_only
    BEFORE UPDATE OR DELETE ON uec.record_access_events
    FOR EACH ROW EXECUTE FUNCTION uec.reject_evidence_mutation();

-- Existing cases receive a non-sensitive initial event. New cases are covered
-- by the trigger below, so direct SQL and the operator command share the same
-- lifecycle semantics.
INSERT INTO uec.suppression_case_events
    (case_id, event_type, reason_category, policy_version, actor, decision, occurred_at)
SELECT case_id, 'suppressed', reason_category, policy_version, actor, decision, created_at
FROM uec.suppression_cases case_record
WHERE NOT EXISTS (
    SELECT 1 FROM uec.suppression_case_events event
    WHERE event.case_id = case_record.case_id
);

CREATE OR REPLACE FUNCTION uec.record_initial_suppression_case_event()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO uec.suppression_case_events
        (case_id, event_type, reason_category, policy_version, actor, decision, occurred_at)
    VALUES (NEW.case_id, 'suppressed', NEW.reason_category, NEW.policy_version,
            NEW.actor, NEW.decision, NEW.created_at);
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS suppression_cases_initial_event ON uec.suppression_cases;
CREATE TRIGGER suppression_cases_initial_event
    AFTER INSERT ON uec.suppression_cases
    FOR EACH ROW EXECUTE FUNCTION uec.record_initial_suppression_case_event();

CREATE OR REPLACE VIEW uec.suppression_case_current AS
SELECT DISTINCT ON (case_id)
       case_id, event_type, reason_category, policy_version, actor,
       decision, occurred_at
FROM uec.suppression_case_events
ORDER BY case_id, occurred_at DESC, suppression_case_event_id DESC;

-- A lift is effective only through this explicit event. Closure, expiry, or
-- time passing remains restrictive until a documented lift is recorded.
CREATE OR REPLACE VIEW uec.public_access_restricted AS
SELECT source_record_id, reason_category, policy_version, occurred_at
FROM uec.record_access_current
WHERE action = 'public_access_revoked'
UNION
SELECT record.source_record_id, current_case.reason_category,
       current_case.policy_version, current_case.occurred_at
FROM uec.suppression_case_current current_case
JOIN uec.suppression_cases case_record ON case_record.case_id = current_case.case_id
JOIN uec.suppression_references ref ON ref.case_id = case_record.case_id
JOIN uec.source_records record ON (
    ref.facility_id IS NOT NULL AND (
        EXISTS (SELECT 1 FROM uec.facility_source_links link
                WHERE link.facility_id = ref.facility_id
                  AND link.source_record_id = record.source_record_id)
        OR EXISTS (SELECT 1 FROM uec.observations observation
                   WHERE observation.facility_id = ref.facility_id
                     AND observation.source_record_id = record.source_record_id)
    )
    OR (ref.source_id = record.source_id AND ref.source_record_key = record.source_record_key)
)
WHERE current_case.event_type = 'suppressed'
  AND case_record.status IN ('active', 'review', 'closed', 'expired');

COMMENT ON VIEW uec.suppression_case_current IS
    'Current append-only suppression decision; only an explicit lifted event ends a case restriction.';
