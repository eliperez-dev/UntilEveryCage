import { describe, expect, it, vi } from 'vitest';
import { PublicGraphRepository, serializeGraphQuery } from '../../src/api/PublicGraphRepository';

const body = { api_version: 'v2-graph-v1', data: [], meta: { profile: 'official', release_id: 'release-1', ruleset_version: 'graph-rules-v1', limit: 100, page_max: 100, next_cursor: null, public_projection: true } };

describe('PublicGraphRepository', () => {
  it('serializes bounded graph filters without dropping false values', () => {
    expect(serializeGraphQuery('official', { confidence_band: 'medium', include_conflicting: false, limit: 100 })).toBe('profile=official&confidence_band=medium&include_conflicting=false&limit=100');
  });
  it('accepts a release-scoped empty public page', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status: 200 }));
    await expect(new PublicGraphRepository(fetcher).connections()).resolves.toMatchObject({ releaseId: 'release-1', nextCursor: null, data: [] });
    expect(fetcher).toHaveBeenCalledWith('/api/v2/graph/connections?profile=official', expect.any(Object));
  });
  it('pins neighborhood queries to the requested public release', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status: 200 }));
    await new PublicGraphRepository(fetcher).neighborhood('550e8400-e29b-41d4-a716-446655440000', 'official', { release_id: 'release-1' });
    expect(String(fetcher.mock.calls[0]?.[0])).toContain('release_id=release-1');
  });
  it('rejects a graph page returned from a different release', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ ...body, meta: { ...body.meta, release_id: 'release-2' } }), { status: 200 }));
    await expect(new PublicGraphRepository(fetcher).neighborhood('550e8400-e29b-41d4-a716-446655440000', 'official', { release_id: 'release-1' })).rejects.toMatchObject({ kind: 'invalid-contract' });
  });
  it('rejects malformed graph responses and invalid entity IDs', async () => {
    await expect(new PublicGraphRepository(vi.fn().mockResolvedValue(new Response(JSON.stringify({ data: [] }), { status: 200 }))).connections()).rejects.toMatchObject({ kind: 'invalid-contract' });
    await expect(new PublicGraphRepository().neighborhood('not-a-uuid')).rejects.toMatchObject({ kind: 'invalid-contract' });
  });
});
