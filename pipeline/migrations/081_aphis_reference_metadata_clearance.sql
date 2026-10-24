-- Narrow approval to the fixed APHIS reference DTO only. This is not a
-- redistribution decision for reports, source payloads, or other APIs.
CREATE TABLE uec.graph_public_evidence_metadata_clearance_events (
    clearance_event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id TEXT NOT NULL CHECK (source_id IN ('us.aphis.annual-reports','us.inspections')),
    profile TEXT NOT NULL CHECK (profile='official'),
    release_id TEXT NOT NULL REFERENCES uec.releases(release_id),
    artifact_id UUID NOT NULL REFERENCES uec.raw_artifacts(artifact_id),
    artifact_sha256 CHAR(64) NOT NULL CHECK (artifact_sha256 ~ '^[0-9a-f]{64}$'),
    scope_version TEXT NOT NULL CHECK (scope_version='aphis-public-reference-metadata-v1'),
    decision_status TEXT NOT NULL CHECK (decision_status IN ('approved','withdrawn')),
    approved_fields TEXT[] NOT NULL CHECK (approved_fields = ARRAY[
        'source_id','evidence_type','event_date','event_period','observed_at','source_url','match_method'
    ]::text[]),
    decision_actor TEXT NOT NULL CHECK (btrim(decision_actor)<>''),
    decision_reference TEXT NOT NULL CHECK (btrim(decision_reference)<>''),
    decided_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
REVOKE ALL ON uec.graph_public_evidence_metadata_clearance_events FROM PUBLIC;
CREATE INDEX graph_public_evidence_metadata_clearance_current_idx
    ON uec.graph_public_evidence_metadata_clearance_events
       (source_id,profile,release_id,artifact_id,decided_at DESC,clearance_event_id DESC);

CREATE FUNCTION uec.validate_graph_public_evidence_metadata_clearance()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    release_profile TEXT;
    release_test_only BOOLEAN;
    release_status TEXT;
    artifact_digest CHAR(64);
BEGIN
    SELECT profile,test_only,status INTO release_profile,release_test_only,release_status
      FROM uec.releases WHERE release_id=NEW.release_id;
    IF release_profile IS DISTINCT FROM NEW.profile OR release_profile<>'official'
       OR release_test_only IS TRUE OR release_status NOT IN ('promoted','validated') THEN
        RAISE EXCEPTION 'metadata clearance requires an eligible official release';
    END IF;
    IF release_status='validated' AND NOT EXISTS (
        SELECT 1 FROM uec.public_release_history history
         WHERE history.release_id=NEW.release_id AND history.profile=NEW.profile
    ) THEN
        RAISE EXCEPTION 'metadata clearance requires a historically public release';
    END IF;
    SELECT sha256 INTO artifact_digest FROM uec.raw_artifacts WHERE artifact_id=NEW.artifact_id;
    IF artifact_digest IS DISTINCT FROM NEW.artifact_sha256 THEN
        RAISE EXCEPTION 'metadata clearance artifact digest does not match immutable artifact';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM uec.source_records record
        JOIN uec.graph_evidence_events event
          ON event.source_record_id=record.source_record_id AND event.source_id=record.source_id
        WHERE record.source_id=NEW.source_id AND record.artifact_id=NEW.artifact_id
          AND ((NEW.source_id='us.aphis.annual-reports' AND event.event_type='annual_reports'
                AND event.event_period ~ '^[0-9]{4}$')
            OR (NEW.source_id='us.inspections' AND event.event_type='inspections'
                AND event.event_date IS NOT NULL))
          AND NOT EXISTS (SELECT 1 FROM uec.observations observation
                          JOIN uec.release_members member USING(observation_id)
                          WHERE member.release_id=NEW.release_id
                            AND observation.source_record_id=record.source_record_id)
    ) THEN
        RAISE EXCEPTION 'metadata clearance artifact has no eligible non-facility APHIS evidence';
    END IF;
    IF EXISTS (
        SELECT 1 FROM uec.source_records record
        JOIN uec.observations observation ON observation.source_record_id=record.source_record_id
        JOIN uec.release_members member ON member.observation_id=observation.observation_id
        WHERE record.source_id=NEW.source_id AND record.artifact_id=NEW.artifact_id
          AND member.release_id=NEW.release_id
    ) THEN
        RAISE EXCEPTION 'APHIS evidence artifact cannot contribute facility release members';
    END IF;
    IF NEW.decision_reference<>'user-approved-reference-metadata-only;https://www.aphis.usda.gov/animal-care/awa-services/usda-animal-care-public-search-tool' THEN
        RAISE EXCEPTION 'metadata clearance reference must identify the approved narrow scope and official source';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER graph_public_evidence_metadata_clearance_guard
    BEFORE INSERT ON uec.graph_public_evidence_metadata_clearance_events
    FOR EACH ROW EXECUTE FUNCTION uec.validate_graph_public_evidence_metadata_clearance();
CREATE TRIGGER graph_public_evidence_metadata_clearance_append_only
    BEFORE UPDATE OR DELETE ON uec.graph_public_evidence_metadata_clearance_events
    FOR EACH ROW EXECUTE FUNCTION uec.reject_evidence_mutation();

CREATE VIEW uec.graph_public_evidence_metadata_clearance_current AS
SELECT clearance_event_id,source_id,profile,release_id,artifact_id,artifact_sha256,
       scope_version,decision_status,approved_fields,decision_actor,decision_reference,decided_at
FROM (
    SELECT DISTINCT ON (source_id,profile,release_id,artifact_id) *
      FROM uec.graph_public_evidence_metadata_clearance_events
     ORDER BY source_id,profile,release_id,artifact_id,decided_at DESC,clearance_event_id DESC
) latest
WHERE decision_status='approved';

COMMENT ON TABLE uec.graph_public_evidence_metadata_clearance_events IS
    'Append-only operator-approved metadata-only permission for the frozen APHIS public reference DTO. Does not clear report contents, payloads, raw identifiers, or other publication surfaces.';
COMMENT ON COLUMN uec.graph_public_evidence_metadata_clearance_events.approved_fields IS
    'Exact public reference allowlist; any additional field requires a separately authorized migration and decision.';
COMMENT ON COLUMN uec.graph_public_evidence_metadata_clearance_events.decision_reference IS
    'Fixed reference to the user-authorized metadata-only scope and APHIS public-search description; not a blanket license claim.';

-- The public selector uses this narrow view only for the APHIS reference DTO.
-- Source-rights gates for all other releases and surfaces are unchanged.
CREATE OR REPLACE VIEW uec.graph_public_evidence_references_current AS
SELECT build.release_id, reference.evidence_ref_id, endpoint.public_entity_id,
       endpoint.source_id AS endpoint_source_id, reference.source_id,
       reference.evidence_type, reference.event_date, reference.event_period,
       reference.observed_at, reference.source_url, reference.match_method
FROM uec.graph_public_projection_evidence_refs reference
JOIN uec.graph_public_projection_builds build
  ON build.projection_id=reference.projection_id
JOIN uec.graph_public_projection_endpoints endpoint
  ON endpoint.projection_id=reference.projection_id
 AND endpoint.endpoint_id=reference.endpoint_id AND endpoint.entity_type='facility'
JOIN uec.graph_projection_generation generation ON generation.singleton=true
JOIN uec.public_suppression_generation suppression ON suppression.singleton=true
JOIN uec.releases release ON release.release_id=build.release_id
JOIN uec.public_discovery_read_models model ON model.release_id=build.release_id
JOIN uec.release_manifests manifest
  ON manifest.release_id=build.release_id AND manifest.manifest_sha256=model.manifest_sha256
JOIN uec.source_records evidence_record
  ON evidence_record.source_record_id=reference.evidence_source_record_id
 AND evidence_record.source_id=reference.source_id
JOIN uec.publication_review_release_current review
  ON review.source_record_id=evidence_record.source_record_id AND review.release_id=build.release_id
JOIN uec.raw_artifacts artifact ON artifact.artifact_id=evidence_record.artifact_id
JOIN uec.graph_public_evidence_metadata_clearance_current clearance
  ON clearance.source_id=evidence_record.source_id
 AND clearance.profile=release.profile AND clearance.release_id=build.release_id
 AND clearance.artifact_id=artifact.artifact_id AND clearance.artifact_sha256=artifact.sha256
 AND clearance.scope_version='aphis-public-reference-metadata-v1'
 AND clearance.approved_fields=ARRAY[
     'source_id','evidence_type','event_date','event_period','observed_at','source_url','match_method'
 ]::text[]
JOIN uec.graph_public_projection_anchors anchor
  ON anchor.projection_id=reference.projection_id AND anchor.endpoint_id=endpoint.endpoint_id
JOIN uec.map_facilities_public_discovery_read_model current_anchor
  ON current_anchor.release_id=build.release_id
 AND current_anchor.source_record_id=anchor.source_record_id
 AND current_anchor.facility_id=anchor.facility_id
LEFT JOIN uec.public_release_history history
  ON history.release_id=release.release_id AND history.profile=release.profile
WHERE build.active AND build.status='completed'
  AND build.projection_version='graph-release-projection-v3'
  AND build.edge_generation=generation.generation
  AND build.suppression_generation=suppression.generation
  AND build.release_manifest_sha256=manifest.manifest_sha256
  AND release.test_only IS NOT TRUE
  AND (release.status='promoted' OR history.release_id IS NOT NULL)
  AND review.publication_eligible=true AND review.privacy_screening_status='passed'
  AND review.factual_review_status<>'rejected' AND review.maintainer_approval='approved'
  AND NOT EXISTS (SELECT 1 FROM uec.public_access_restricted restricted
                  WHERE restricted.source_record_id=reference.evidence_source_record_id)
  AND NOT EXISTS (SELECT 1 FROM uec.public_access_restricted restricted
                  WHERE restricted.source_record_id=anchor.source_record_id)
  AND NOT EXISTS (
      SELECT 1 FROM uec.observations observation
      JOIN uec.release_members member ON member.observation_id=observation.observation_id
      WHERE member.release_id=build.release_id
        AND observation.source_record_id=evidence_record.source_record_id
  );

DO $$
DECLARE role_row RECORD;
BEGIN
    FOR role_row IN SELECT rolname FROM pg_roles WHERE left(rolname,17)='uec_graph_writer_' LOOP
        EXECUTE format('GRANT SELECT ON uec.graph_public_evidence_metadata_clearance_current TO %I', role_row.rolname);
    END LOOP;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='uec_api_runtime') THEN
        REVOKE ALL ON uec.graph_public_evidence_metadata_clearance_events FROM uec_api_runtime;
        GRANT SELECT ON uec.graph_public_evidence_references_current TO uec_api_runtime;
    END IF;
END
$$;
