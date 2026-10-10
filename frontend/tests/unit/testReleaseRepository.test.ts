import { describe, expect, it, vi } from 'vitest';
import { TestReleaseRepository } from '../../src/api/TestReleaseRepository';

const row = { facility_id: '550e8400-e29b-41d4-a716-446655440000', canonical_name: 'Candidate facility', city: 'North Coast', country_code: 'DK', category: 'dairy', source_type: 'official', publication_profile: 'official', factual_review_status: 'reviewed', privacy_screening_status: 'passed', project_approval: 'pending', reviewer_role: null, publication_warning: null, display_precision: 'city', latitude: 55, longitude: 10, first_observed_at: null, last_observed_at: '2026-01-01T00:00:00Z', observation_count: 1, lifecycle_status: 'active_observed', provenance_source_id: 'source-1', provenance_source: null, provenance_source_name: 'Candidate source', provenance_source_url: 'https://example.test/source', provenance_retrieved_at: '2026-01-01T00:00:00Z', source_rights_status: 'unknown', release_id: 'candidate-1', release_ruleset_version: 'rules-1' };
const envelope = { data: [row], meta: { api_version: 'dev-test-v1', private_preview: true, candidate_only: true, test_only: false, release_id: 'candidate-1', snapshot_id: 'a'.repeat(64), preview_label: 'Configured candidate correction', result_count: 1, total_count: 313, next_cursor: '550e8400-e29b-41d4-a716-446655440001' } };

describe('configured candidate list', () => {
  it('uses only configured candidate metadata and carries the filtered total plus cursor', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify(envelope), { status: 200 }));
    const page = await new TestReleaseRepository(fetcher).list({ q: 'north facility', countryCode: 'dk', category: 'dairy', cursor: '550e8400-e29b-41d4-a716-446655440002', limit: 500 });
    expect(fetcher).toHaveBeenCalledWith('/api/dev/preview/test-release/locations?profile=official&limit=500&q=north+facility&country_code=DK&category=dairy&cursor=550e8400-e29b-41d4-a716-446655440002', expect.objectContaining({ credentials: 'same-origin', cache: 'no-store' }));
    expect(page).toMatchObject({ totalCount: 313, nextCursor: envelope.meta.next_cursor, previewLabel: envelope.meta.preview_label });
  });

  it('rejects legacy test-only metadata rather than silently treating it as the candidate', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ ...envelope, meta: { ...envelope.meta, candidate_only: false, test_only: true } }), { status: 200 }));
    await expect(new TestReleaseRepository(fetcher).list()).rejects.toThrow('rejected safely');
  });

  it('accepts only candidate-scoped discovery facets', async () => {
    const facets = { data: null, meta: { api_version: 'dev-test-v1', private_preview: true, candidate_only: true, test_only: false, release_id: 'candidate-1', preview_label: 'Configured candidate correction', result_count: 2 }, dimensions: { country_code: [{ value: 'DK', count: 1 }], category: [{ value: 'dairy', count: 1 }], display_precision: [], source_type: [] } };
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify(facets), { status: 200 }));
    await expect(new TestReleaseRepository(fetcher).facets()).resolves.toEqual({ countries: facets.dimensions.country_code, categories: facets.dimensions.category });
    expect(fetcher).toHaveBeenCalledWith('/api/dev/preview/test-release/discovery/facets', expect.objectContaining({ credentials: 'same-origin', cache: 'no-store' }));
  });
});
