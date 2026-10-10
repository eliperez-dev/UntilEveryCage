import { describe, expect, it, vi } from 'vitest';
import { parseRealPreviewMapFeed, RealPreviewMapFeedError } from '../../src/api/RealPreviewMapFeedRepository';
import { createTestReleaseMapFeedRepository, filterTestReleaseMapCollection } from '../../src/api/TestReleaseMapFeedRepository';

const envelope = {
  api_version: 'dev-test-v1',
  data: { points: [{ key: '550e8400-e29b-41d4-a716-446655440000', source_id: 'us.fsis', country_code: 'US', activity_keys: ['us.fsis:slaughter'], kind: 'source_coordinate', precision: 'source_provided_unverified', latitude: 38.9, longitude: -77.1, weight: 1, category_key: 'slaughter', category_keys: ['slaughter'] }] },
  meta: { private_preview: true, candidate_only: true, test_only: false, release_id: 'candidate-2026', snapshot_id: 'b'.repeat(64), bounded: true, scope: 'candidate_map', zoom_max: 14, preview_label: 'Configured candidate correction' },
};

describe('configured candidate map feed', () => {
  it('accepts only its points envelope and preserves source-native precision', () => {
    const result = parseRealPreviewMapFeed(envelope, true);
    expect(result.collection.features[0]?.properties).toMatchObject({ key: envelope.data.points[0].key, precision: 'source_provided_unverified', kind: 'source-coordinate' });
    expect(result.collection.features[0]?.properties).toMatchObject({ country_code: 'US', activity_keys: ['us.fsis:slaughter'] });
    expect(JSON.stringify(result.collection)).not.toMatch(/name|address|detail/i);
  });

  it('accepts the configured candidate’s opaque 32-hex snapshot identity', () => {
    expect(() => parseRealPreviewMapFeed({ ...envelope, meta: { ...envelope.meta, snapshot_id: 'a'.repeat(32) } }, true)).not.toThrow();
  });

  it('applies all selected full-projection dimensions before clustering', () => {
    const collection = parseRealPreviewMapFeed({ ...envelope, data: { points: [
      envelope.data.points[0],
      { ...envelope.data.points[0], key: '660e8400-e29b-41d4-a716-446655440000', source_id: 'au.example', country_code: 'AU', category_key: 'animal_keeping_and_production', category_keys: ['animal_keeping_and_production'], activity_keys: ['au.example:keeping'] },
    ] } }, true).collection;
    const filtered = filterTestReleaseMapCollection(collection, { countryCodes: ['AU'], categoryKeys: ['animal_keeping_and_production'], activityKeys: ['au.example:keeping'] });
    expect(filtered.features).toHaveLength(1);
    expect(filtered.features[0]?.properties.country_code).toBe('AU');
  });

  it('rejects fixtures and non-candidate boundaries', () => {
    expect(() => parseRealPreviewMapFeed({ ...envelope, meta: { ...envelope.meta, test_only: true } }, true)).toThrow(RealPreviewMapFeedError);
    expect(() => parseRealPreviewMapFeed({ ...envelope, data: {} }, true)).toThrow(RealPreviewMapFeedError);
  });

  it('loads the authenticated candidate feed without using the location list as map input', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify(envelope), { status: 200 }));
    await createTestReleaseMapFeedRepository(fetcher as typeof fetch).load();
    expect(fetcher).toHaveBeenCalledWith('/api/dev/preview/test-release/map/feed', expect.objectContaining({ credentials: 'same-origin', cache: 'no-store' }));
  });

  it('revalidates one cached candidate projection by ETag and shares a concurrent load', async () => {
    const entries = new Map<string, Response>();
    const cache = {
      keys: vi.fn(async () => [...entries.keys()].map(url => new Request(url))),
      match: vi.fn(async (request: Request) => entries.get(request.url)),
      put: vi.fn(async (request: Request, response: Response) => { entries.set(request.url, response); }),
      delete: vi.fn(async (request: Request) => entries.delete(request.url)),
    };
    vi.stubGlobal('location', new URL('http://127.0.0.1:34206/'));
    vi.stubGlobal('caches', { open: vi.fn(async () => cache) });
    const fetcher = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(envelope), { status: 200, headers: { etag: '"candidate-map-' + 'b'.repeat(64) + '"' } }))
      .mockResolvedValueOnce(new Response(null, { status: 304 }));
    const repository = createTestReleaseMapFeedRepository(fetcher as typeof fetch);
    const [first, duplicate] = await Promise.all([repository.load(), repository.load()]);
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(first.cacheStatus).toBe('miss');
    expect(duplicate.cacheStatus).toBe('miss');
    await vi.waitFor(() => expect(entries.size).toBe(1));
    const hit = await repository.load();
    expect(hit.cacheStatus).toBe('hit');
    expect(fetcher.mock.calls[1]?.[1]).toMatchObject({ headers: { 'If-None-Match': '"candidate-map-' + 'b'.repeat(64) + '"' } });
    vi.unstubAllGlobals();
  });

  it('replaces a stale release snapshot after a 200 and removes the older cache entry', async () => {
    const oldKey = 'http://127.0.0.1:34206/__uec_candidate_map_cache__/candidate-2026/' + 'a'.repeat(64);
    const entries = new Map<string, Response>([[oldKey, new Response(JSON.stringify({ ...envelope, meta: { ...envelope.meta, snapshot_id: 'a'.repeat(64) } }), { headers: { etag: '"candidate-map-' + 'a'.repeat(64) + '"' } })]]);
    const cache = { keys: vi.fn(async () => [...entries.keys()].map(url => new Request(url))), match: vi.fn(async (request: Request) => entries.get(request.url)), put: vi.fn(async (request: Request, response: Response) => { entries.set(request.url, response); }), delete: vi.fn(async (request: Request) => entries.delete(request.url)) };
    vi.stubGlobal('location', new URL('http://127.0.0.1:34206/'));
    vi.stubGlobal('caches', { open: vi.fn(async () => cache) });
    const next = { ...envelope, meta: { ...envelope.meta, snapshot_id: 'c'.repeat(64) } };
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify(next), { status: 200, headers: { etag: '"candidate-map-' + 'c'.repeat(64) + '"' } }));
    await expect(createTestReleaseMapFeedRepository(fetcher as typeof fetch).load()).resolves.toMatchObject({ cacheStatus: 'miss', snapshotId: 'c'.repeat(64) });
    await vi.waitFor(() => expect(entries.has(oldKey)).toBe(false));
    expect(entries.size).toBe(1);
    vi.unstubAllGlobals();
  });

  it('renders a parsed candidate projection before a slow Cache Storage write finishes', async () => {
    let finishPut: (() => void) | undefined;
    const cache = {
      keys: vi.fn(async () => []), match: vi.fn(async () => undefined),
      put: vi.fn(() => new Promise<void>(resolve => { finishPut = resolve; })), delete: vi.fn(async () => true),
    };
    vi.stubGlobal('location', new URL('http://127.0.0.1:34206/'));
    vi.stubGlobal('caches', { open: vi.fn(async () => cache) });
    const result = await createTestReleaseMapFeedRepository(vi.fn().mockResolvedValue(new Response(JSON.stringify(envelope), { status: 200 })) as typeof fetch).load();
    expect(result.cacheStatus).toBe('miss');
    await vi.waitFor(() => expect(finishPut).toBeTypeOf('function'));
    finishPut?.();
    vi.unstubAllGlobals();
  });

  it('does not restore a cache entry after clear while an older write is in flight', async () => {
    const entries = new Map<string, Response>();
    let finishPut: (() => void) | undefined;
    const cache = {
      keys: vi.fn(async () => [...entries.keys()].map(url => new Request(url))), match: vi.fn(async () => undefined),
      put: vi.fn(async (request: Request, response: Response) => { await new Promise<void>(resolve => { finishPut = resolve; }); entries.set(request.url, response); }),
      delete: vi.fn(async (request: Request) => entries.delete(request.url)),
    };
    vi.stubGlobal('location', new URL('http://127.0.0.1:34206/'));
    vi.stubGlobal('caches', { open: vi.fn(async () => cache) });
    await createTestReleaseMapFeedRepository(vi.fn().mockResolvedValue(new Response(JSON.stringify(envelope), { status: 200 })) as typeof fetch).load();
    await vi.waitFor(() => expect(finishPut).toBeTypeOf('function'));
    const { clearTestReleaseMapCache } = await import('../../src/api/TestReleaseMapFeedRepository');
    await clearTestReleaseMapCache();
    finishPut?.();
    await vi.waitFor(() => expect(entries.size).toBe(0));
    vi.unstubAllGlobals();
  });
});
