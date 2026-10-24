-- Add only public opaque canonical routing keys so candidate page scans can
-- preserve entity/source-scoped endpoint performance. The live connection
-- eligibility view remains mandatory before candidates can be returned.
CREATE OR REPLACE VIEW uec.graph_public_connection_page_candidates_current AS
SELECT e.release_id,e.connection_edge_id,
       e.from_entity_id,e.to_entity_id,e.from_source_id,e.to_source_id
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
  AND (release.status='promoted' OR history.release_id IS NOT NULL);

COMMENT ON VIEW uec.graph_public_connection_page_candidates_current IS
    'Opaque release/edge and canonical entity/source routing keys for active approved graph projections; every candidate requires graph_public_connections_current recheck.';
