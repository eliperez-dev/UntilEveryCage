-- Synthetic control-plane fixture kept outside the older database dump.
-- Replay only into this drill's disposable project, before any public service.
INSERT INTO uec.suppression_cases (case_id,status,reason_category,policy_version,actor,decision)
VALUES ('00000000-0000-0000-0000-000000000003','active','privacy','ethics-v1','fixture','suppress');
INSERT INTO uec.suppression_references (case_id,source_id,source_record_key,scope)
VALUES ('00000000-0000-0000-0000-000000000003','e2e.backup','restricted','whole_record');
