DROP VIEW IF EXISTS uec.map_facilities_display_history;

CREATE VIEW uec.map_facilities_display_history AS
SELECT display.*, observation.classification_category,
       summary.first_observed_at, summary.last_observed_at, summary.observation_count,
       COALESCE(lifecycle.status, 'status_unknown') AS lifecycle_status,
       lifecycle.effective_at AS lifecycle_effective_at,
       lifecycle.source_record_id AS lifecycle_source_record_id,
       release.ruleset_version AS release_ruleset_version,
       release.created_at AS release_created_at,
       source.source_id AS provenance_source_id,
       source.name AS provenance_source_name,
       source.official_url AS provenance_source_url,
       artifact.retrieved_at AS provenance_retrieved_at
FROM uec.map_facilities_display AS display
JOIN uec.observations AS observation ON observation.observation_id = display.observation_id
JOIN uec.source_records AS record ON record.source_record_id = display.source_record_id
JOIN uec.sources AS source ON source.source_id = record.source_id
JOIN uec.release_members AS member ON member.release_id = display.release_id AND member.observation_id = display.observation_id
JOIN uec.releases AS release ON release.release_id = member.release_id
JOIN uec.raw_artifacts AS artifact ON artifact.artifact_id = record.artifact_id
LEFT JOIN uec.facility_observation_summary AS summary ON summary.facility_id = display.facility_id
LEFT JOIN uec.facility_lifecycle_current AS lifecycle ON lifecycle.facility_id = display.facility_id;
