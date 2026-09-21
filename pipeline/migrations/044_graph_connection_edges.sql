-- D6: thin, private graph connection read model.
--
-- This is a derived edge table, not an identity-merge or review workflow.
-- Endpoints remain source-qualified typed references.  Rebuilding this table
-- from source evidence and a versioned ruleset is expected and safe.
CREATE TABLE uec.graph_connection_edges (
    connection_edge_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    edge_key TEXT NOT NULL UNIQUE,
    from_entity_type TEXT NOT NULL
        CHECK (from_entity_type IN ('facility', 'organization', 'evidence_event')),
    from_source_id TEXT NOT NULL REFERENCES uec.sources(source_id),
    from_identifier_type TEXT NOT NULL,
    from_source_identifier TEXT NOT NULL,
    to_entity_type TEXT NOT NULL
        CHECK (to_entity_type IN ('facility', 'organization', 'evidence_event')),
    to_source_id TEXT NOT NULL REFERENCES uec.sources(source_id),
    to_identifier_type TEXT NOT NULL,
    to_source_identifier TEXT NOT NULL,
    relationship_type TEXT NOT NULL,
    connection_type TEXT NOT NULL CHECK (connection_type IN ('exact', 'inferred')),
    confidence NUMERIC(6,5) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    confidence_band TEXT NOT NULL
        CHECK (confidence_band IN ('exact', 'high', 'probable', 'possible', 'low')),
    match_method TEXT NOT NULL,
    supporting_source_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
    signal_explanation JSONB NOT NULL DEFAULT '{}'::jsonb,
    ruleset_version TEXT NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    computed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    conflicting BOOLEAN NOT NULL DEFAULT false,
    suppressed BOOLEAN NOT NULL DEFAULT false,
    storage_state TEXT NOT NULL DEFAULT 'private' CHECK (storage_state = 'private'),
    publication_status TEXT NOT NULL DEFAULT 'not_eligible'
        CHECK (publication_status = 'not_eligible'),
    CHECK (btrim(edge_key) <> ''),
    CHECK (btrim(from_identifier_type) <> '' AND btrim(from_source_identifier) <> ''),
    CHECK (btrim(to_identifier_type) <> '' AND btrim(to_source_identifier) <> ''),
    CHECK (btrim(relationship_type) <> '' AND btrim(match_method) <> ''),
    CHECK (jsonb_typeof(supporting_source_refs) = 'array'),
    CHECK (jsonb_typeof(signal_explanation) = 'object'),
    CHECK ((connection_type = 'exact' AND confidence = 1.00000 AND confidence_band = 'exact')
        OR (connection_type = 'inferred' AND confidence_band <> 'exact'))
);

CREATE INDEX graph_connection_edges_from_idx
    ON uec.graph_connection_edges
       (from_source_id, from_identifier_type, from_source_identifier,
        connection_type, confidence DESC);
CREATE INDEX graph_connection_edges_to_idx
    ON uec.graph_connection_edges
       (to_source_id, to_identifier_type, to_source_identifier,
        connection_type, confidence DESC);
CREATE INDEX graph_connection_edges_filter_idx
    ON uec.graph_connection_edges
       (connection_type, confidence_band, conflicting, suppressed, computed_at DESC);

COMMENT ON TABLE uec.graph_connection_edges IS
    'Private derived exact/inferred graph connections. Source-qualified endpoints never assert a universal identity, merge nodes, or transfer claims.';
COMMENT ON COLUMN uec.graph_connection_edges.confidence IS
    'Versioned ruleset estimate, not a measured probability unless separately calibrated.';
COMMENT ON COLUMN uec.graph_connection_edges.supporting_source_refs IS
    'Redacted/source-qualified evidence references only; raw payloads remain outside the repository.';
