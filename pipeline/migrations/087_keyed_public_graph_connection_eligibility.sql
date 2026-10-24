-- Keep the complete release, projection-generation, suppression, manifest,
-- source-record-version, current-map, and source-backed organization gates,
-- but probe them by the requested edge's exact keys. The 085 statement-wide
-- materialized eligibility sets were semantically correct but made even a
-- bounded ordered API page exceed its deadline on the released graph.
CREATE OR REPLACE VIEW uec.graph_public_connections_current AS
SELECT e.connection_edge_id,e.from_entity_id,e.from_entity_type,e.from_source_id,
       e.from_identifier_type,e.to_entity_id,e.to_entity_type,e.to_source_id,
       e.to_identifier_type,e.relationship_type,e.connection_type,e.confidence,
       e.confidence_band,e.signal_explanation::text AS signal_explanation,
       e.match_method,e.observed_at,e.computed_at,e.ruleset_version,e.conflicting,
       e.release_id,b.projection_version
FROM uec.graph_public_projection_edges e
JOIN uec.graph_public_projection_builds b
  ON b.projection_id=e.projection_id AND b.release_id=e.release_id
JOIN uec.graph_projection_generation generation ON generation.singleton=true
JOIN uec.public_suppression_generation suppression ON suppression.singleton=true
JOIN uec.releases release ON release.release_id=e.release_id
JOIN uec.public_discovery_read_models model ON model.release_id=e.release_id
JOIN uec.release_manifests manifest
  ON manifest.release_id=e.release_id AND manifest.manifest_sha256=model.manifest_sha256
LEFT JOIN uec.public_release_history history
  ON history.release_id=release.release_id AND history.profile=release.profile
WHERE b.active AND b.status='completed'
  AND b.projection_version='graph-release-projection-v3'
  AND b.edge_generation=generation.generation
  AND b.suppression_generation=suppression.generation
  AND b.release_manifest_sha256=manifest.manifest_sha256
  AND release.test_only IS NOT TRUE
  AND (release.status='promoted' OR history.release_id IS NOT NULL)
  AND EXISTS (
      SELECT 1
      FROM uec.graph_public_projection_edge_supports support
      JOIN uec.source_records record
        ON record.source_record_id=support.source_record_id
       AND record.source_id=support.source_id
       AND record.artifact_id=support.artifact_id
      WHERE support.projection_id=e.projection_id
        AND support.connection_edge_id=e.connection_edge_id
        AND EXISTS (
            SELECT 1
            FROM uec.public_discovery_read_model_rows candidate
            WHERE candidate.release_id=e.release_id
              AND candidate.source_record_id=support.source_record_id
              AND EXISTS (
                  SELECT current_support.source_record_id
                  FROM uec.map_facilities_public_discovery_read_model current_support
                  WHERE current_support.release_id=e.release_id
                    AND current_support.facility_id=candidate.facility_id
                    AND current_support.source_record_id=support.source_record_id
                  OFFSET 0
              )
        )
  )
  AND NOT EXISTS (
      SELECT 1
      FROM uec.graph_public_projection_edge_supports support
      LEFT JOIN uec.source_records record
        ON record.source_record_id=support.source_record_id
       AND record.source_id=support.source_id
       AND record.artifact_id=support.artifact_id
      WHERE support.projection_id=e.projection_id
        AND support.connection_edge_id=e.connection_edge_id
        AND (record.source_record_id IS NULL OR NOT EXISTS (
            SELECT 1
            FROM uec.public_discovery_read_model_rows candidate
            WHERE candidate.release_id=e.release_id
              AND candidate.source_record_id=support.source_record_id
              AND EXISTS (
                  SELECT current_support.source_record_id
                  FROM uec.map_facilities_public_discovery_read_model current_support
                  WHERE current_support.release_id=e.release_id
                    AND current_support.facility_id=candidate.facility_id
                    AND current_support.source_record_id=support.source_record_id
                  OFFSET 0
              )
        ))
  )
  AND EXISTS (
      SELECT 1
      FROM uec.graph_public_projection_anchors anchor
      WHERE anchor.projection_id=e.projection_id
        AND anchor.endpoint_id=e.from_endpoint_id
        AND EXISTS (
            SELECT current_anchor.source_record_id
            FROM uec.map_facilities_public_discovery_read_model current_anchor
            WHERE current_anchor.release_id=e.release_id
              AND current_anchor.facility_id=anchor.facility_id
              AND current_anchor.source_record_id=anchor.source_record_id
            OFFSET 0
        )
  )
  AND EXISTS (
      SELECT 1
      FROM uec.graph_public_projection_anchors anchor
      WHERE anchor.projection_id=e.projection_id
        AND anchor.endpoint_id=e.to_endpoint_id
        AND EXISTS (
            SELECT current_anchor.source_record_id
            FROM uec.map_facilities_public_discovery_read_model current_anchor
            WHERE current_anchor.release_id=e.release_id
              AND current_anchor.facility_id=anchor.facility_id
              AND current_anchor.source_record_id=anchor.source_record_id
            OFFSET 0
        )
  )
  AND (e.from_entity_type<>'organization' OR EXISTS (
      SELECT 1 FROM uec.graph_public_organization_label_candidates_current org
      WHERE org.release_id=e.release_id
        AND org.endpoint_id=e.from_endpoint_id
        AND org.organization_id=e.from_entity_id
        AND EXISTS (
            SELECT live.source_record_id
            FROM uec.map_facilities_public_discovery_read_model live
            WHERE live.release_id=e.release_id
              AND live.facility_id=org.facility_id
              AND live.source_record_id=org.source_record_id
            OFFSET 0
        )
      OFFSET 0
  ))
  AND (e.to_entity_type<>'organization' OR EXISTS (
      SELECT 1 FROM uec.graph_public_organization_label_candidates_current org
      WHERE org.release_id=e.release_id
        AND org.endpoint_id=e.to_endpoint_id
        AND org.organization_id=e.to_entity_id
        AND EXISTS (
            SELECT live.source_record_id
            FROM uec.map_facilities_public_discovery_read_model live
            WHERE live.release_id=e.release_id
              AND live.facility_id=org.facility_id
              AND live.source_record_id=org.source_record_id
            OFFSET 0
        )
      OFFSET 0
  ));

COMMENT ON VIEW uec.graph_public_connections_current IS
    'Current v3 graph connections whose complete support, endpoint, release, and source-backed organization evidence remains eligible in the live public map.';
