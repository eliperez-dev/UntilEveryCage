-- Public graph projections are opt-in, release-scoped, privacy-screened, and
-- suppression-aware. Raw/private/reviewed graph rows are never public by view
-- default, even when their source is government-originated.

CREATE OR REPLACE VIEW uec.graph_public_relationships AS
SELECT relationship.relationship_observation_id,
       relationship.release_id,
       relationship.from_organization_id,
       relationship.target_facility_id,
       relationship.target_organization_id,
       relationship.relationship_type,
       relationship.assertion_status,
       relationship.valid_from,
       relationship.valid_to,
       relationship.observed_at,
       relationship.confidence,
       relationship.review_state,
       relationship.source_id,
       relationship.source_record_id
FROM uec.organization_relationship_observations relationship
JOIN uec.releases release ON release.release_id = relationship.release_id
WHERE relationship.publication_status = 'released'
  AND relationship.storage_state = 'released'
  AND relationship.review_state = 'accepted'
  AND relationship.privacy_status = 'passed'
  AND release.status = 'promoted'
  AND NOT EXISTS (
      SELECT 1 FROM uec.public_access_restricted restricted
      WHERE restricted.source_record_id = relationship.source_record_id
  );

CREATE OR REPLACE VIEW uec.graph_public_claims AS
SELECT claim.claim_id,
       claim.release_id,
       claim.facility_id,
       claim.organization_id,
       claim.claim_domain,
       claim.claim_kind,
       claim.value_state,
       claim.claim_value,
       claim.unknown_reason,
       claim.valid_from,
       claim.valid_to,
       claim.observed_at,
       claim.confidence,
       claim.review_state,
       claim.source_id,
       claim.source_record_id
FROM uec.claims claim
JOIN uec.releases release ON release.release_id = claim.release_id
WHERE claim.publication_status = 'released'
  AND claim.storage_state = 'released'
  AND claim.review_state = 'accepted'
  AND claim.privacy_status = 'passed'
  AND release.status = 'promoted'
  AND NOT EXISTS (
      SELECT 1 FROM uec.public_access_restricted restricted
      WHERE restricted.source_record_id = claim.source_record_id
  );

CREATE OR REPLACE VIEW uec.graph_publication_safety AS
SELECT 'relationship'::TEXT AS graph_kind,
       relationship.relationship_observation_id AS graph_id,
       relationship.release_id,
       relationship.publication_status,
       relationship.storage_state,
       relationship.review_state,
       relationship.privacy_status,
       (COALESCE(release.status = 'promoted', false)
        AND relationship.publication_status = 'released'
        AND relationship.storage_state = 'released'
        AND relationship.review_state = 'accepted'
        AND relationship.privacy_status = 'passed'
        AND NOT EXISTS (SELECT 1 FROM uec.public_access_restricted restricted
                        WHERE restricted.source_record_id = relationship.source_record_id)) AS public_eligible
FROM uec.organization_relationship_observations relationship
LEFT JOIN uec.releases release ON release.release_id = relationship.release_id
UNION ALL
SELECT 'claim'::TEXT,
       claim.claim_id,
       claim.release_id,
       claim.publication_status,
       claim.storage_state,
       claim.review_state,
       claim.privacy_status,
       (COALESCE(release.status = 'promoted', false)
        AND claim.publication_status = 'released'
        AND claim.storage_state = 'released'
        AND claim.review_state = 'accepted'
        AND claim.privacy_status = 'passed'
        AND NOT EXISTS (SELECT 1 FROM uec.public_access_restricted restricted
                        WHERE restricted.source_record_id = claim.source_record_id))
FROM uec.claims claim
LEFT JOIN uec.releases release ON release.release_id = claim.release_id;

CREATE INDEX organization_relationship_public_idx
    ON uec.organization_relationship_observations (release_id, publication_status, privacy_status)
    WHERE publication_status = 'released';
CREATE INDEX claims_public_idx
    ON uec.claims (release_id, claim_domain, publication_status, privacy_status)
    WHERE publication_status = 'released';

COMMENT ON VIEW uec.graph_public_relationships IS
    'Only promoted-release relationship observations with accepted review, passed privacy, released storage, and no active source-record suppression.';
COMMENT ON VIEW uec.graph_public_claims IS
    'Only promoted-release claims with accepted review, passed privacy, released storage, and no active source-record suppression.';
COMMENT ON VIEW uec.graph_publication_safety IS
    'Diagnostic projection showing why each graph row is or is not eligible for public output; it never exposes raw/private payloads.';
