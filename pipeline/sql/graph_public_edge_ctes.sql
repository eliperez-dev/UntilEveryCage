record_facility_candidates AS MATERIALIZED (
  SELECT DISTINCT p.source_record_id, p.facility_id
  FROM uec.map_facilities_public_discovery_read_model p
  WHERE p.release_id=$1
),
ambiguous_record_facilities AS MATERIALIZED (
  SELECT source_record_id
  FROM record_facility_candidates
  GROUP BY source_record_id
  HAVING count(*)>1
),
record_facilities AS MATERIALIZED (
  SELECT candidate.source_record_id, candidate.facility_id
  FROM record_facility_candidates candidate
  LEFT JOIN ambiguous_record_facilities ambiguous USING (source_record_id)
  WHERE ambiguous.source_record_id IS NULL
),
release_support_candidates AS MATERIALIZED (
  SELECT DISTINCT record.source_id, record.source_record_id, record.artifact_id,
         record.source_record_id AS canonical_source_record_id
  FROM record_facilities rf
  JOIN uec.source_records record ON record.source_record_id=rf.source_record_id
  UNION
  SELECT DISTINCT binding.source_id, private_record.source_record_id,
         private_record.artifact_id, binding.canonical_source_record_id
  FROM uec.graph_record_release_bindings binding
  JOIN record_facilities rf
    ON rf.source_record_id=binding.canonical_source_record_id
   AND rf.facility_id=binding.facility_id
  JOIN uec.source_records canonical_record
    ON canonical_record.source_record_id=binding.canonical_source_record_id
   AND canonical_record.source_id=binding.source_id
   AND canonical_record.artifact_id=binding.artifact_id
  JOIN uec.source_records private_record
    ON private_record.source_record_id=binding.private_source_record_id
   AND private_record.source_id=binding.source_id
   AND private_record.artifact_id=binding.artifact_id
  WHERE binding.release_id=$1
),
release_support_records AS MATERIALIZED (
  SELECT source_id,source_record_id,artifact_id,
         (array_agg(DISTINCT canonical_source_record_id
                    ORDER BY canonical_source_record_id))[1] AS canonical_source_record_id
  FROM release_support_candidates
  GROUP BY source_id,source_record_id,artifact_id
  HAVING count(DISTINCT canonical_source_record_id)=1
),
edge_support_refs AS MATERIALIZED (
  SELECT edge.connection_edge_id,
         refs.value->>'source_id' AS source_id,
         refs.value->>'source_record_id' AS source_record_id
  FROM uec.graph_connection_edges edge
  CROSS JOIN LATERAL jsonb_array_elements(edge.supporting_source_refs)
    AS refs(value)
  WHERE edge.suppressed=false AND edge.storage_state='private'
    AND edge.publication_status='not_eligible'
),
eligible_edge_supports AS MATERIALIZED (
  SELECT refs.connection_edge_id,
         array_agg(DISTINCT record.canonical_source_record_id
                   ORDER BY record.canonical_source_record_id) AS support_record_ids,
         jsonb_agg(DISTINCT jsonb_build_object(
             'source_record_id', record.canonical_source_record_id,
             'source_id', record.source_id, 'artifact_id', record.artifact_id)) AS support_records
  FROM edge_support_refs refs
  LEFT JOIN release_support_records record
    ON record.source_id=refs.source_id
   AND record.source_record_id::text=refs.source_record_id
  GROUP BY refs.connection_edge_id
  HAVING count(*)=count(record.source_record_id)
),
facility_assertions AS MATERIALIZED (
  SELECT DISTINCT i.source_record_id, i.facility_id
  FROM uec.source_entity_identifiers i
  JOIN record_facilities rf ON rf.source_record_id=i.source_record_id
                           AND rf.facility_id=i.facility_id
  WHERE i.entity_type='facility'
),
endpoint_candidates AS MATERIALIZED (
  SELECT i.source_id, i.identifier_type, i.source_identifier, i.entity_type,
         i.facility_id AS public_entity_id, i.source_record_id,
         rf.facility_id AS anchor_facility_id
  FROM uec.source_entity_identifiers i
  JOIN record_facilities rf ON rf.source_record_id=i.source_record_id
  WHERE i.entity_type='facility' AND i.facility_id=rf.facility_id
  UNION ALL
  SELECT i.source_id, i.identifier_type, i.source_identifier, i.entity_type,
         i.organization_id AS public_entity_id, name_support.canonical_source_record_id AS source_record_id,
         rf.facility_id AS anchor_facility_id
  FROM uec.source_entity_identifiers i
  JOIN uec.graph_source_name_assertions business_name
    ON business_name.source_id=i.source_id
   AND business_name.source_record_id=i.source_record_id
   AND business_name.organization_id=i.organization_id
   AND business_name.identifier_id=i.identifier_id
   AND business_name.assertion_role IN ('legal','business','operator')
   AND lower(regexp_replace(business_name.source_field,'^.*[.]','')) IN (
      'legal_name','business_name','registered_business_name','company_name',
      'organization_name','organisation_name','operator_name','operator_company_name',
      'raison_sociale','ragione_sociale','registered_name'
   )
  JOIN release_support_records name_support
    ON name_support.source_id=i.source_id
   AND name_support.source_record_id=i.source_record_id
  JOIN uec.source_records canonical_record
    ON canonical_record.source_record_id=name_support.canonical_source_record_id
   AND canonical_record.source_id=i.source_id
   AND canonical_record.artifact_id=name_support.artifact_id
  JOIN record_facilities rf ON rf.source_record_id=name_support.canonical_source_record_id
  JOIN facility_assertions asserted_facility
    ON asserted_facility.source_record_id=name_support.canonical_source_record_id
   AND asserted_facility.facility_id=rf.facility_id
  WHERE i.entity_type='organization'
    AND i.identifier_type IN (
      'business_id','business_number','business_registration','business_registration_number',
      'company_number','company_registration_number','company_registry_number',
      'registered_business_id','legal_entity_id','legal_entity_identifier',
      'siren','abn','acn','nzbn','lei',
      'vat','vat_number','italian_vat','p_iva'
    )
    AND i.organization_id IS NOT NULL
    AND uec.is_valid_italian_vat_identifier(
        i.source_id, i.identifier_type, i.source_identifier
    )
),
distinct_endpoint_targets AS MATERIALIZED (
  SELECT DISTINCT source_id, identifier_type, source_identifier, entity_type,
                  public_entity_id
  FROM endpoint_candidates
),
ambiguous_source_endpoints AS MATERIALIZED (
  SELECT source_id, identifier_type, source_identifier, entity_type
  FROM distinct_endpoint_targets
  GROUP BY source_id, identifier_type, source_identifier, entity_type
  HAVING count(*)>1
),
eligible_source_endpoints AS MATERIALIZED (
  SELECT target.source_id, target.identifier_type, target.source_identifier,
         target.entity_type, target.public_entity_id,
         jsonb_agg(DISTINCT jsonb_build_object(
             'source_record_id', candidate.source_record_id,
             'facility_id', candidate.anchor_facility_id)) AS anchors
  FROM distinct_endpoint_targets target
  JOIN endpoint_candidates candidate
    ON candidate.source_id=target.source_id
   AND candidate.identifier_type=target.identifier_type
   AND candidate.source_identifier=target.source_identifier
   AND candidate.entity_type=target.entity_type
   AND candidate.public_entity_id=target.public_entity_id
  LEFT JOIN ambiguous_source_endpoints ambiguous
    ON ambiguous.source_id=target.source_id
   AND ambiguous.identifier_type=target.identifier_type
   AND ambiguous.source_identifier=target.source_identifier
   AND ambiguous.entity_type=target.entity_type
  WHERE ambiguous.source_id IS NULL
  GROUP BY target.source_id, target.identifier_type, target.source_identifier,
           target.entity_type, target.public_entity_id
),
edges AS (
SELECT e.connection_edge_id,
       fi.public_entity_id AS from_entity_id,
       e.from_entity_type, e.from_source_id, e.from_identifier_type,
       e.from_source_identifier,
       ti.public_entity_id AS to_entity_id,
       e.to_entity_type, e.to_source_id, e.to_identifier_type,
       e.to_source_identifier, e.relationship_type, e.connection_type,
       e.confidence::double precision,
       CASE WHEN e.confidence_band = 'probable' THEN 'high'
            WHEN e.confidence_band = 'possible' THEN 'medium'
            ELSE e.confidence_band END AS public_confidence_band,
       e.signal_explanation::text, e.match_method,
       e.observed_at, e.computed_at, e.ruleset_version, e.conflicting,
       support.support_record_ids, support.support_records
FROM uec.graph_connection_edges e
JOIN eligible_source_endpoints fi
  ON fi.source_id=e.from_source_id AND fi.identifier_type=e.from_identifier_type
 AND fi.source_identifier=e.from_source_identifier AND fi.entity_type=e.from_entity_type
JOIN eligible_source_endpoints ti
  ON ti.source_id=e.to_source_id AND ti.identifier_type=e.to_identifier_type
 AND ti.source_identifier=e.to_source_identifier AND ti.entity_type=e.to_entity_type
JOIN eligible_edge_supports support
  ON support.connection_edge_id=e.connection_edge_id
WHERE e.suppressed = false
  AND e.storage_state = 'private'
  AND e.publication_status = 'not_eligible'
  AND (
    fi.entity_type = 'facility'
    OR (fi.entity_type = 'organization' AND (
          e.connection_type='inferred'
          OR (e.connection_type='exact' AND e.relationship_type='operator')
       ))
  )
  AND (
    ti.entity_type = 'facility'
    OR (ti.entity_type = 'organization' AND (
          e.connection_type='inferred'
          OR (e.connection_type='exact' AND e.relationship_type='operator')
       ))
  ))
