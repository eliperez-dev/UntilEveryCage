DROP VIEW IF EXISTS uec.map_facilities_display_history;

CREATE VIEW uec.map_facilities_display_history AS
SELECT display.*, observation.classification_category,
       summary.first_observed_at, summary.last_observed_at, summary.observation_count,
       COALESCE(lifecycle.status, 'status_unknown') AS lifecycle_status,
       lifecycle.effective_at AS lifecycle_effective_at,
       lifecycle.source_record_id AS lifecycle_source_record_id
FROM uec.map_facilities_display AS display
JOIN uec.observations AS observation ON observation.observation_id = display.observation_id
LEFT JOIN uec.facility_observation_summary AS summary ON summary.facility_id = display.facility_id
LEFT JOIN uec.facility_lifecycle_current AS lifecycle ON lifecycle.facility_id = display.facility_id;
