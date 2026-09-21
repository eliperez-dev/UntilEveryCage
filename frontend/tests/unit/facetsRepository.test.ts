import { describe, expect, it, vi } from 'vitest';
import { FacetsRepository } from '../../src/api/FacetsRepository';

const body = (overrides: Record<string, unknown> = {}) => ({ api_version: 'v2', meta: { profile: 'official', release_id: 'release-1', ruleset_version: 'rules-1', release_created_at: '2026-01-01T00:00:00Z', coverage_scope: 'selected_promoted_release_public_facilities', count_semantics: 'Counts are eligible public facility projection rows after current suppression; they are not story-wide or animal counts.', filters: { country_code: null, region: null, category: null, source_type: null, display_precision: null, lifecycle_status: null } }, dimensions: { display_precision: [{ value: 'exact', count: 2 }], source_type: [{ value: 'official', count: 2 }], lifecycle_status: [{ value: 'active_observed', count: 2 }] }, ...overrides });

describe('FacetsRepository', () => {
  it('validates and pins profile, release, and ruleset', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify(body())));
    const result = await new FacetsRepository(fetcher).get('official', {}, { releaseId: 'release-1', ruleset: 'rules-1' });
    expect(result.dimensions.display_precision?.[0]?.count).toBe(2);
    expect(fetcher.mock.calls[0]?.[0]).toContain('profile=official');
  });

  it('rejects a facet snapshot from a different release', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify(body({ meta: { ...body().meta, release_id: 'old-release' } }))));
    await expect(new FacetsRepository(fetcher).get('official', {}, { releaseId: 'release-1', ruleset: 'rules-1' })).rejects.toThrow(/different profile or promoted release/);
  });

  it('rejects a facet snapshot from a different requested filter scope', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify(body({ meta: { ...body().meta, filters: { ...body().meta.filters, category: 'slaughter' } } }))));
    await expect(new FacetsRepository(fetcher).get('official', { category: 'dairy' }, { releaseId: 'release-1', ruleset: 'rules-1' })).rejects.toMatchObject({ kind: 'invalid-contract' });
  });

  it('accepts normalized filter metadata from the backend', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify(body({ meta: { ...body().meta, filters: { ...body().meta.filters, region: 'North Coast' } } }))));
    await expect(new FacetsRepository(fetcher).get('official', { region: '  North Coast  ' }, { releaseId: 'release-1', ruleset: 'rules-1' })).resolves.toMatchObject({ releaseId: 'release-1' });
  });

  it('classifies malformed successful JSON as an invalid contract', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response('{not-json'));
    await expect(new FacetsRepository(fetcher).get('official', {}, { releaseId: 'release-1', ruleset: 'rules-1' })).rejects.toMatchObject({ kind: 'invalid-contract' });
  });
});
