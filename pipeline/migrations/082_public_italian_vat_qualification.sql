-- Placeholder or malformed Italian VAT-shaped identifiers are not public
-- business identifiers. This does not mutate source identifiers or edges;
-- it only gates new/public organization qualification.
CREATE FUNCTION uec.is_valid_italian_vat_identifier(
    source_id TEXT, identifier_type TEXT, source_identifier TEXT
) RETURNS BOOLEAN
LANGUAGE sql IMMUTABLE PARALLEL SAFE
SET search_path=pg_catalog,uec AS $$
    WITH normalized AS (
        SELECT regexp_replace(
                 regexp_replace(upper(coalesce(source_identifier,'')), '[[:space:]]', '', 'g'),
                 '^IT', ''
               ) AS vat
    )
    SELECT CASE
      WHEN lower(coalesce(source_id,'')) LIKE 'it.%'
       AND lower(coalesce(identifier_type,'')) IN (
           'italian_vat','it.tax-authority.vat','vat','vat_number','p_iva'
       )
      THEN vat ~ '^[0-9]{11}$'
       AND vat <> repeat(substr(vat,1,1),11)
      ELSE true
    END
    FROM normalized
$$;
REVOKE ALL ON FUNCTION uec.is_valid_italian_vat_identifier(TEXT,TEXT,TEXT) FROM PUBLIC;
COMMENT ON FUNCTION uec.is_valid_italian_vat_identifier(TEXT,TEXT,TEXT) IS
    'Public qualification guard only: Italian VAT types are whitespace/optional-IT normalized and must be 11 digits, not a repeated-digit placeholder. Does not alter private IDs or edges.';

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
  AND review.publication_eligible=true
  AND review.privacy_screening_status='passed'
  AND review.factual_review_status<>'rejected'
  AND review.maintainer_approval='approved'
  AND uec.is_valid_italian_vat_identifier(
      endpoint.source_id,endpoint.identifier_type,endpoint.source_identifier
  )
  AND NOT EXISTS (
      SELECT 1 FROM uec.public_access_restricted restricted
      WHERE restricted.source_record_id=label.label_source_record_id
  )
  AND NOT EXISTS (
      SELECT 1 FROM uec.public_access_restricted restricted
      WHERE restricted.source_record_id=anchor.source_record_id
  );

COMMENT ON VIEW uec.graph_public_organization_endpoints_current IS
    'Release-safe source-backed business endpoints; excludes malformed and repeated-digit Italian VAT identifiers from public qualification.';

DO $$
DECLARE role_row RECORD;
BEGIN
    FOR role_row IN SELECT rolname FROM pg_roles WHERE left(rolname,17)='uec_graph_writer_' LOOP
        EXECUTE format(
            'GRANT EXECUTE ON FUNCTION uec.is_valid_italian_vat_identifier(text,text,text) TO %I',
            role_row.rolname
        );
    END LOOP;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='uec_api_runtime') THEN
        GRANT EXECUTE ON FUNCTION uec.is_valid_italian_vat_identifier(TEXT,TEXT,TEXT) TO uec_api_runtime;
    END IF;
END
$$;
