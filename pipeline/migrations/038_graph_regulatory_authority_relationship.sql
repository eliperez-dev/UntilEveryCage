-- Add the source-backed authority-role edge used by private graph candidates.
-- Authorities remain organizations; this does not create a new canonical entity
-- type and does not grant approval or publication.

ALTER TABLE uec.organization_relationship_observations
    DROP CONSTRAINT organization_relationship_observations_relationship_type_check;

ALTER TABLE uec.organization_relationship_observations
    ADD CONSTRAINT organization_relationship_observations_relationship_type_check
    CHECK (relationship_type IN ('operator', 'owner', 'parent', 'brand', 'supplier', 'customer', 'regulatory_authority_for'));
