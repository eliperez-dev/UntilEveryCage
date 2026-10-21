-- Exact-version lineage for graph evidence that is projected onto a
-- different canonical source record in an already-approved release.
-- This table records mapping provenance only; it does not change any review,
-- privacy, publication, or release state.
CREATE TABLE uec.graph_record_release_bindings (
    release_id TEXT NOT NULL REFERENCES uec.releases(release_id),
    private_source_record_id UUID NOT NULL REFERENCES uec.source_records(source_record_id),
    canonical_source_record_id UUID NOT NULL REFERENCES uec.source_records(source_record_id),
    facility_id UUID NOT NULL REFERENCES uec.facilities(facility_id),
    source_id TEXT NOT NULL REFERENCES uec.sources(source_id),
    artifact_id UUID NOT NULL REFERENCES uec.raw_artifacts(artifact_id),
    binding_method TEXT NOT NULL
        CHECK (binding_method = 'it_recognition_activity_singleton_v1'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (release_id, private_source_record_id),
    UNIQUE (release_id, canonical_source_record_id),
    CHECK (private_source_record_id <> canonical_source_record_id)
);

COMMENT ON TABLE uec.graph_record_release_bindings IS
    'Private source-record aliases to exact canonical records in an approved release; no release or rights decisions are changed.';
COMMENT ON COLUMN uec.graph_record_release_bindings.binding_method IS
    'Exact native recognition/activity pair, singleton on the imported and approved sides.';

DO $$
DECLARE role_row RECORD;
BEGIN
    FOR role_row IN SELECT rolname FROM pg_roles WHERE left(rolname, 17)='uec_graph_writer_' LOOP
        EXECUTE format('GRANT SELECT, INSERT ON uec.graph_record_release_bindings TO %I', role_row.rolname);
    END LOOP;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='uec_api_runtime') THEN
        GRANT SELECT ON uec.graph_record_release_bindings TO uec_api_runtime;
    END IF;
END
$$;
