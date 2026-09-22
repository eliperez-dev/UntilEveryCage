import type { PublicGraphConnection, PublicGraphEntity } from '../api/publicGraphSchema';

export const publicGraphEntities: readonly PublicGraphEntity[] = [
  { entity_id: '00000000-0000-4000-8000-000000000001', entity_type: 'facility', display_name: 'Exact mapped facility', country_code: 'DK' },
  { entity_id: '00000000-0000-4000-8000-000000000002', entity_type: 'facility', display_name: 'Approximate city facility', country_code: 'IT' },
  { entity_id: '00000000-0000-4000-8000-000000000003', entity_type: 'organization', display_name: 'Example operator', country_code: 'FR' },
];

const endpoint = (entity_id: string | null, entity_type: 'facility' | 'organization', source_id: string, source_identifier: string) => ({ entity_id, entity_type, source_id, identifier_type: 'source_record', source_identifier });
const base = { relationship_type: 'operator', match_method: 'shared_identifier_plus_name', signals: { identifier: 1, name: 0.5 }, contradictions: [], provenance: { source_ids: ['dk.example', 'it.example'], observed_at: '2026-01-01T00:00:00Z', release_id: 'release-example' }, source_references: [{ source_id: 'dk.example' }, { source_id: 'it.example' }], observed_at: '2026-01-01T00:00:00Z', computed_at: '2026-01-02T00:00:00Z', ruleset: 'graph-rules-v1', conflicting: false, publication_warning: 'Confidence is a deterministic ruleset estimate, not a measured probability.', disclaimer: 'Confidence is a deterministic ruleset estimate, not a measured probability.' };
const [facilityExact, facilityApprox, operator] = publicGraphEntities;
if (!facilityExact || !facilityApprox || !operator) throw new Error('public graph fixture is incomplete');

export const publicGraphConnections: readonly PublicGraphConnection[] = [
  { ...base, connection_edge_id: '00000000-0000-4000-8000-000000000101', from: endpoint(facilityExact.entity_id, 'facility', 'dk.example', 'DK-001'), to: endpoint(operator.entity_id, 'organization', 'fr.example', 'FR-001'), connection_type: 'exact', confidence: 1, confidence_band: 'exact' },
  { ...base, connection_edge_id: '00000000-0000-4000-8000-000000000102', from: endpoint(facilityApprox.entity_id, 'facility', 'it.example', 'IT-001'), to: endpoint(operator.entity_id, 'organization', 'fr.example', 'FR-002'), connection_type: 'inferred', confidence: 0.82, confidence_band: 'high' },
  { ...base, connection_edge_id: '00000000-0000-4000-8000-000000000103', from: endpoint(facilityApprox.entity_id, 'facility', 'it.example', 'IT-002'), to: endpoint(operator.entity_id, 'organization', 'fr.example', 'FR-003'), connection_type: 'inferred', confidence: 0.61, confidence_band: 'medium' },
  { ...base, connection_edge_id: '00000000-0000-4000-8000-000000000104', from: endpoint(facilityExact.entity_id, 'facility', 'dk.example', 'DK-004'), to: endpoint(operator.entity_id, 'organization', 'fr.example', 'FR-004'), connection_type: 'inferred', confidence: 0.31, confidence_band: 'low', conflicting: true },
];
