import { describe, expect, it, vi } from 'vitest';
import { clearPublicMapCache, createPublicMapFeedRepository, parsePublicMapFeed, publicMapCacheEntryCount } from '../../src/api/PublicMapFeedRepository';

const id = '11111111-1111-4111-8111-111111111111';
const meta = { profile: 'official', release_id: 'v0', manifest_sha256: 'a'.repeat(64), suppression_generation: 7, dataset_version: 'v0', release_label: 'v0', public_record_count: 1, feature_count: 1, unmapped_count: 0 };

describe('public map compact feed', () => {
  it('expands repeated-property dictionaries while retaining the direct UUID', () => {
    const feed = parsePublicMapFeed({ api_version: 'v2', data: { format: 'compact-v1', dictionaries: { source_ids: ['source'], category_keys: ['slaughter'], precisions: ['exact'] }, features: [[id, 1, 2, 0, 0, [0], 0]] }, meta }, 'official', 'v0');
    expect(feed.collection.features).toHaveLength(1);
    expect(feed.collection.features[0]?.properties).toMatchObject({ facility_id: id, source_id: 'source', category_key: 'slaughter', icon: 'v1-pin-red', precision: 'exact' });
  });
  it('keeps approximate precision as a reference in compact and legacy feeds', () => {
    const compact = parsePublicMapFeed({ api_version: 'v2', data: { format: 'compact-v1', dictionaries: { source_ids: ['source'], category_keys: ['slaughter'], precisions: ['approximate'] }, features: [[id, 1, 2, 0, 0, [0], 0]] }, meta }, 'official', 'v0');
    const legacy = parsePublicMapFeed({ api_version: 'v2', data: { type: 'FeatureCollection', features: [{ type: 'Feature', id, geometry: { type: 'Point', coordinates: [1, 2] }, properties: { facility_id: id, source_id: 'source', category_key: 'slaughter', category_keys: ['slaughter'], precision: 'approximate', weight: 1 } }] }, meta }, 'official', 'v0');
    for (const feed of [compact, legacy]) expect(feed.collection.features[0]?.properties).toMatchObject({ precision: 'approximate', kind: 'reference', cosLatitude: expect.any(Number) });
  });
  it('keeps source-reported coordinates as points without a reference radius', () => {
    const feed = parsePublicMapFeed({ api_version: 'v2', data: { format: 'compact-v1', dictionaries: { source_ids: ['source'], category_keys: ['slaughter'], precisions: ['source_reported'] }, features: [[id, 1, 2, 0, 0, [0], 0]] }, meta }, 'official', 'v0');
    expect(feed.collection.features[0]?.properties).toMatchObject({ precision: 'source_reported', kind: 'source-coordinate' });
    expect(feed.collection.features[0]?.properties.cosLatitude).toBeUndefined();
  });
  it('rejects compact indices outside their dictionaries', () => {
    expect(() => parsePublicMapFeed({ api_version: 'v2', data: { format: 'compact-v1', dictionaries: { source_ids: [], category_keys: [], precisions: [] }, features: [[id, 1, 2, 0, 0, [], 0]] }, meta }, 'official', 'v0')).toThrow();
  });
  it('retains country codes and uses grey processing pins', () => {
    const feed = parsePublicMapFeed({ api_version: 'v2', data: { format: 'compact-v1', dictionaries: { source_ids: ['source'], category_keys: ['processing_and_preparation'], precisions: ['exact'] }, features: [[id, 1, 2, 0, 0, [0], 0, 'NL']] }, meta }, 'official', 'v0');
    expect(feed.collection.features[0]?.properties).toMatchObject({ country_code: 'NL', icon: 'v1-pin-grey' });
  });
  it('reports zero and clears safely when Cache Storage is unavailable', async () => {
    const original = (globalThis as { caches?: unknown }).caches;
    Object.defineProperty(globalThis, 'caches', { configurable: true, value: undefined });
    await expect(publicMapCacheEntryCount()).resolves.toBe(0);
    await expect(clearPublicMapCache()).resolves.toBeUndefined();
    Object.defineProperty(globalThis, 'caches', { configurable: true, value: original });
  });
  it('singleflights an identity and isolates one aborted subscriber', async () => {
    const original = (globalThis as { caches?: unknown }).caches;
    Object.defineProperty(globalThis, 'caches', { configurable: true, value: undefined });
    let calls = 0; let resolve!: (value: Response) => void;
    const fetcher = (() => { calls++; return new Promise<Response>(r => { resolve = r; }); }) as typeof fetch;
    const repo = createPublicMapFeedRepository(fetcher);
    const controller = new AbortController();
    const identity = { releaseId: 'v0', manifestSha256: 'a'.repeat(64), suppressionGeneration: 7 };
    const first = repo.load('official', 'v0', controller.signal, identity);
    const second = repo.load('official', 'v0', undefined, identity);
    controller.abort();
    resolve(new Response(JSON.stringify({ api_version: 'v2', data: { type: 'FeatureCollection', features: [{ type:'Feature', id, geometry:{type:'Point',coordinates:[1,2]}, properties:{facility_id:id,source_id:'source',category_key:'slaughter',category_keys:['slaughter'],precision:'exact',weight:1} }] }, meta }), { status: 200 }));
    await expect(first).rejects.toMatchObject({ name: 'AbortError' });
    await expect(second).resolves.toMatchObject({ meta: { cacheStatus: 'unavailable' } });
    expect(calls).toBe(1);
    Object.defineProperty(globalThis, 'caches', { configurable: true, value: original });
  });
  it('keeps cache identity versioned across repository instances', async () => {
    const original = (globalThis as { caches?: unknown }).caches;
    const entries = new Map<string, Response>();
    const cache = { match: async (key: Request) => entries.get(key.url)?.clone(), put: async (key: Request, value: Response) => { entries.set(key.url, value.clone()); }, keys: async () => [...entries.keys()].map(url => new Request(url)), delete: async (key: Request) => entries.delete(key.url) };
    Object.defineProperty(globalThis, 'caches', { configurable: true, value: { open: async () => cache, delete: async () => { entries.clear(); return true; } } });
    let calls = 0; const payload = { api_version:'v2', data:{type:'FeatureCollection',features:[{type:'Feature',id,geometry:{type:'Point',coordinates:[1,2]},properties:{facility_id:id,source_id:'source',category_key:'slaughter',category_keys:['slaughter'],precision:'exact',weight:1}}]}, meta };
    const fetcher = (async () => { calls++; return new Response(JSON.stringify({ ...payload, meta: { ...meta, suppression_generation: calls === 1 ? 7 : 8 } })); }) as typeof fetch;
    const identity = { releaseId:'v0', manifestSha256:'a'.repeat(64), suppressionGeneration:7 };
    await createPublicMapFeedRepository(fetcher).load('official','v0',undefined,identity);
    await expect(createPublicMapFeedRepository(fetcher).load('official','v0',undefined,identity)).resolves.toMatchObject({meta:{cacheStatus:'hit'}});
    await createPublicMapFeedRepository(fetcher).load('official','v0',undefined,{...identity,suppressionGeneration:8});
    expect(calls).toBe(2);
    expect(await publicMapCacheEntryCount()).toBe(1);
    expect([...entries.keys()][0]).toMatch(/\/8$/);
    await clearPublicMapCache(); expect(await publicMapCacheEntryCount()).toBe(0);
    Object.defineProperty(globalThis, 'caches', { configurable: true, value: original });
  });
  it.each(['open', 'write'])('loads validated network data when projection storage fails on %s', async failure => {
    const original = (globalThis as { caches?: unknown }).caches;
    const fail = async () => { throw new Error('Storage unavailable'); };
    Object.defineProperty(globalThis, 'caches', { configurable: true, value: { open: failure === 'open' ? fail : async () => ({ match: async () => undefined, put: fail }) } });
    const payload = { api_version: 'v2', data: { format: 'compact-v1', dictionaries: {
      source_ids: ['source'], category_keys: ['slaughter'], precisions: ['exact'],
    }, features: [[id, 1, 2, 0, 0, [0], 0]] }, meta };
    const identity = { releaseId: 'v0', manifestSha256: 'a'.repeat(64), suppressionGeneration: 7 };
    try {
      const repo = createPublicMapFeedRepository((async () => new Response(JSON.stringify(payload))) as typeof fetch);
      await expect(repo.load('official', 'v0', undefined, identity)).resolves.toMatchObject({ meta: { cacheStatus: 'unavailable', featureCount: 1 } });
    } finally { Object.defineProperty(globalThis, 'caches', { configurable: true, value: original }); }
  });
  it.each([true, false])('restores cached feeds without serializing all points again (measured metadata: %s)', async hasMetadata => {
    const original = (globalThis as { caches?: unknown }).caches;
    const entries = new Map<string, Response>();
    const cache = { match: async (key: Request) => entries.get(key.url)?.clone(),
      put: async (key: Request, value: Response) => { entries.set(key.url, value.clone()); },
      keys: async () => [...entries.keys()].map(url => new Request(url)), delete: async (key: Request) => entries.delete(key.url) };
    Object.defineProperty(globalThis, 'caches', { configurable: true, value: { open: async () => cache } });
    const payload = { api_version: 'v2', data: { format: 'compact-v1', dictionaries: {
      source_ids: ['source'], category_keys: ['slaughter'], precisions: ['exact'],
    }, features: [[id, 1, 2, 0, 0, [0], 0]] }, meta };
    const identity = { releaseId: 'v0', manifestSha256: 'a'.repeat(64), suppressionGeneration: 7 };
    const fetcher = vi.fn(async () => new Response(JSON.stringify(payload)));
    let stringify: ReturnType<typeof vi.spyOn> | undefined;
    try {
      const repo = createPublicMapFeedRepository(fetcher as typeof fetch);
      const cold = await repo.load('official', 'v0', undefined, identity);
      expect(cold.meta.decodedBytes).toBeGreaterThan(0);
      if (!hasMetadata) {
        for (const [key, response] of entries) entries.set(key, new Response(await response.text(), { headers: { 'content-type': 'application/json' } }));
      }
      stringify = vi.spyOn(JSON, 'stringify');
      const warm = await repo.load('official', 'v0', undefined, identity);
      expect(fetcher).toHaveBeenCalledTimes(1);
      expect(warm.meta.cacheStatus).toBe('hit');
      expect(warm.collection).toEqual(cold.collection);
      expect(warm.meta.decodedBytes).toBe(hasMetadata ? cold.meta.decodedBytes : undefined);
      expect(stringify.mock.calls.some(([value]) => value?.type === 'FeatureCollection')).toBe(false);
    } finally {
      stringify?.mockRestore();
      Object.defineProperty(globalThis, 'caches', { configurable: true, value: original });
    }
  });
  it('replaces the previous release and rejects cached payloads with a mismatched identity', async () => {
    const original = (globalThis as { caches?: unknown }).caches;
    const entries = new Map<string, Response>();
    const cache = { match: async (key: Request) => entries.get(key.url)?.clone(), put: async (key: Request, value: Response) => { entries.set(key.url, value.clone()); }, keys: async () => [...entries.keys()].map(url => new Request(url)), delete: async (key: Request) => entries.delete(key.url) };
    Object.defineProperty(globalThis, 'caches', { configurable: true, value: { open: async () => cache } });
    const payload = (releaseId: string, generation = 7) => ({ api_version: 'v2', data: { format: 'compact-v1', dictionaries: { source_ids: ['source'], category_keys: ['slaughter'], precisions: ['exact'] }, features: [[id, 1, 2, 0, 0, [0], 0]] }, meta: { ...meta, release_id: releaseId, suppression_generation: generation } });
    let calls = 0;
    const fetcher = (async (input: string | URL | Request) => {
      calls++;
      const releaseId = new URL(String(input), 'https://example.test').searchParams.get('release_id')!;
      return new Response(JSON.stringify(payload(releaseId)));
    }) as typeof fetch;
    try {
      const repo = createPublicMapFeedRepository(fetcher);
      const identity = { releaseId: 'v0', manifestSha256: 'a'.repeat(64), suppressionGeneration: 7 };
      await repo.load('official', 'v0', undefined, identity);
      await repo.load('official', 'v1', undefined, { ...identity, releaseId: 'v1' });
      expect(entries.size).toBe(1);
      const key = [...entries.keys()][0]!;
      expect(key).toContain('/v1/');
      entries.set(key, new Response(JSON.stringify(payload('v1', 6))));
      await expect(repo.load('official', 'v1', undefined, { ...identity, releaseId: 'v1' })).resolves.toMatchObject({ meta: { suppressionGeneration: 7, cacheStatus: 'miss' } });
      expect(calls).toBe(3);
      expect(entries.size).toBe(1);
    } finally {
      Object.defineProperty(globalThis, 'caches', { configurable: true, value: original });
    }
  });
});
