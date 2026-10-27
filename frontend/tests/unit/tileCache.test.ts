import { webcrypto } from 'node:crypto';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { allowedTileUrl, createViewedTileCache, getTileCacheSettings, resetTileCacheSettings, setTileCachePersistenceAllowed, TILE_CACHE_NAME, tileCacheUrl, tileFreshUntil, updateTileCacheSettings } from '../../src/map/tileCache';
import { updateMapTileMemoryCache } from '../../src/map/mapTileMemoryCache';

const now = Date.parse('2026-10-25T12:00:00Z');
const url = 'https://tile.openstreetmap.org/4/8/5.png';
const bytes = new Uint8Array([137, 80, 78, 71]).buffer;
function memoryStorage() {
  const values = new Map<string, Response>();
  const cache = {
    keys: async () => [...values.keys()].map(key => new Request(key)),
    match: async (key: Request | string) => values.get(typeof key === 'string' ? key : key.url)?.clone(),
    put: async (key: Request | string, value: Response) => { values.set(typeof key === 'string' ? key : key.url, value.clone()); },
    delete: async (key: Request | string) => values.delete(typeof key === 'string' ? key : key.url),
  };
  return { values, storage: { open: vi.fn(async (name: string) => { expect(name).toBe(TILE_CACHE_NAME); return cache; }) } as unknown as CacheStorage };
}
function response(headers: Record<string, string> = {}) {
  return new Response(bytes.slice(0), { headers: { 'content-type': 'image/png', 'cache-control': 'public, max-age=3600', expires: new Date(now + 3600_000).toUTCString(), ...headers } });
}
function setup(options: { maxEntries?: number; maxBytes?: number } = {}) {
  vi.stubGlobal('crypto', webcrypto);
  let time = now;
  const memory = memoryStorage();
  const fetcher = vi.fn(async () => response());
  const environment = { storage: memory.storage, fetcher: fetcher as typeof fetch, now: () => time, origin: 'https://app.test', ...options };
  return { memory, fetcher, environment, setTime: (value: number) => { time = value; }, create: () => createViewedTileCache(environment) };
}
const signal = () => new AbortController().signal;

describe('viewed map tile cache', () => {
  beforeEach(() => { resetTileCacheSettings(); setTileCachePersistenceAllowed(true); });
  it('accepts only the existing static provider tile paths, with canonical world coordinates', () => {
    expect(allowedTileUrl(tileCacheUrl(url))).toBe(url);
    expect(allowedTileUrl('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/4/5/8')).toBeTruthy();
    expect(allowedTileUrl('https://tiles.mapterhorn.com/0/0/0.webp')).toBeTruthy();
    for (const value of ['/api/v2/locations?q=private', 'https://app.test/api/v2/map', url + '?q=private', url + '#private', url.replace('/8/', '/16/'), url.replace('https:', 'http:'), url.replace('tile.openstreetmap.org', 'evil.test'), url.replace('https://', 'https://user@')]) expect(allowedTileUrl(value)).toBeNull();
  });

  it('uses absolute expiry and observed server age without restarting a cached response TTL', () => {
    expect(tileFreshUntil(response().headers, now)).toBe(now + 3600_000);
    expect(tileFreshUntil(new Headers({ 'cache-control': 'max-age=3600', date: new Date(now - 1800_000).toUTCString(), age: '2700' }), now)).toBe(now + 900_000);
    expect(tileFreshUntil(new Headers({ 'cache-control': 'max-age=3600' }), now)).toBeNull();
    for (const control of ['no-store', 'private, max-age=3600', 'no-cache="set-cookie",max-age=3600', 'max-age=0']) {
      const headers = response({ 'cache-control': control, date: new Date(now).toUTCString() }).headers;
      expect(tileFreshUntil(headers, now)).toBeNull();
    }
    expect(tileFreshUntil(response({ expires: new Date(now - 1).toUTCString() }).headers, now)).toBeNull();
  });

  it('reuses hashed stored bytes across new cache instances and refetches after TTL', async () => {
    const fixture = setup();
    expect((await fixture.create().load(tileCacheUrl(url), signal())).data).toEqual(bytes);
    expect((await fixture.create().load(tileCacheUrl(url), signal())).data).toEqual(bytes);
    expect(fixture.fetcher).toHaveBeenCalledTimes(1);
    const keys = [...fixture.memory.values.keys()];
    expect(keys).toHaveLength(1);
    expect(keys[0]).toMatch(/^https:\/\/app\.test\/__uec_tile_cache__\/[a-f0-9]{64}$/);
    expect(keys[0]).not.toContain('openstreetmap');
    fixture.setTime(now + 3600_001);
    await fixture.create().load(tileCacheUrl(url), signal());
    expect(fixture.fetcher).toHaveBeenCalledTimes(2);
  });

  it('evicts least recently viewed entries within both byte and entry limits', async () => {
    const fixture = setup({ maxEntries: 2, maxBytes: 8 });
    const cache = fixture.create();
    await cache.load(tileCacheUrl(url), signal());
    fixture.setTime(now + 1);
    await cache.load(tileCacheUrl(url.replace('/8/', '/9/')), signal());
    fixture.setTime(now + 2);
    await cache.load(tileCacheUrl(url), signal());
    fixture.setTime(now + 3);
    await cache.load(tileCacheUrl(url.replace('/8/', '/10/')), signal());
    expect(fixture.memory.values.size).toBe(2);
    await cache.load(tileCacheUrl(url), signal());
    expect(fixture.fetcher).toHaveBeenCalledTimes(3);
    await cache.load(tileCacheUrl(url.replace('/8/', '/9/')), signal());
    expect(fixture.fetcher).toHaveBeenCalledTimes(4);
  });

  it('discards malformed metadata and damaged bytes, without serving stale data after errors', async () => {
    const fixture = setup();
    await fixture.create().load(tileCacheUrl(url), signal());
    const [key, value] = [...fixture.memory.values][0]!;
    fixture.memory.values.set(key, new Response(new Uint8Array([1, 2, 3, 4]), { headers: value.headers }));
    await fixture.create().load(tileCacheUrl(url), signal());
    expect(fixture.fetcher).toHaveBeenCalledTimes(2);
    fixture.setTime(now + 7200_000);
    fixture.fetcher.mockRejectedValueOnce(new Error('offline'));
    await expect(fixture.create().load(tileCacheUrl(url), signal())).rejects.toThrow('offline');
  });

  it('delegates uncacheable responses to browser HTTP caching and survives unavailable storage', async () => {
    const fixture = setup();
    fixture.fetcher.mockImplementation(async () => response({ 'cache-control': 'no-store' }));
    await fixture.create().load(tileCacheUrl(url), signal());
    expect(fixture.memory.values.size).toBe(0);
    const cache = createViewedTileCache({ storage: { open: async () => { throw new Error('blocked'); } } as unknown as CacheStorage, fetcher: fixture.fetcher as typeof fetch });
    await expect(cache.load(tileCacheUrl(url), signal())).resolves.toHaveProperty('data');
    expect(fixture.fetcher).toHaveBeenLastCalledWith(url, expect.objectContaining({ cache: 'default', credentials: 'omit' }));
    const controller = new AbortController(); controller.abort();
    await expect(cache.load(tileCacheUrl(url), controller.signal)).rejects.toMatchObject({ name: 'AbortError' });
  });

  it('separates app storage hits from browser-managed satellite requests without inventing a freshness deadline', async () => {
    const fixture = setup();
    const satellite = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/4/5/8';
    fixture.fetcher.mockImplementation(async (request?: unknown) => String(request).includes('World_Imagery')
      ? new Response(bytes.slice(0), { headers: { 'content-type': 'image/jpeg', 'cache-control': 'max-age=86400' } })
      : response());
    const updates: Array<Record<string, unknown>> = [];
    const cache = createViewedTileCache({ ...fixture.environment, onDiagnostics: value => updates.push({ ...value }) });
    await cache.load(tileCacheUrl(url), signal());
    await cache.load(tileCacheUrl(url), signal());
    await cache.load(tileCacheUrl(satellite), signal());
    await cache.load(tileCacheUrl(satellite), signal());
    expect(updates.at(-1)).toMatchObject({ hits: 1, misses: 3, policyDelegations: 2,
      streetHits: 1, streetMisses: 1, streetDelegations: 0,
      satelliteHits: 0, satelliteMisses: 2, satelliteDelegations: 2 });
    expect(fixture.memory.values.size).toBe(1);
    expect(fixture.fetcher).toHaveBeenCalledTimes(3);
  });

  it('applies bounded session controls, shortened TTL and clear to actual stored tiles', async () => {
    const fixture = setup();
    fixture.fetcher.mockImplementation(async () => response({ expires: new Date(now + 7 * 86400_000).toUTCString() }));
    const updates: { hits: number; misses: number; entries: number }[] = [];
    const cache = createViewedTileCache({ ...fixture.environment, onDiagnostics: value => updates.push(value) });
    await cache.load(tileCacheUrl(url), signal());
    await cache.load(tileCacheUrl(url), signal());
    expect(updates.at(-1)).toMatchObject({ hits: 1, misses: 1, entries: 1 });
    updateTileCacheSettings({ maxTtlMs: 3600_000 });
    fixture.setTime(now + 7200_000);
    await cache.load(tileCacheUrl(url), signal());
    expect(fixture.fetcher).toHaveBeenCalledTimes(2);
    updateTileCacheSettings({ enabled: false });
    await cache.load(tileCacheUrl(url), signal());
    expect(fixture.fetcher).toHaveBeenCalledTimes(3);
    await cache.clear();
    expect(fixture.memory.values.size).toBe(0);
    expect(updates.at(-1)).toMatchObject({ entries: 0 });
    updateTileCacheSettings({ maxEntries: 10000, maxBytes: 1, maxTtlMs: 10000 });
    expect(getTileCacheSettings()).toMatchObject({ maxEntries: 1024, maxBytes: 4 * 1024 * 1024, maxTtlMs: 3600_000 });
  });

  it('never persists private/device-derived views, including requests already in flight', async () => {
    const fixture = setup();
    const cache = fixture.create();
    setTileCachePersistenceAllowed(false);
    await cache.load(tileCacheUrl(url), signal());
    expect(fixture.memory.storage.open).not.toHaveBeenCalled();
    expect(fixture.memory.values.size).toBe(0);
    setTileCachePersistenceAllowed(true);
    let finish!: (value: Response) => void;
    fixture.fetcher.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
    const loading = cache.load(tileCacheUrl(url), signal());
    await vi.waitFor(() => expect(finish).toBeTypeOf('function'));
    setTileCachePersistenceAllowed(false);
    finish(response()); await loading;
    expect(fixture.memory.values.size).toBe(0);
  });

  it('does not repopulate cleared storage when an older tile request finishes', async () => {
    const fixture = setup();
    const cache = fixture.create();
    let finish!: (value: Response) => void;
    fixture.fetcher.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
    const loading = cache.load(tileCacheUrl(url), signal());
    await vi.waitFor(() => expect(finish).toBeTypeOf('function'));
    await cache.clear();
    finish(response()); await loading;
    expect(fixture.memory.values.size).toBe(0);
    await cache.load(tileCacheUrl(url), signal());
    expect(fixture.memory.values.size).toBe(1);
  });

  it('changes the guarded MapLibre memory cache limit without reloading sources', () => {
    const updateCacheSize = vi.fn();
    const map = { _maxTileCacheSize: null, _camera: { transform: { width: 800 } }, style: { tileManagers: { base: { _maxTileCacheSize: 128, updateCacheSize } } } };
    expect(updateMapTileMemoryCache(map, 300)).toBe(true);
    expect(map._maxTileCacheSize).toBe(256);
    expect(map.style.tileManagers.base._maxTileCacheSize).toBe(256);
    expect(updateCacheSize).toHaveBeenCalledWith(map._camera.transform);
    expect(updateMapTileMemoryCache({}, 128)).toBe(false);
    expect(updateMapTileMemoryCache(map, NaN)).toBe(false);
  });
});
