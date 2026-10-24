-- Keep the existing v3 evidence and organization publication gates live, but
-- perform canonical current-anchor checks as parameterized existence lookups.
-- Ordinary joins can expand the public map view's release-wide discovery and
-- review windows for a single API entity/reference lookup.
CREATE OR REPLACE VIEW uec.graph_public_organization_endpoints_current AS
SELECT DISTINCT build.release_id,endpoint.endpoint_id,
       endpoint.public_entity_id AS organization_id
FROM uec.graph_public_projection_org_labels label
JOIN uec.graph_public_projection_builds build ON build.projection_id=label.projection_id
JOIN uec.graph_public_projection_endpoints endpoint
  ON endpoint.projection_id=label.projection_id AND endpoint.endpoint_id=label.endpoint_id
 AND endpoint.entity_type='organization'
JOIN uec.graph_projection_generation generation ON generation.singleton=true
JOIN uec.public_suppression_generation suppression ON suppression.singleton=true
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
JOIN LATERAL (
    SELECT 1
      FROM uec.map_facilities_public_discovery_read_model current_anchor
     WHERE current_anchor.release_id=build.release_id
       AND current_anchor.source_record_id=anchor.source_record_id
       AND current_anchor.facility_id=anchor.facility_id
     LIMIT 1
) current_anchor ON true
LEFT JOIN uec.public_release_history history
  ON history.release_id=release.release_id AND history.profile=release.profile
WHERE build.active AND build.status='completed'
  AND build.projection_version='graph-release-projection-v3'
  AND build.edge_generation=generation.generation
  AND build.suppression_generation=suppression.generation
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
JOIN LATERAL (
    SELECT 1
      FROM uec.map_facilities_public_discovery_read_model current_anchor
     WHERE current_anchor.release_id=build.release_id
       AND current_anchor.source_record_id=anchor.source_record_id
       AND current_anchor.facility_id=anchor.facility_id
     LIMIT 1
) current_anchor ON true
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
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='uec_api_runtime') THEN
        GRANT SELECT ON uec.graph_public_evidence_references_current TO uec_api_runtime;
    END IF;
END
$$;
