-- Store a qualified endpoint and its release anchors once per projection.
-- The private source identifier is used only by the builder's in-memory join.
CREATE TABLE uec.graph_public_projection_endpoints (
    projection_id UUID NOT NULL REFERENCES uec.graph_public_projection_builds(projection_id),
    endpoint_id UUID NOT NULL,
    public_entity_id UUID NOT NULL,
    entity_type TEXT NOT NULL CHECK (entity_type IN ('facility','organization')),
    source_id TEXT NOT NULL,
    identifier_type TEXT NOT NULL,
    PRIMARY KEY (projection_id, endpoint_id),
    UNIQUE (projection_id, endpoint_id, public_entity_id, entity_type)
);

CREATE TABLE uec.graph_public_projection_anchors (
    projection_id UUID NOT NULL,
    endpoint_id UUID NOT NULL,
    source_record_id UUID NOT NULL REFERENCES uec.source_records(source_record_id),
    facility_id UUID NOT NULL REFERENCES uec.facilities(facility_id),
    PRIMARY KEY (projection_id, endpoint_id, source_record_id, facility_id),
    FOREIGN KEY (projection_id, endpoint_id)
        REFERENCES uec.graph_public_projection_endpoints(projection_id, endpoint_id)
);
CREATE INDEX graph_public_projection_anchor_current_idx
    ON uec.graph_public_projection_anchors(source_record_id, facility_id, projection_id, endpoint_id);

ALTER TABLE uec.graph_public_projection_edges
    ADD COLUMN from_endpoint_id UUID,
    ADD COLUMN to_endpoint_id UUID;
ALTER TABLE uec.graph_public_projection_edges
    ADD CONSTRAINT graph_public_projection_from_endpoint_fk
        FOREIGN KEY (projection_id, from_endpoint_id, from_entity_id, from_entity_type)
        REFERENCES uec.graph_public_projection_endpoints(projection_id, endpoint_id, public_entity_id, entity_type),
    ADD CONSTRAINT graph_public_projection_to_endpoint_fk
        FOREIGN KEY (projection_id, to_endpoint_id, to_entity_id, to_entity_type)
        REFERENCES uec.graph_public_projection_endpoints(projection_id, endpoint_id, public_entity_id, entity_type);

CREATE OR REPLACE VIEW uec.graph_public_connections_current AS
SELECT e.connection_edge_id, e.from_entity_id, e.from_entity_type, e.from_source_id,
       e.from_identifier_type, e.to_entity_id, e.to_entity_type, e.to_source_id,
       e.to_identifier_type, e.relationship_type, e.connection_type, e.confidence,
       e.confidence_band, e.signal_explanation::text AS signal_explanation,
       e.match_method, e.observed_at, e.computed_at, e.ruleset_version, e.conflicting,
       e.release_id, b.projection_version
FROM uec.graph_public_projection_edges e
JOIN uec.graph_public_projection_builds b
  ON b.projection_id=e.projection_id AND b.release_id=e.release_id
JOIN uec.graph_projection_generation generation ON generation.singleton=true
JOIN uec.releases release ON release.release_id=e.release_id
JOIN uec.public_discovery_read_models model ON model.release_id=e.release_id
JOIN uec.release_manifests manifest
  ON manifest.release_id=e.release_id AND manifest.manifest_sha256=model.manifest_sha256
LEFT JOIN uec.public_release_history history
  ON history.release_id=release.release_id AND history.profile=release.profile
WHERE b.active AND b.status='completed'
  AND b.projection_version='graph-release-projection-v2'
  AND b.edge_generation=generation.generation
  AND b.release_manifest_sha256=manifest.manifest_sha256
  AND release.test_only IS NOT TRUE
  AND (release.status='promoted' OR history.release_id IS NOT NULL)
  AND EXISTS (
      SELECT 1 FROM uec.graph_public_projection_edge_supports support
      JOIN uec.source_records record
        ON record.source_record_id=support.source_record_id
       AND record.source_id=support.source_id AND record.artifact_id=support.artifact_id
      JOIN uec.map_facilities_public_discovery_read_model current_support
        ON current_support.release_id=e.release_id
       AND current_support.source_record_id=support.source_record_id
      WHERE support.projection_id=e.projection_id AND support.connection_edge_id=e.connection_edge_id
  )
  AND NOT EXISTS (
      SELECT 1 FROM uec.graph_public_projection_edge_supports support
      LEFT JOIN uec.source_records record
        ON record.source_record_id=support.source_record_id
       AND record.source_id=support.source_id AND record.artifact_id=support.artifact_id
      WHERE support.projection_id=e.projection_id AND support.connection_edge_id=e.connection_edge_id
        AND (record.source_record_id IS NULL OR NOT EXISTS (
              SELECT 1 FROM uec.map_facilities_public_discovery_read_model current_support
              WHERE current_support.release_id=e.release_id
                AND current_support.source_record_id=support.source_record_id
        ))
  )
  AND EXISTS (
      SELECT 1 FROM uec.graph_public_projection_anchors anchor
      JOIN uec.map_facilities_public_discovery_read_model current_anchor
        ON current_anchor.release_id=e.release_id
       AND current_anchor.source_record_id=anchor.source_record_id
       AND current_anchor.facility_id=anchor.facility_id
      WHERE anchor.projection_id=e.projection_id AND anchor.endpoint_id=e.from_endpoint_id
  )
  AND EXISTS (
      SELECT 1 FROM uec.graph_public_projection_anchors anchor
      JOIN uec.map_facilities_public_discovery_read_model current_anchor
        ON current_anchor.release_id=e.release_id
       AND current_anchor.source_record_id=anchor.source_record_id
       AND current_anchor.facility_id=anchor.facility_id
      WHERE anchor.projection_id=e.projection_id AND anchor.endpoint_id=e.to_endpoint_id
  );

COMMENT ON TABLE uec.graph_public_projection_endpoints IS
    'Opaque build-local endpoint references; source-native identifier values are not stored.';
COMMENT ON TABLE uec.graph_public_projection_anchors IS
    'Release-qualified anchors stored once per opaque endpoint, independent of edge fanout.';
COMMENT ON VIEW uec.graph_public_connections_current IS
    'Only v2 normalized endpoint projections pass current release, support, and live eligibility gates.';

DO $$
DECLARE role_row RECORD;
BEGIN
    FOR role_row IN SELECT rolname FROM pg_roles WHERE left(rolname, 17)='uec_graph_writer_' LOOP
        EXECUTE format('GRANT SELECT, INSERT ON uec.graph_public_projection_endpoints TO %I', role_row.rolname);
        EXECUTE format('GRANT SELECT, INSERT ON uec.graph_public_projection_anchors TO %I', role_row.rolname);
    END LOOP;
END
$$;
