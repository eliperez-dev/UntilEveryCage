-- Manifest-bound public discovery read model.
--
-- This is a rebuildable performance component, not an authority for
-- publication.  It contains only rows that passed the public projection at
-- build time and every read still re-checks the current release, review,
-- profile, and suppression gates below.  A missing or stale component is
-- deliberately an empty result and the API treats that state as unavailable.
CREATE TABLE uec.public_discovery_read_models (
    release_id TEXT PRIMARY KEY REFERENCES uec.releases(release_id),
    manifest_sha256 CHAR(64) NOT NULL CHECK (manifest_sha256 ~ '^[0-9a-f]{64}$'),
    content_sha256 CHAR(64) NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
    row_count INTEGER NOT NULL CHECK (row_count >= 0),
    built_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE uec.public_discovery_read_model_rows (
    release_id TEXT NOT NULL REFERENCES uec.releases(release_id),
    facility_id UUID NOT NULL REFERENCES uec.facilities(facility_id),
    observation_id UUID NOT NULL REFERENCES uec.observations(observation_id),
    source_record_id UUID NOT NULL REFERENCES uec.source_records(source_record_id),
    canonical_name TEXT,
    country_code CHAR(2) NOT NULL,
    postal_code TEXT,
    city TEXT,
    display_location GEOGRAPHY(Point, 4326),
    display_precision TEXT NOT NULL,
    display_label TEXT NOT NULL,
    geocoding_status TEXT,
    geocoder_provider TEXT,
    geocoded_at TIMESTAMPTZ,
    classification_category TEXT NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    first_observed_at TIMESTAMPTZ NOT NULL,
    provenance_origin_type TEXT NOT NULL,
    provenance_source_id TEXT NOT NULL,
    provenance_source_name TEXT NOT NULL,
    provenance_source_url TEXT NOT NULL,
    provenance_retrieved_at TIMESTAMPTZ NOT NULL,
    source_rights_status TEXT NOT NULL,
    PRIMARY KEY (release_id, facility_id, observation_id)
);

CREATE INDEX public_discovery_read_model_order_idx
    ON uec.public_discovery_read_model_rows (release_id, facility_id, observation_id);
CREATE INDEX public_discovery_read_model_country_idx
    ON uec.public_discovery_read_model_rows (release_id, country_code, facility_id);
CREATE INDEX public_discovery_read_model_category_idx
    ON uec.public_discovery_read_model_rows (release_id, classification_category, facility_id);
CREATE INDEX public_discovery_read_model_source_type_idx
    ON uec.public_discovery_read_model_rows (release_id, provenance_origin_type, facility_id);
CREATE INDEX public_discovery_read_model_location_gix
    ON uec.public_discovery_read_model_rows USING GIST (display_location);

CREATE TRIGGER public_discovery_read_models_append_only
    BEFORE UPDATE OR DELETE ON uec.public_discovery_read_models
    FOR EACH ROW EXECUTE FUNCTION uec.reject_evidence_mutation();
CREATE TRIGGER public_discovery_read_model_rows_append_only
    BEFORE UPDATE OR DELETE ON uec.public_discovery_read_model_rows
    FOR EACH ROW EXECUTE FUNCTION uec.reject_evidence_mutation();

-- Live safety gates are intentionally in a view rather than frozen in the
-- component.  Aggregates are calculated after current suppression/review so
-- a newly restricted observation disappears from both the row and its count.
CREATE OR REPLACE VIEW uec.map_facilities_public_discovery_read_model AS
WITH eligible AS (
    SELECT model.*,
           release.ruleset_version AS release_ruleset_version,
           release.created_at AS release_created_at,
           review.factual_review_status,
           review.privacy_screening_status,
           review.maintainer_approval,
           review.reviewer_role
    FROM uec.public_discovery_read_model_rows model
    JOIN uec.public_discovery_read_models metadata
      ON metadata.release_id = model.release_id
    JOIN uec.releases release
      ON release.release_id = model.release_id
     AND release.profile IS NOT NULL
    JOIN uec.release_manifests manifest
      ON manifest.release_id = model.release_id
     AND manifest.manifest_sha256 = metadata.manifest_sha256
    -- This lateral form is equivalent to publication_review_release_current
    -- for one source/release, but lets the indexed source-record lookup avoid
    -- materializing the complete append-only review view for every request.
    JOIN LATERAL (
        SELECT review.factual_review_status,
               review.privacy_screening_status,
               review.maintainer_approval,
               review.reviewer_role,
               review.publication_eligible
        FROM uec.publication_review_events review
        JOIN uec.publication_review_release_scopes scope
          ON scope.publication_review_event_id = review.publication_review_event_id
         AND scope.release_id = model.release_id
        WHERE review.source_record_id = model.source_record_id
        ORDER BY review.reviewed_at DESC, review.publication_review_event_id DESC
        LIMIT 1
    ) review ON true
    WHERE release.status = 'promoted'
      AND release.test_only IS NOT TRUE
      AND review.publication_eligible = true
      AND review.privacy_screening_status = 'passed'
      AND review.factual_review_status <> 'rejected'
      AND (
          review.maintainer_approval = 'approved'
          OR (release.profile = 'community'
              AND model.provenance_origin_type = 'user_submitted'
              AND review.factual_review_status = 'unreviewed'
              AND review.maintainer_approval = 'pending')
      )
      -- Keep both current append-only restriction sources live, but correlate
      -- them to the candidate record so a large model does not force a full
      -- public_access_restricted UNION expansion on every read.
      AND NOT EXISTS (
          SELECT 1
          FROM uec.record_access_current access
          WHERE access.source_record_id = model.source_record_id
            AND access.action = 'public_access_revoked'
      )
      AND NOT EXISTS (
          SELECT 1
          FROM uec.suppression_case_current current_case
          JOIN uec.suppression_cases case_record
            ON case_record.case_id = current_case.case_id
          JOIN uec.suppression_references ref
            ON ref.case_id = case_record.case_id
          JOIN uec.source_records record ON (
              (ref.facility_id IS NOT NULL AND (
                  EXISTS (SELECT 1 FROM uec.facility_source_links link
                          WHERE link.facility_id = ref.facility_id
                            AND link.source_record_id = record.source_record_id)
                  OR EXISTS (SELECT 1 FROM uec.observations observation
                             WHERE observation.facility_id = ref.facility_id
                               AND observation.source_record_id = record.source_record_id)
              ))
              OR (ref.source_id = record.source_id
                  AND ref.source_record_key = record.source_record_key)
          )
          WHERE current_case.event_type = 'suppressed'
            AND case_record.status IN ('active', 'review', 'closed', 'expired')
            AND record.source_record_id = model.source_record_id
      )
)
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
       COALESCE(lifecycle.status, 'status_unknown') AS lifecycle_status,
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
       eligible.reviewer_role
FROM eligible
LEFT JOIN uec.facility_lifecycle_current lifecycle
  ON lifecycle.facility_id = eligible.facility_id
WINDOW facility_history AS (PARTITION BY eligible.release_id, eligible.facility_id);

COMMENT ON VIEW uec.map_facilities_public_discovery_read_model IS
    'Manifest-bound public discovery component with live publication_review_release_current-equivalent review, profile, suppression, and lifecycle gates; missing or stale metadata yields no rows.';
