-- Synthetic-only fixture. No real source, address, or raw payload is permitted here.
INSERT INTO uec.sources (source_id,country_code,name,official_url,access_method)
VALUES ('e2e.backup','DK','Synthetic backup source','https://example.invalid/backup','fixture');
INSERT INTO uec.releases (release_id,status,ruleset_version,profile,summary)
VALUES ('e2e-promoted','promoted','synthetic-v1','official','{}');
INSERT INTO uec.release_manifests (release_id,manifest,manifest_sha256)
VALUES ('e2e-promoted','{"eligible_record_count":1,"manifest_version":"v1","profile":"official","release_id":"e2e-promoted","ruleset_version":"synthetic-v1","source_ids":["e2e.backup"]}', 'cabe8641a05beb76c9517006a8ec4cdd60b3bad58aa5b0fc29335fee1ac7d5dd');
INSERT INTO uec.raw_artifacts (artifact_id,storage_key,sha256,byte_size,retrieved_at)
VALUES ('00000000-0000-0000-0000-000000000001','e2e/backup/restricted',repeat('a',64),0,now());
INSERT INTO uec.source_records (source_record_id,source_id,source_record_key,artifact_id,raw_fields,parsed_at)
VALUES ('00000000-0000-0000-0000-000000000002','e2e.backup','restricted','00000000-0000-0000-0000-000000000001','{}',now());
INSERT INTO uec.facilities (facility_id,canonical_name,country_code,city)
VALUES ('00000000-0000-0000-0000-000000000004','Synthetic restricted facility','DK','Backupby');
INSERT INTO uec.observations (observation_id,facility_id,source_record_id,observed_at,observation,classification,ruleset_id,rule_id,classification_category,classification_review_status,default_visible,first_observed_at)
VALUES ('00000000-0000-0000-0000-000000000005','00000000-0000-0000-0000-000000000004','00000000-0000-0000-0000-000000000002',now(),'{}','{}','synthetic-v1','fixture','slaughter','approved',true,now());
INSERT INTO uec.release_members (release_id,facility_id,observation_id,default_visible)
VALUES ('e2e-promoted','00000000-0000-0000-0000-000000000004','00000000-0000-0000-0000-000000000005',true);
INSERT INTO uec.publication_review_events (source_record_id,factual_review_status,privacy_screening_status,maintainer_approval,publication_eligible,reviewer_role)
VALUES ('00000000-0000-0000-0000-000000000002','reviewed','passed','approved',true,'maintainer');
-- The read model is part of the backup and is still only a public projection.
-- Current suppression remains live after restore/replay.
INSERT INTO uec.public_discovery_read_models (release_id,manifest_sha256,content_sha256,row_count)
VALUES ('e2e-promoted','cabe8641a05beb76c9517006a8ec4cdd60b3bad58aa5b0fc29335fee1ac7d5dd',repeat('b',64),1);
INSERT INTO uec.public_discovery_read_model_rows
    (release_id,facility_id,observation_id,source_record_id,canonical_name,country_code,
     city,display_precision,display_label,classification_category,observed_at,
     first_observed_at,provenance_origin_type,provenance_source_id,provenance_source_name,
     provenance_source_url,provenance_retrieved_at,source_rights_status)
SELECT 'e2e-promoted', facility.facility_id, observation.observation_id,
       observation.source_record_id, facility.canonical_name, facility.country_code,
       facility.city, 'unmapped', 'No publishable location', observation.classification_category,
       observation.observed_at, observation.first_observed_at, source.origin_type,
       source.source_id, source.name, source.official_url, artifact.retrieved_at, 'unknown'
FROM uec.observations observation
JOIN uec.facilities facility ON facility.facility_id=observation.facility_id
JOIN uec.source_records record ON record.source_record_id=observation.source_record_id
JOIN uec.sources source ON source.source_id=record.source_id
JOIN uec.raw_artifacts artifact ON artifact.artifact_id=record.artifact_id
WHERE observation.observation_id='00000000-0000-0000-0000-000000000005';
