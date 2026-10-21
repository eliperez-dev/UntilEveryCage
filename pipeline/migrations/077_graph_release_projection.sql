-- Versioned graph materialization checkpoints and selected-release serving projection.
-- The public projection contains no source identifier values or raw graph payloads.

CREATE TABLE uec.graph_edge_materialization_runs (
    materialization_run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id TEXT NOT NULL REFERENCES uec.sources(source_id),
    handoff_sha256 TEXT NOT NULL CHECK (handoff_sha256 ~ '^[0-9a-f]{64}$'),
    materialization_fingerprint TEXT NOT NULL CHECK (materialization_fingerprint ~ '^[0-9a-f]{64}$'),
    status TEXT NOT NULL DEFAULT 'in_progress' CHECK (status IN ('in_progress','completed','failed')),
    edge_inserted_count BIGINT NOT NULL DEFAULT 0 CHECK (edge_inserted_count >= 0),
    edge_updated_count BIGINT NOT NULL DEFAULT 0 CHECK (edge_updated_count >= 0),
    edge_unchanged_count BIGINT NOT NULL DEFAULT 0 CHECK (edge_unchanged_count >= 0),
    edge_count BIGINT NOT NULL DEFAULT 0 CHECK (edge_count >= 0),
    matcher_summary JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(matcher_summary)='object'),
    error_category TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    UNIQUE (source_id, handoff_sha256, materialization_fingerprint),
    CHECK ((status='completed') = (completed_at IS NOT NULL))
);

CREATE TABLE uec.graph_projection_generation (
    singleton BOOLEAN PRIMARY KEY DEFAULT true CHECK (singleton),
    generation BIGINT NOT NULL DEFAULT 0 CHECK (generation >= 0)
);
INSERT INTO uec.graph_projection_generation(singleton,generation) VALUES (true,0);

CREATE FUNCTION uec.bump_graph_projection_generation() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,uec AS $$
BEGIN
    UPDATE uec.graph_projection_generation SET generation=generation+1 WHERE singleton=true;
    RETURN NULL;
END
$$;
REVOKE ALL ON FUNCTION uec.bump_graph_projection_generation() FROM PUBLIC;

CREATE TRIGGER graph_edges_projection_generation
AFTER INSERT OR UPDATE OR DELETE ON uec.graph_connection_edges
FOR EACH STATEMENT EXECUTE FUNCTION uec.bump_graph_projection_generation();
CREATE TRIGGER graph_bindings_projection_generation
AFTER INSERT OR UPDATE OR DELETE ON uec.graph_record_release_bindings
FOR EACH STATEMENT EXECUTE FUNCTION uec.bump_graph_projection_generation();
CREATE TRIGGER graph_identifiers_projection_generation
AFTER INSERT OR UPDATE OR DELETE ON uec.source_entity_identifiers
FOR EACH STATEMENT EXECUTE FUNCTION uec.bump_graph_projection_generation();

CREATE TABLE uec.graph_public_projection_builds (
    projection_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    release_id TEXT NOT NULL REFERENCES uec.releases(release_id),
    projection_version TEXT NOT NULL,
    edge_generation BIGINT NOT NULL,
    release_manifest_sha256 TEXT NOT NULL CHECK (release_manifest_sha256 ~ '^[0-9a-f]{64}$'),
    suppression_generation BIGINT NOT NULL,
    status TEXT NOT NULL DEFAULT 'in_progress' CHECK (status IN ('in_progress','completed','failed')),
    edge_count BIGINT NOT NULL DEFAULT 0 CHECK (edge_count >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    active BOOLEAN NOT NULL DEFAULT false,
    UNIQUE (projection_id, release_id),
    CHECK ((status='completed') = (completed_at IS NOT NULL)),
    CHECK (NOT active OR status='completed')
);
CREATE INDEX graph_public_projection_build_active_idx
    ON uec.graph_public_projection_builds(release_id, projection_version, edge_generation, completed_at DESC)
    WHERE active AND status='completed';

CREATE TABLE uec.graph_public_projection_edges (
    projection_id UUID NOT NULL,
    release_id TEXT NOT NULL,
    connection_edge_id UUID NOT NULL,
    from_entity_id UUID NOT NULL,
    from_entity_type TEXT NOT NULL CHECK (from_entity_type IN ('facility','organization')),
    from_source_id TEXT NOT NULL,
    from_identifier_type TEXT NOT NULL,
    to_entity_id UUID NOT NULL,
    to_entity_type TEXT NOT NULL CHECK (to_entity_type IN ('facility','organization')),
    to_source_id TEXT NOT NULL,
    to_identifier_type TEXT NOT NULL,
    relationship_type TEXT NOT NULL,
    connection_type TEXT NOT NULL CHECK (connection_type IN ('exact','inferred')),
    confidence DOUBLE PRECISION NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    confidence_band TEXT NOT NULL CHECK (confidence_band IN ('exact','high','medium','low')),
    signal_explanation JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(signal_explanation)='object'),
    match_method TEXT NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    computed_at TIMESTAMPTZ NOT NULL,
    ruleset_version TEXT NOT NULL,
    conflicting BOOLEAN NOT NULL DEFAULT false,
    PRIMARY KEY (projection_id, connection_edge_id),
    FOREIGN KEY (projection_id, release_id)
        REFERENCES uec.graph_public_projection_builds(projection_id, release_id)
);
CREATE INDEX graph_public_projection_edges_page_idx
    ON uec.graph_public_projection_edges(release_id, projection_id, connection_edge_id DESC);
CREATE INDEX graph_public_projection_edges_from_idx
    ON uec.graph_public_projection_edges(release_id, projection_id, from_entity_id, connection_edge_id DESC);
CREATE INDEX graph_public_projection_edges_to_idx
    ON uec.graph_public_projection_edges(release_id, projection_id, to_entity_id, connection_edge_id DESC);
CREATE INDEX graph_public_projection_edges_filter_idx
    ON uec.graph_public_projection_edges(release_id, projection_id, connection_type, confidence_band, conflicting, connection_edge_id DESC);

-- Canonical selected-release record references remain internal to the serving
-- gate and are not granted to the network role or emitted in the API DTO.
CREATE TABLE uec.graph_public_projection_edge_supports (
    projection_id UUID NOT NULL,
    connection_edge_id UUID NOT NULL,
    source_record_id UUID NOT NULL REFERENCES uec.source_records(source_record_id),
    source_id TEXT NOT NULL REFERENCES uec.sources(source_id),
    artifact_id UUID NOT NULL REFERENCES uec.raw_artifacts(artifact_id),
    PRIMARY KEY (projection_id, connection_edge_id, source_record_id),
    FOREIGN KEY (projection_id, connection_edge_id)
        REFERENCES uec.graph_public_projection_edges(projection_id, connection_edge_id)
);
CREATE INDEX graph_public_projection_support_record_idx
    ON uec.graph_public_projection_edge_supports(source_record_id, projection_id, connection_edge_id);

CREATE TABLE uec.graph_public_projection_endpoint_anchors (
    projection_id UUID NOT NULL,
    connection_edge_id UUID NOT NULL,
    endpoint_side TEXT NOT NULL CHECK (endpoint_side IN ('from','to')),
    source_record_id UUID NOT NULL REFERENCES uec.source_records(source_record_id),
    facility_id UUID NOT NULL REFERENCES uec.facilities(facility_id),
    PRIMARY KEY (projection_id, connection_edge_id, endpoint_side, source_record_id, facility_id),
    FOREIGN KEY (projection_id, connection_edge_id)
        REFERENCES uec.graph_public_projection_edges(projection_id, connection_edge_id)
);
CREATE INDEX graph_public_projection_anchor_current_idx
    ON uec.graph_public_projection_endpoint_anchors(source_record_id, facility_id, projection_id, connection_edge_id);

CREATE VIEW uec.graph_public_connections_current AS
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
      WHERE support.projection_id=e.projection_id
        AND support.connection_edge_id=e.connection_edge_id
  )
  AND NOT EXISTS (
      SELECT 1 FROM uec.graph_public_projection_edge_supports support
      LEFT JOIN uec.source_records record
        ON record.source_record_id=support.source_record_id
       AND record.source_id=support.source_id AND record.artifact_id=support.artifact_id
      WHERE support.projection_id=e.projection_id
        AND support.connection_edge_id=e.connection_edge_id
        AND (record.source_record_id IS NULL OR NOT EXISTS (
              SELECT 1 FROM uec.map_facilities_public_discovery_read_model current_support
              WHERE current_support.release_id=e.release_id
                AND current_support.source_record_id=support.source_record_id
        ))
  )
  AND EXISTS (
      SELECT 1 FROM uec.graph_public_projection_endpoint_anchors anchor
      JOIN uec.map_facilities_public_discovery_read_model current_anchor
        ON current_anchor.release_id=e.release_id
       AND current_anchor.source_record_id=anchor.source_record_id
       AND current_anchor.facility_id=anchor.facility_id
      WHERE anchor.projection_id=e.projection_id
        AND anchor.connection_edge_id=e.connection_edge_id
        AND anchor.endpoint_side='from'
  )
  AND EXISTS (
      SELECT 1 FROM uec.graph_public_projection_endpoint_anchors anchor
      JOIN uec.map_facilities_public_discovery_read_model current_anchor
        ON current_anchor.release_id=e.release_id
       AND current_anchor.source_record_id=anchor.source_record_id
       AND current_anchor.facility_id=anchor.facility_id
      WHERE anchor.projection_id=e.projection_id
        AND anchor.connection_edge_id=e.connection_edge_id
        AND anchor.endpoint_side='to'
  );

COMMENT ON TABLE uec.graph_edge_materialization_runs IS
    'Version-keyed completed private matcher/edge passes; a new fingerprint rebuilds edges without replaying base ingest.';
COMMENT ON TABLE uec.graph_public_projection_edges IS
    'Safe release-scoped graph projection; contains opaque canonical endpoints and sanitized signals, not source identifier values or raw evidence.';
COMMENT ON VIEW uec.graph_public_connections_current IS
    'Indexed graph projection with current release, support, rights, and suppression gates. Generation mismatch hides stale projections.';

DO $$
DECLARE role_row RECORD;
BEGIN
    FOR role_row IN SELECT rolname FROM pg_roles WHERE left(rolname, 17)='uec_graph_writer_' LOOP
        EXECUTE format('GRANT SELECT, INSERT, UPDATE ON uec.graph_edge_materialization_runs TO %I', role_row.rolname);
        EXECUTE format('GRANT SELECT ON uec.graph_projection_generation TO %I', role_row.rolname);
        EXECUTE format('GRANT SELECT, INSERT, UPDATE ON uec.graph_public_projection_builds TO %I', role_row.rolname);
        EXECUTE format('GRANT SELECT, INSERT ON uec.graph_public_projection_edges TO %I', role_row.rolname);
        EXECUTE format('GRANT SELECT, INSERT ON uec.graph_public_projection_edge_supports TO %I', role_row.rolname);
        EXECUTE format('GRANT SELECT, INSERT ON uec.graph_public_projection_endpoint_anchors TO %I', role_row.rolname);
    END LOOP;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='uec_api_runtime') THEN
        GRANT SELECT ON uec.graph_public_connections_current TO uec_api_runtime;
    END IF;
END
$$;
