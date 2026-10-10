import { describe, expect, it, vi } from 'vitest';
import { TestReleaseDetailRepository } from '../../src/api/TestReleaseDetailRepository';

const id = '550e8400-e29b-41d4-a716-446655440000';
const meta = { api_version: 'dev-test-v1', private_preview: true, candidate_only: true, test_only: false, environment: 'private-candidate-preview', release_status: 'candidate', release_id: 'candidate-1', profile: 'official', coverage_scope: 'candidate_release_private_preview', count_semantics: 'One configured candidate record', preview_label: 'Configured candidate correction', result_count: 1 };
const row = { facility_id: id, canonical_name: 'Candidate facility', city: 'North Coast', country_code: 'DK', category: 'fish_processing', publication_profile: 'official', factual_review_status: 'reviewed', privacy_screening_status: 'passed', project_approval: 'approved', publication_warning: null, display_precision: 'source_reported', latitude: 55, longitude: 10, provenance_source_id: 'us.fsis', provenance_source_name: 'FSIS', provenance_source_url: 'https://example.test/source', provenance_retrieved_at: '2026-01-01T00:00:00Z', release_id: 'candidate-1', release_ruleset_version: null, alternate_names: ['Former name'], species_slaughtered: { cattle: true }, processing_activities: { processing: true }, source_volume_categories: [{ code: 'large', provenance: { source_field: 'volume', method: 'native' } }], establishment_number: 'E-1' };

describe('configured candidate detail', () => {
  it('accepts the candidate detail core plus only allowlisted source facts', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ data: row, meta }), { status: 200 }));
    const result = await new TestReleaseDetailRepository(fetcher).detail(id);
    expect(result).toMatchObject({ id, name: 'Candidate facility', sourceId: 'us.fsis', sourceFacts: { alternateNames: ['Former name'], establishmentNumber: 'E-1' } });
  });

  it('rejects a detail whose release identity differs from its candidate envelope', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ data: { ...row, release_id: 'another-candidate' }, meta }), { status: 200 }));
    await expect(new TestReleaseDetailRepository(fetcher).detail(id)).rejects.toThrow('rejected safely');
  });

  it('rejects a legacy test-only envelope', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ data: row, meta: { ...meta, candidate_only: false, test_only: true } }), { status: 200 }));
    await expect(new TestReleaseDetailRepository(fetcher).detail(id)).rejects.toThrow('rejected safely');
  });
});
