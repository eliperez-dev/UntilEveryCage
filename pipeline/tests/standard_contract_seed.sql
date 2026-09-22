-- Clean synthetic fixture for database contract tests. This is not a release
-- fixture: the candidate release lets tests promote/restrict records safely.
INSERT INTO uec.sources (source_id,country_code,name,official_url,access_method)
VALUES ('standard.contract','DK','Synthetic contract source','https://example.invalid/contract','fixture');
INSERT INTO uec.releases (release_id,status,ruleset_version,profile,summary)
VALUES ('standard-candidate','candidate','synthetic-test-v1','official','{}');
INSERT INTO uec.raw_artifacts (artifact_id,storage_key,sha256,byte_size,retrieved_at)
VALUES ('10000000-0000-0000-0000-000000000001','standard/contract',repeat('c',64),1,now());
INSERT INTO uec.source_rights_decisions (source_id,profile,release_id,artifact_id,artifact_sha256,redistribution_status,decision_actor,decision_reference,decided_at)
VALUES ('standard.contract','official','standard-candidate','10000000-0000-0000-0000-000000000001',repeat('c',64),'cleared','synthetic-fixture','standard-contract-fixture',now());
INSERT INTO uec.source_records (source_record_id,source_id,source_record_key,artifact_id,raw_fields,parsed_at)
VALUES ('10000000-0000-0000-0000-000000000002','standard.contract','contract','10000000-0000-0000-0000-000000000001','{}',now());
INSERT INTO uec.facilities (facility_id,canonical_name,country_code,city)
VALUES ('10000000-0000-0000-0000-000000000003','Synthetic contract facility','DK','Contractby');
INSERT INTO uec.observations (observation_id,facility_id,source_record_id,observed_at,observation,classification,ruleset_id,rule_id,classification_category,classification_review_status,default_visible,first_observed_at)
VALUES ('10000000-0000-0000-0000-000000000004','10000000-0000-0000-0000-000000000003','10000000-0000-0000-0000-000000000002',now(),'{}','{}','synthetic-test-v1','fixture','slaughter','approved',true,now());
INSERT INTO uec.release_members (release_id,facility_id,observation_id,default_visible)
VALUES ('standard-candidate','10000000-0000-0000-0000-000000000003','10000000-0000-0000-0000-000000000004',true);
INSERT INTO uec.geocode_results (source_record_id,provider_id,query,match_method,status,attempt_number,result,queried_at)
VALUES ('10000000-0000-0000-0000-000000000002','fixture','Contractby','city','accepted',1,ST_SetSRID(ST_MakePoint(10,55),4326)::geography,now());
INSERT INTO uec.publication_review_events (source_record_id,factual_review_status,privacy_screening_status,maintainer_approval,publication_eligible,reviewer_role)
VALUES ('10000000-0000-0000-0000-000000000002','reviewed','passed','approved',true,'maintainer');
INSERT INTO uec.raw_artifacts (artifact_id,storage_key,sha256,byte_size,retrieved_at)
VALUES ('10000000-0000-0000-0000-000000000005','standard/auxiliary',repeat('d',64),1,now());
INSERT INTO uec.source_records (source_record_id,source_id,source_record_key,artifact_id,raw_fields,parsed_at)
VALUES ('10000000-0000-0000-0000-000000000006','standard.contract','auxiliary','10000000-0000-0000-0000-000000000005','{}',now());
