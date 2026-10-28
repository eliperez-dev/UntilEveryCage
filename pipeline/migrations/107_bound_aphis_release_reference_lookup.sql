-- Keep all 086 reference gates, but allow release/facility filters to reach
-- the candidate rows and probe live review/anchor eligibility by exact keys.
CREATE OR REPLACE VIEW uec.graph_public_evidence_references_current AS
WITH current_builds AS (
    SELECT build.projection_id,build.release_id,release.profile
    FROM uec.graph_public_projection_builds build
    JOIN uec.graph_projection_generation generation ON generation.singleton=true
    JOIN uec.public_suppression_generation suppression ON suppression.singleton=true
    JOIN uec.releases release ON release.release_id=build.release_id
    JOIN uec.public_discovery_read_models model ON model.release_id=build.release_id
    JOIN uec.release_manifests manifest
      ON manifest.release_id=build.release_id
     AND manifest.manifest_sha256=model.manifest_sha256
    LEFT JOIN uec.public_release_history history
      ON history.release_id=release.release_id AND history.profile=release.profile
    WHERE build.active AND build.status='completed'
      AND build.projection_version='graph-release-projection-v3'
      AND build.edge_generation=generation.generation
      AND build.suppression_generation=suppression.generation
      AND build.release_manifest_sha256=manifest.manifest_sha256
      AND release.test_only IS NOT TRUE
      AND (release.status='promoted' OR history.release_id IS NOT NULL)
), eligible_evidence_candidates AS (
    SELECT build.release_id,reference.evidence_ref_id,
           endpoint.public_entity_id,endpoint.source_id AS endpoint_source_id,
           reference.source_id,reference.evidence_type,reference.event_date,
           reference.event_period,reference.observed_at,reference.source_url,
           reference.match_method,
           anchor.source_record_id AS anchor_source_record_id,
           anchor.facility_id AS anchor_facility_id
    FROM uec.graph_public_projection_evidence_refs reference
    JOIN current_builds build
      ON build.projection_id=reference.projection_id
    JOIN uec.graph_public_projection_endpoints endpoint
      ON endpoint.projection_id=reference.projection_id
     AND endpoint.endpoint_id=reference.endpoint_id
     AND endpoint.entity_type='facility'
    JOIN uec.source_records evidence_record
      ON evidence_record.source_record_id=reference.evidence_source_record_id
     AND evidence_record.source_id=reference.source_id
    JOIN LATERAL (
        SELECT checked.* FROM uec.publication_review_release_current checked
        WHERE checked.source_record_id=evidence_record.source_record_id
          AND checked.release_id=build.release_id OFFSET 0
    ) review ON true
    JOIN uec.raw_artifacts artifact
      ON artifact.artifact_id=evidence_record.artifact_id
    JOIN uec.graph_public_evidence_metadata_clearance_current clearance
      ON clearance.source_id=evidence_record.source_id
     AND clearance.profile=build.profile
     AND clearance.release_id=build.release_id
     AND clearance.artifact_id=artifact.artifact_id
     AND clearance.artifact_sha256=artifact.sha256
     AND clearance.scope_version='aphis-public-reference-metadata-v1'
     AND clearance.approved_fields=ARRAY[
         'source_id','evidence_type','event_date','event_period','observed_at','source_url','match_method'
     ]::text[]
    JOIN uec.graph_public_projection_anchors anchor
      ON anchor.projection_id=reference.projection_id
     AND anchor.endpoint_id=endpoint.endpoint_id
    WHERE review.publication_eligible=true
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
      )
      AND NOT EXISTS (
          SELECT 1 FROM uec.observations observation
          JOIN uec.release_members member ON member.observation_id=observation.observation_id
          WHERE member.release_id=build.release_id
            AND observation.source_record_id=evidence_record.source_record_id
      )
)
SELECT candidate.release_id,candidate.evidence_ref_id,candidate.public_entity_id,
       candidate.endpoint_source_id,candidate.source_id,candidate.evidence_type,
       candidate.event_date,candidate.event_period,candidate.observed_at,
       candidate.source_url,candidate.match_method
FROM eligible_evidence_candidates candidate
WHERE EXISTS (
    SELECT live.source_record_id FROM uec.graph_public_live_facility_anchors_current live
    WHERE live.release_id=candidate.release_id
      AND live.source_record_id=candidate.anchor_source_record_id
      AND live.facility_id=candidate.anchor_facility_id OFFSET 0
);

COMMENT ON VIEW uec.graph_public_evidence_references_current IS
    'Current release, live membership, suppression, and source-record gates for safe typed APHIS evidence references.';
