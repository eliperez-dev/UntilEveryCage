-- Release-safe, typed references to APHIS evidence records reviewed for a release.
-- Only event type/date/period, the fixed government source URL, and the
-- source-scoped match method enter this serving projection. Event identifiers,
-- native identifiers, and event payloads remain private.

CREATE TABLE uec.graph_source_name_assertions (
    name_assertion_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id TEXT NOT NULL REFERENCES uec.sources(source_id),
    source_record_id UUID NOT NULL REFERENCES uec.source_records(source_record_id),
    organization_id UUID NOT NULL REFERENCES uec.organizations(organization_id),
    identifier_id UUID NOT NULL REFERENCES uec.source_entity_identifiers(identifier_id),
    assertion_role TEXT NOT NULL CHECK (assertion_role IN ('legal','business','trading','dba','operator','brand')),
    source_field TEXT NOT NULL CHECK (btrim(source_field)<>''),
    assertion_value TEXT NOT NULL CHECK (btrim(assertion_value)<>''),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source_record_id,identifier_id,assertion_role,source_field,assertion_value)
);
CREATE INDEX graph_source_name_assertions_lookup_idx
    ON uec.graph_source_name_assertions(source_id,source_record_id,organization_id,assertion_role);
CREATE FUNCTION uec.validate_graph_source_name_assertion()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM uec.source_records record
                   JOIN uec.source_entity_identifiers identifier
                     ON identifier.source_record_id=record.source_record_id
                    AND identifier.source_id=record.source_id
                   WHERE record.source_record_id=NEW.source_record_id
                     AND record.source_id=NEW.source_id
                     AND identifier.identifier_id=NEW.identifier_id
                     AND identifier.entity_type='organization'
                     AND identifier.organization_id=NEW.organization_id) THEN
        RAISE EXCEPTION 'business name assertion must bind an organization identifier on the same source record';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER graph_source_name_assertions_guard
    BEFORE INSERT ON uec.graph_source_name_assertions
    FOR EACH ROW EXECUTE FUNCTION uec.validate_graph_source_name_assertion();
CREATE TRIGGER graph_source_name_assertions_append_only
    BEFORE UPDATE OR DELETE ON uec.graph_source_name_assertions
    FOR EACH ROW EXECUTE FUNCTION uec.reject_evidence_mutation();

CREATE TABLE uec.graph_public_projection_org_labels (
    projection_id UUID NOT NULL,
    endpoint_id UUID NOT NULL,
    label_source_record_id UUID NOT NULL REFERENCES uec.source_records(source_record_id),
    display_name TEXT NOT NULL CHECK (btrim(display_name)<>''),
    assertion_role TEXT NOT NULL CHECK (assertion_role IN ('legal','business','trading','dba','operator','brand')),
    PRIMARY KEY (projection_id,endpoint_id),
    FOREIGN KEY (projection_id,endpoint_id)
        REFERENCES uec.graph_public_projection_endpoints(projection_id,endpoint_id)
);

CREATE TABLE uec.graph_public_projection_evidence_refs (
    evidence_ref_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    projection_id UUID NOT NULL,
    endpoint_id UUID NOT NULL,
    evidence_source_record_id UUID NOT NULL REFERENCES uec.source_records(source_record_id),
    source_id TEXT NOT NULL CHECK (source_id IN ('us.aphis.annual-reports','us.inspections')),
    evidence_type TEXT NOT NULL CHECK (evidence_type IN ('annual_reports','inspections')),
    event_date DATE,
    event_period TEXT,
    observed_at TIMESTAMPTZ NOT NULL,
    source_url TEXT NOT NULL CHECK (source_url IN (
        'https://direct.aphis.usda.gov/awa/research-facility-report/annual-summary',
        'https://direct.aphis.usda.gov/awa/search/inspection-reports'
    )),
    match_method TEXT NOT NULL CHECK (match_method='exact_source_identifier'),
    UNIQUE (projection_id, endpoint_id, evidence_source_record_id),
    FOREIGN KEY (projection_id, endpoint_id)
        REFERENCES uec.graph_public_projection_endpoints(projection_id,endpoint_id),
    CHECK ((evidence_type='annual_reports' AND source_id='us.aphis.annual-reports'
            AND event_date IS NULL AND event_period ~ '^[0-9]{4}$'
            AND source_url='https://direct.aphis.usda.gov/awa/research-facility-report/annual-summary')
        OR (evidence_type='inspections' AND source_id='us.inspections'
            AND event_date IS NOT NULL AND event_period IS NULL
            AND source_url='https://direct.aphis.usda.gov/awa/search/inspection-reports'))
);
CREATE INDEX graph_public_projection_evidence_ref_current_idx
    ON uec.graph_public_projection_evidence_refs(projection_id,endpoint_id,evidence_type,event_period,event_date);

CREATE OR REPLACE VIEW uec.graph_public_evidence_references_current AS
SELECT build.release_id, reference.evidence_ref_id, endpoint.public_entity_id, endpoint.source_id AS endpoint_source_id,
       reference.source_id, reference.evidence_type, reference.event_date,
       reference.event_period, reference.observed_at, reference.source_url,
       reference.match_method
FROM uec.graph_public_projection_evidence_refs reference
JOIN uec.graph_public_projection_builds build
  ON build.projection_id=reference.projection_id
JOIN uec.graph_public_projection_endpoints endpoint
  ON endpoint.projection_id=reference.projection_id
 AND endpoint.endpoint_id=reference.endpoint_id
 AND endpoint.entity_type='facility'
JOIN uec.graph_projection_generation generation ON generation.singleton=true
JOIN uec.releases release ON release.release_id=build.release_id
JOIN uec.public_discovery_read_models model ON model.release_id=build.release_id
JOIN uec.release_manifests manifest
  ON manifest.release_id=build.release_id AND manifest.manifest_sha256=model.manifest_sha256
JOIN uec.source_records evidence_record
  ON evidence_record.source_record_id=reference.evidence_source_record_id
 AND evidence_record.source_id=reference.source_id
JOIN uec.publication_review_release_current review
  ON review.source_record_id=evidence_record.source_record_id
 AND review.release_id=build.release_id
JOIN uec.raw_artifacts artifact ON artifact.artifact_id=evidence_record.artifact_id
JOIN (
  SELECT DISTINCT ON (source_id,profile,release_id,artifact_id) *
  FROM uec.source_rights_decisions
  ORDER BY source_id,profile,release_id,artifact_id,decided_at DESC,source_rights_decision_id DESC
) rights
  ON rights.source_id=evidence_record.source_id
 AND rights.profile=release.profile
 AND rights.release_id=build.release_id
 AND rights.artifact_id=artifact.artifact_id
 AND rights.artifact_sha256=artifact.sha256
 AND rights.redistribution_status='cleared'
JOIN uec.graph_public_projection_anchors anchor
  ON anchor.projection_id=reference.projection_id
 AND anchor.endpoint_id=endpoint.endpoint_id
JOIN uec.map_facilities_public_discovery_read_model current_anchor
  ON current_anchor.release_id=build.release_id
 AND current_anchor.source_record_id=anchor.source_record_id
 AND current_anchor.facility_id=anchor.facility_id
LEFT JOIN uec.public_release_history history
  ON history.release_id=release.release_id AND history.profile=release.profile
WHERE build.active AND build.status='completed'
  AND build.projection_version='graph-release-projection-v3'
  AND build.edge_generation=generation.generation
  AND build.release_manifest_sha256=manifest.manifest_sha256
  AND release.test_only IS NOT TRUE
  AND (release.status='promoted' OR history.release_id IS NOT NULL)
  AND review.publication_eligible=true
  AND review.privacy_screening_status='passed'
  AND review.factual_review_status<>'rejected'
  AND review.maintainer_approval='approved'
  AND NOT EXISTS (
      SELECT 1 FROM uec.public_access_restricted restricted
      WHERE restricted.source_record_id=reference.evidence_source_record_id
  )
  AND NOT EXISTS (
      SELECT 1 FROM uec.public_access_restricted restricted
      WHERE restricted.source_record_id=anchor.source_record_id
  );

CREATE OR REPLACE VIEW uec.graph_public_organization_labels_current AS
SELECT build.release_id,endpoint.public_entity_id AS organization_id,label.display_name,label.assertion_role
FROM uec.graph_public_projection_org_labels label
JOIN uec.graph_public_projection_builds build ON build.projection_id=label.projection_id
JOIN uec.graph_public_projection_endpoints endpoint
  ON endpoint.projection_id=label.projection_id AND endpoint.endpoint_id=label.endpoint_id
 AND endpoint.entity_type='organization'
JOIN uec.graph_projection_generation generation ON generation.singleton=true
JOIN uec.releases release ON release.release_id=build.release_id
JOIN uec.public_discovery_read_models model ON model.release_id=build.release_id
JOIN uec.release_manifests manifest
  ON manifest.release_id=build.release_id AND manifest.manifest_sha256=model.manifest_sha256
JOIN uec.graph_public_projection_anchors anchor
  ON anchor.projection_id=label.projection_id AND anchor.endpoint_id=label.endpoint_id
JOIN uec.source_records label_record
  ON label_record.source_record_id=label.label_source_record_id
JOIN uec.raw_artifacts artifact ON artifact.artifact_id=label_record.artifact_id
JOIN uec.publication_review_release_current review
  ON review.source_record_id=label_record.source_record_id
 AND review.release_id=build.release_id
JOIN (
  SELECT DISTINCT ON (source_id,profile,release_id,artifact_id) *
  FROM uec.source_rights_decisions
  ORDER BY source_id,profile,release_id,artifact_id,decided_at DESC,source_rights_decision_id DESC
) rights
  ON rights.source_id=label_record.source_id
 AND rights.profile=release.profile
 AND rights.release_id=build.release_id
 AND rights.artifact_id=artifact.artifact_id
 AND rights.artifact_sha256=artifact.sha256
 AND rights.redistribution_status='cleared'
JOIN uec.map_facilities_public_discovery_read_model current_anchor
  ON current_anchor.release_id=build.release_id
 AND current_anchor.source_record_id=anchor.source_record_id
 AND current_anchor.facility_id=anchor.facility_id
LEFT JOIN uec.public_release_history history
  ON history.release_id=release.release_id AND history.profile=release.profile
WHERE build.active AND build.status='completed'
  AND build.projection_version='graph-release-projection-v3'
  AND build.edge_generation=generation.generation
  AND build.release_manifest_sha256=manifest.manifest_sha256
  AND release.test_only IS NOT TRUE
  AND (release.status='promoted' OR history.release_id IS NOT NULL)
  AND review.publication_eligible=true
  AND review.privacy_screening_status='passed'
  AND review.factual_review_status<>'rejected'
  AND review.maintainer_approval='approved'
  AND NOT EXISTS (
      SELECT 1 FROM uec.public_access_restricted restricted
      WHERE restricted.source_record_id=label.label_source_record_id
  )
  AND NOT EXISTS (
      SELECT 1 FROM uec.public_access_restricted restricted
      WHERE restricted.source_record_id=anchor.source_record_id
  );

COMMENT ON TABLE uec.graph_public_projection_evidence_refs IS
    'Allowlisted APHIS evidence references for a source-qualified endpoint. Contains no event/native identifier or raw payload.';
COMMENT ON VIEW uec.graph_public_evidence_references_current IS
    'Current release, live membership, suppression, and source-record gates for safe typed APHIS evidence references.';
COMMENT ON TABLE uec.graph_source_name_assertions IS
    'Private source-backed business labels bound to one source-record organization identifier; not publication approval.';
COMMENT ON TABLE uec.graph_public_projection_org_labels IS
    'Selected-release labels derived only from exact business identifiers and explicit same-record business-name assertions, with label source records retained for live rights and review gates.';

CREATE TRIGGER graph_evidence_events_projection_generation
AFTER INSERT ON uec.graph_evidence_events
FOR EACH STATEMENT EXECUTE FUNCTION uec.bump_graph_projection_generation();
CREATE TRIGGER graph_evidence_links_projection_generation
AFTER INSERT ON uec.graph_evidence_links
FOR EACH STATEMENT EXECUTE FUNCTION uec.bump_graph_projection_generation();
CREATE TRIGGER graph_source_name_assertions_projection_generation
AFTER INSERT ON uec.graph_source_name_assertions
FOR EACH STATEMENT EXECUTE FUNCTION uec.bump_graph_projection_generation();

-- Existing builds predate this additive reference projection. Force a fresh
-- selected-release build so an old completed build cannot be mistaken for a
-- build that evaluated APHIS evidence references.
UPDATE uec.graph_projection_generation
   SET generation=generation+1
 WHERE singleton=true;

DO $$
DECLARE role_row RECORD;
BEGIN
    FOR role_row IN SELECT rolname FROM pg_roles WHERE left(rolname,17)='uec_graph_writer_' LOOP
        EXECUTE format('GRANT SELECT, INSERT ON uec.graph_public_projection_evidence_refs TO %I', role_row.rolname);
        EXECUTE format('GRANT SELECT, INSERT ON uec.graph_source_name_assertions TO %I', role_row.rolname);
        EXECUTE format('GRANT SELECT, INSERT ON uec.graph_public_projection_org_labels TO %I', role_row.rolname);
        EXECUTE format('GRANT SELECT ON uec.publication_review_release_current TO %I', role_row.rolname);
        EXECUTE format('GRANT SELECT ON uec.source_rights_decisions TO %I', role_row.rolname);
        EXECUTE format('GRANT SELECT ON uec.public_access_restricted TO %I', role_row.rolname);
    END LOOP;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='uec_api_runtime') THEN
        GRANT SELECT ON uec.graph_public_evidence_references_current TO uec_api_runtime;
        GRANT SELECT ON uec.graph_public_organization_labels_current TO uec_api_runtime;
    END IF;
END
$$;
