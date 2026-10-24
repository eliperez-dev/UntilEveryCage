-- Factor the public map's exact live eligibility predicate once. The map keeps
-- its established columns, window aggregates, geometry, and lifecycle fields;
-- graph consumers can probe the canonical rows by indexed release/record keys
-- without repeatedly expanding display-history windows.
-- Keep the one canonical restriction selector, but resolve suppression
-- references through their indexed keys instead of an OR join over every
-- source record. UNION preserves the original full-row deduplication.
CREATE OR REPLACE VIEW uec.public_access_restricted AS
SELECT source_record_id,reason_category,policy_version,occurred_at
FROM uec.record_access_current
WHERE action='public_access_revoked'
UNION
SELECT record.source_record_id,current_case.reason_category,
       current_case.policy_version,current_case.occurred_at
FROM uec.suppression_case_current current_case
JOIN uec.suppression_cases case_record ON case_record.case_id=current_case.case_id
JOIN uec.suppression_references ref ON ref.case_id=case_record.case_id
JOIN uec.facility_source_links link
  ON ref.facility_id IS NOT NULL AND link.facility_id=ref.facility_id
JOIN uec.source_records record ON record.source_record_id=link.source_record_id
WHERE current_case.event_type='suppressed'
  AND case_record.status IN ('active','review','closed','expired')
UNION
SELECT record.source_record_id,current_case.reason_category,
       current_case.policy_version,current_case.occurred_at
FROM uec.suppression_case_current current_case
JOIN uec.suppression_cases case_record ON case_record.case_id=current_case.case_id
JOIN uec.suppression_references ref ON ref.case_id=case_record.case_id
JOIN uec.observations observation
  ON ref.facility_id IS NOT NULL AND observation.facility_id=ref.facility_id
JOIN uec.source_records record ON record.source_record_id=observation.source_record_id
WHERE current_case.event_type='suppressed'
  AND case_record.status IN ('active','review','closed','expired')
UNION
SELECT record.source_record_id,current_case.reason_category,
       current_case.policy_version,current_case.occurred_at
FROM uec.suppression_case_current current_case
JOIN uec.suppression_cases case_record ON case_record.case_id=current_case.case_id
JOIN uec.suppression_references ref ON ref.case_id=case_record.case_id
JOIN uec.source_records record
  ON ref.source_id=record.source_id
 AND ref.source_record_key=record.source_record_key
WHERE current_case.event_type='suppressed'
  AND case_record.status IN ('active','review','closed','expired');

CREATE OR REPLACE VIEW uec.public_discovery_live_eligible_rows AS
SELECT model.*,
       release.ruleset_version AS release_ruleset_version,
       release.created_at AS release_created_at,
       review.factual_review_status,
       review.privacy_screening_status,
       review.maintainer_approval,
       review.reviewer_role
FROM uec.public_discovery_read_model_rows model
JOIN uec.public_discovery_read_models metadata
  ON metadata.release_id=model.release_id
JOIN uec.releases release
  ON release.release_id=model.release_id AND release.profile IS NOT NULL
JOIN uec.release_manifests manifest
  ON manifest.release_id=model.release_id
 AND manifest.manifest_sha256=metadata.manifest_sha256
JOIN uec.source_records record ON record.source_record_id=model.source_record_id
JOIN LATERAL (
    SELECT decision.factual_review_status, decision.privacy_screening_status,
           decision.maintainer_approval, decision.reviewer_role,
           decision.publication_eligible
    FROM (
        SELECT event.factual_review_status, event.privacy_screening_status,
               event.maintainer_approval, event.reviewer_role,
               event.publication_eligible, event.reviewed_at AS decided_at,
               event.publication_review_event_id::text AS tie_break
        FROM uec.publication_review_events event
        JOIN uec.publication_review_release_scopes event_scope
          ON event_scope.publication_review_event_id=event.publication_review_event_id
         AND event_scope.release_id=model.release_id
        WHERE event.source_record_id=model.source_record_id
          AND release.summary->>'candidate_only' IS DISTINCT FROM 'true'
        UNION ALL
        SELECT cohort.factual_review_status, cohort.privacy_screening_status,
               cohort.maintainer_approval, cohort.reviewer_role,
               cohort.publication_eligible, cohort.reviewed_at AS decided_at,
               cohort.document_sha256 AS tie_break
        FROM uec.release_cohort_review_current cohort
        WHERE cohort.release_id=model.release_id
          AND cohort.source_id=record.source_id
          AND cohort.artifact_id=record.artifact_id
          AND release.summary->>'candidate_only'='true'
    ) decision
    ORDER BY decision.decided_at DESC, decision.tie_break DESC
    LIMIT 1
) review ON true
WHERE release.status='promoted'
  AND release.test_only IS NOT TRUE
  AND review.publication_eligible=true
  AND review.privacy_screening_status='passed'
  AND review.factual_review_status<>'rejected'
  AND (
      review.maintainer_approval='approved'
      OR (release.profile='community'
          AND model.provenance_origin_type='user_submitted'
          AND review.factual_review_status='unreviewed'
          AND review.maintainer_approval='pending')
  )
  AND NOT EXISTS (
      SELECT 1 FROM uec.public_access_restricted restricted
      WHERE restricted.source_record_id=model.source_record_id
  );

CREATE OR REPLACE VIEW uec.map_facilities_public_discovery_read_model AS
SELECT eligible.release_id,
       'promoted'::text AS release_status,
       true AS release_visible,
       eligible.observation_id,
       eligible.facility_id,
       eligible.source_record_id,
       eligible.canonical_name,
       eligible.country_code,
       NULL::text AS street_address,
       eligible.postal_code,
       eligible.city,
       eligible.display_location,
       eligible.display_precision,
       eligible.display_label,
       eligible.geocoding_status,
       eligible.geocoder_provider,
       eligible.geocoded_at,
       eligible.classification_category,
       min(eligible.first_observed_at) OVER facility_history AS first_observed_at,
       max(eligible.observed_at) OVER facility_history AS last_observed_at,
       (count(*) OVER facility_history)::int AS observation_count,
       COALESCE(lifecycle.status,'status_unknown') AS lifecycle_status,
       lifecycle.effective_at AS lifecycle_effective_at,
       lifecycle.source_record_id AS lifecycle_source_record_id,
       eligible.release_ruleset_version,
       eligible.release_created_at,
       eligible.provenance_origin_type,
       eligible.provenance_source_id,
       eligible.provenance_source_name,
       eligible.provenance_source_url,
       eligible.provenance_retrieved_at,
       eligible.source_rights_status,
       eligible.factual_review_status,
       eligible.privacy_screening_status,
       eligible.maintainer_approval,
       eligible.reviewer_role,
       eligible.geometry_provenance
FROM uec.public_discovery_live_eligible_rows eligible
LEFT JOIN uec.facility_lifecycle_current lifecycle
  ON lifecycle.facility_id=eligible.facility_id
WINDOW facility_history AS (PARTITION BY eligible.release_id,eligible.facility_id);

CREATE OR REPLACE VIEW uec.graph_public_live_facility_anchors_current AS
SELECT release_id,source_record_id,facility_id
FROM uec.public_discovery_live_eligible_rows;

COMMENT ON VIEW uec.public_discovery_live_eligible_rows IS
    'Canonical current public-map eligibility rows before windowed display aggregates; consumed unchanged by the map and graph live-anchor lookup.';
COMMENT ON VIEW uec.graph_public_live_facility_anchors_current IS
    'Private graph-only keys projected from the canonical current public-map eligibility rows.';

-- Keep the source-backed organization review/rights selector in one private
-- view. Connection gating can join this exact selector to its statement-local
-- materialized live-anchor set instead of re-expanding the map eligibility
-- view once per organization endpoint.
CREATE OR REPLACE VIEW uec.graph_public_organization_label_candidates_current AS
SELECT DISTINCT build.release_id,endpoint.endpoint_id,
       endpoint.public_entity_id AS organization_id,
       anchor.source_record_id,anchor.facility_id
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
JOIN LATERAL (
    SELECT review.*
    FROM uec.publication_review_release_current review
    WHERE review.source_record_id=label_record.source_record_id
      AND review.release_id=build.release_id
    LIMIT 1 OFFSET 0
) review ON true
JOIN LATERAL (
    SELECT decision.*
    FROM uec.source_rights_decisions decision
    WHERE decision.source_id=label_record.source_id
      AND decision.profile=release.profile
      AND decision.release_id=build.release_id
      AND decision.artifact_id=artifact.artifact_id
    ORDER BY decision.decided_at DESC,decision.source_rights_decision_id DESC
    LIMIT 1 OFFSET 0
) rights ON rights.artifact_sha256=artifact.sha256
       AND rights.redistribution_status='cleared'
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

-- Evaluate the canonical current-map keys once per statement. Support,
-- endpoint, and source-backed organization eligibility reuse these exact
-- live rows and remain subject to the same release and rights gates.
CREATE OR REPLACE VIEW uec.graph_public_connections_current AS
WITH active_releases AS MATERIALIZED (
    SELECT DISTINCT release_id FROM uec.graph_public_projection_builds
    WHERE active AND status='completed' AND projection_version='graph-release-projection-v3'
), live_anchors AS MATERIALIZED (
    SELECT DISTINCT eligible.release_id,eligible.source_record_id,eligible.facility_id
    FROM uec.public_discovery_live_eligible_rows eligible
    JOIN active_releases active USING(release_id)
), eligible_supports AS MATERIALIZED (
    SELECT DISTINCT support.projection_id,support.connection_edge_id,support.source_record_id
    FROM uec.graph_public_projection_edge_supports support
    JOIN uec.graph_public_projection_builds support_build
      ON support_build.projection_id=support.projection_id
     AND support_build.active AND support_build.status='completed'
     AND support_build.projection_version='graph-release-projection-v3'
    JOIN uec.source_records record
      ON record.source_record_id=support.source_record_id
     AND record.source_id=support.source_id
     AND record.artifact_id=support.artifact_id
    JOIN live_anchors live
      ON live.release_id=support_build.release_id
     AND live.source_record_id=support.source_record_id
), support_status AS MATERIALIZED (
    SELECT support.projection_id,support.connection_edge_id,
           count(*) AS support_count,
           count(eligible.source_record_id) AS eligible_support_count
    FROM uec.graph_public_projection_edge_supports support
    JOIN uec.graph_public_projection_builds support_build
      ON support_build.projection_id=support.projection_id
     AND support_build.active AND support_build.status='completed'
     AND support_build.projection_version='graph-release-projection-v3'
    LEFT JOIN eligible_supports eligible
      ON eligible.projection_id=support.projection_id
     AND eligible.connection_edge_id=support.connection_edge_id
     AND eligible.source_record_id=support.source_record_id
    GROUP BY support.projection_id,support.connection_edge_id
), eligible_endpoints AS MATERIALIZED (
    SELECT DISTINCT anchor.projection_id,anchor.endpoint_id
    FROM uec.graph_public_projection_anchors anchor
    JOIN uec.graph_public_projection_builds anchor_build
      ON anchor_build.projection_id=anchor.projection_id
     AND anchor_build.active AND anchor_build.status='completed'
     AND anchor_build.projection_version='graph-release-projection-v3'
    JOIN live_anchors live
      ON live.release_id=anchor_build.release_id
     AND live.source_record_id=anchor.source_record_id
     AND live.facility_id=anchor.facility_id
), organization_candidates AS MATERIALIZED (
    -- This view contains the full source-backed label/review/rights selector.
    -- Bound its result before joining live anchors so PostgreSQL cannot inline
    -- and re-expand that selector beneath the anchor join for each candidate.
    SELECT candidate.release_id,candidate.endpoint_id,candidate.organization_id,
           candidate.source_record_id,candidate.facility_id
    FROM uec.graph_public_organization_label_candidates_current candidate
    JOIN active_releases active USING(release_id)
), eligible_organizations AS MATERIALIZED (
    SELECT DISTINCT candidate.release_id,candidate.endpoint_id,candidate.organization_id
    FROM organization_candidates candidate
    JOIN live_anchors live
      ON live.release_id=candidate.release_id
     AND live.source_record_id=candidate.source_record_id
     AND live.facility_id=candidate.facility_id
)
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
JOIN uec.public_suppression_generation suppression ON suppression.singleton=true
JOIN uec.releases release ON release.release_id=e.release_id
JOIN uec.public_discovery_read_models model ON model.release_id=e.release_id
JOIN uec.release_manifests manifest
  ON manifest.release_id=e.release_id AND manifest.manifest_sha256=model.manifest_sha256
LEFT JOIN uec.public_release_history history
  ON history.release_id=release.release_id AND history.profile=release.profile
JOIN support_status support
  ON support.projection_id=e.projection_id
 AND support.connection_edge_id=e.connection_edge_id
 AND support.support_count>0
 AND support.support_count=support.eligible_support_count
JOIN eligible_endpoints from_anchor
  ON from_anchor.projection_id=e.projection_id
 AND from_anchor.endpoint_id=e.from_endpoint_id
JOIN eligible_endpoints to_anchor
  ON to_anchor.projection_id=e.projection_id
 AND to_anchor.endpoint_id=e.to_endpoint_id
LEFT JOIN eligible_organizations from_organization
  ON from_organization.release_id=e.release_id
 AND from_organization.endpoint_id=e.from_endpoint_id
 AND from_organization.organization_id=e.from_entity_id
LEFT JOIN eligible_organizations to_organization
  ON to_organization.release_id=e.release_id
 AND to_organization.endpoint_id=e.to_endpoint_id
 AND to_organization.organization_id=e.to_entity_id
WHERE b.active AND b.status='completed'
  AND b.projection_version='graph-release-projection-v3'
  AND b.edge_generation=generation.generation
  AND b.suppression_generation=suppression.generation
  AND b.release_manifest_sha256=manifest.manifest_sha256
  AND release.test_only IS NOT TRUE
  AND (release.status='promoted' OR history.release_id IS NOT NULL)
  AND (e.from_entity_type<>'organization' OR from_organization.endpoint_id IS NOT NULL)
  AND (e.to_entity_type<>'organization' OR to_organization.endpoint_id IS NOT NULL);

-- Public organization anchors reuse the same private source-backed selector
-- and apply current map/release eligibility without duplicating rights logic.
CREATE OR REPLACE VIEW uec.graph_public_organization_endpoints_current AS
SELECT DISTINCT candidate.release_id,candidate.endpoint_id,candidate.organization_id
FROM uec.graph_public_organization_label_candidates_current candidate
JOIN uec.graph_public_live_facility_anchors_current live
  ON live.release_id=candidate.release_id
 AND live.source_record_id=candidate.source_record_id
 AND live.facility_id=candidate.facility_id;

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
  ON review.source_record_id=evidence_record.source_record_id
 AND review.release_id=build.release_id
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
    SELECT 1 FROM uec.graph_public_live_facility_anchors_current live
    WHERE live.release_id=build.release_id
      AND live.source_record_id=anchor.source_record_id
      AND live.facility_id=anchor.facility_id
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
  );

-- Dedicated graph paging indexes avoid forcing a release-wide scan when the
-- API filters by one public entity UUID or traverses the release edge list.
CREATE INDEX IF NOT EXISTS graph_public_projection_edges_release_page_idx
    ON uec.graph_public_projection_edges(release_id,connection_edge_id DESC);
CREATE INDEX IF NOT EXISTS graph_public_projection_edges_release_from_idx
    ON uec.graph_public_projection_edges(release_id,from_entity_id,connection_edge_id DESC);
CREATE INDEX IF NOT EXISTS graph_public_projection_edges_release_to_idx
    ON uec.graph_public_projection_edges(release_id,to_entity_id,connection_edge_id DESC);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='uec_api_runtime') THEN
        GRANT SELECT ON uec.graph_public_connections_current TO uec_api_runtime;
        GRANT SELECT ON uec.graph_public_organization_endpoints_current TO uec_api_runtime;
        GRANT SELECT ON uec.graph_public_evidence_references_current TO uec_api_runtime;
    END IF;
END
$$;
