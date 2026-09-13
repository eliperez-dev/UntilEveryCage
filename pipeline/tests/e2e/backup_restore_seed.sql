-- Synthetic-only fixture. No real source, address, or raw payload is permitted here.
INSERT INTO uec.sources (source_id,country_code,name,official_url,access_method)
VALUES ('e2e.backup','DK','Synthetic backup source','https://example.invalid/backup','fixture');
INSERT INTO uec.releases (release_id,status,ruleset_version,profile,summary)
VALUES ('e2e-promoted','promoted','synthetic-v1','official','{}');
INSERT INTO uec.raw_artifacts (artifact_id,storage_key,sha256,byte_size,retrieved_at)
VALUES ('00000000-0000-0000-0000-000000000001','e2e/backup/restricted',repeat('a',64),0,now());
INSERT INTO uec.source_records (source_record_id,source_id,source_record_key,artifact_id,raw_fields,parsed_at)
VALUES ('00000000-0000-0000-0000-000000000002','e2e.backup','restricted','00000000-0000-0000-0000-000000000001','{}',now());
INSERT INTO uec.suppression_cases (case_id,status,reason_category,policy_version,actor,decision)
VALUES ('00000000-0000-0000-0000-000000000003','active','privacy','ethics-v1','fixture','suppress');
INSERT INTO uec.suppression_references (case_id,source_id,source_record_key,scope)
VALUES ('00000000-0000-0000-0000-000000000003','e2e.backup','restricted','whole_record');
INSERT INTO uec.facilities (facility_id,canonical_name,country_code,city)
VALUES ('00000000-0000-0000-0000-000000000004','Synthetic restricted facility','DK','Backupby');
INSERT INTO uec.observations (observation_id,facility_id,source_record_id,observed_at,observation,classification,ruleset_id,rule_id,classification_category,classification_review_status,default_visible,first_observed_at)
VALUES ('00000000-0000-0000-0000-000000000005','00000000-0000-0000-0000-000000000004','00000000-0000-0000-0000-000000000002',now(),'{}','{}','synthetic-v1','fixture','slaughter','approved',true,now());
INSERT INTO uec.release_members (release_id,facility_id,observation_id,default_visible)
VALUES ('e2e-promoted','00000000-0000-0000-0000-000000000004','00000000-0000-0000-0000-000000000005',true);
INSERT INTO uec.publication_review_events (source_record_id,factual_review_status,privacy_screening_status,maintainer_approval,publication_eligible,reviewer_role)
VALUES ('00000000-0000-0000-0000-000000000002','reviewed','passed','approved',true,'maintainer');
