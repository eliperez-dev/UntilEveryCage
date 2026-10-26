/** Viewed provider tiles only. Never accepts API URLs, queries, or arbitrary hosts. */
export const TILE_CACHE_NAME = 'uec-viewed-map-tiles-v1';
export const TILE_CACHE_MAX_ENTRIES = 512;
export const TILE_CACHE_MAX_BYTES = 32 * 1024 * 1024;
const MAX_TILE_BYTES = 2 * 1024 * 1024;
const PREFIX = 'uec-tile://';
const META_EXPIRY = 'x-uec-expiry';
const META_ACCESS = 'x-uec-access';
const META_SIZE = 'x-uec-size';
const META_STORED = 'x-uec-stored';
const META_DIGEST = 'x-uec-content-digest';

export type TileCacheSettings = { enabled: boolean; maxEntries: number; maxBytes: number; maxTtlMs: number };
export type TileCacheDiagnostics = {
  available: 'unknown' | 'available' | 'unavailable'; entries: number; bytes: number;
  hits: number; misses: number; evictions: number; policyDelegations: number; persistenceAllowed: boolean;
};
export const DEFAULT_TILE_CACHE_SETTINGS: Readonly<TileCacheSettings> = Object.freeze({
  enabled: true, maxEntries: TILE_CACHE_MAX_ENTRIES, maxBytes: TILE_CACHE_MAX_BYTES, maxTtlMs: 7 * 86400_000,
});
let settings: TileCacheSettings = { ...DEFAULT_TILE_CACHE_SETTINGS };
let persistenceAllowed = true;
let persistenceGeneration = 0;
let diagnostics: TileCacheDiagnostics = { available: 'unknown', entries: 0, bytes: 0, hits: 0, misses: 0, evictions: 0, policyDelegations: 0, persistenceAllowed };
const listeners = new Set<(value: TileCacheDiagnostics) => void>();
function notifyDiagnostics(value = diagnostics) { diagnostics = { ...value }; for (const listener of listeners) listener({ ...diagnostics }); }
export function getTileCacheSettings(): TileCacheSettings { return { ...settings }; }
export function setTileCachePersistenceAllowed(allowed: boolean): void {
  if (persistenceAllowed !== allowed) persistenceGeneration++;
  persistenceAllowed = allowed; notifyDiagnostics({ ...diagnostics, persistenceAllowed });
}
export function updateTileCacheSettings(patch: Partial<TileCacheSettings>): TileCacheSettings {
  const bounded = (value: number | undefined, current: number, minimum: number, maximum: number) =>
    value !== undefined && Number.isFinite(value) ? Math.round(Math.min(maximum, Math.max(minimum, value))) : current;
  settings = {
    enabled: patch.enabled ?? settings.enabled,
    maxEntries: bounded(patch.maxEntries, settings.maxEntries, 32, 1024),
    maxBytes: bounded(patch.maxBytes, settings.maxBytes, 4 * 1024 * 1024, 64 * 1024 * 1024),
    maxTtlMs: bounded(patch.maxTtlMs, settings.maxTtlMs, 3600_000, 7 * 86400_000),
  };
  void activeCache?.trim();
  notifyDiagnostics();
  return getTileCacheSettings();
}
export function resetTileCacheSettings(): TileCacheSettings { return updateTileCacheSettings({ ...DEFAULT_TILE_CACHE_SETTINGS }); }
export function getTileCacheDiagnostics(): TileCacheDiagnostics { return { ...diagnostics }; }
export function subscribeTileCacheDiagnostics(listener: (value: TileCacheDiagnostics) => void): () => void {
  listeners.add(listener); listener(getTileCacheDiagnostics()); return () => { listeners.delete(listener); };
}

export function tileCacheUrl(url: string): string { return PREFIX + url; }

export function allowedTileUrl(value: string): string | null {
  const raw = value.startsWith(PREFIX) ? value.slice(PREFIX.length) : value;
  let url: URL;
  try { url = new URL(raw); } catch { return null; }
  if (url.protocol !== 'https:' || url.search || url.hash || url.username || url.password || url.port) return null;
  const pattern = url.hostname === 'tile.openstreetmap.org' ? /^\/(\d+)\/(\d+)\/(\d+)\.png$/
    : url.hostname === 'server.arcgisonline.com' ? /^\/ArcGIS\/rest\/services\/(?:World_Imagery|Reference\/World_Transportation)\/MapServer\/tile\/(\d+)\/(\d+)\/(\d+)$/
    : url.hostname === 'tiles.mapterhorn.com' ? /^\/(\d+)\/(\d+)\/(\d+)\.webp$/ : null;
  const match = pattern?.exec(url.pathname);
  if (!match) return null;
  const [z, x, y] = match.slice(1).map(Number);
  if (z === undefined || x === undefined || y === undefined || z > 22 || x >= 2 ** z || y >= 2 ** z) return null;
  return url.href;
}

/** Use an absolute freshness deadline, never restart max-age on an HTTP-cache hit.
 * Date/Age are often not CORS-exposed. Without a usable absolute deadline the
 * browser's HTTP cache remains the authority instead of guessing a new TTL.
 */
export function tileFreshUntil(headers: Headers, now: number): number | null {
  const control = headers.get('cache-control') ?? '';
  if (/(?:^|,)\s*(?:no-store|no-cache|private)(?:\s|,|=|$)/i.test(control) || headers.get('vary') === '*') return null;
  const expiry = Date.parse(headers.get('expires') ?? '');
  const date = Date.parse(headers.get('date') ?? '');
  const maxAge = /(?:^|,)\s*max-age\s*=\s*"?(\d+)"?/i.exec(control);
  if (maxAge && Number(maxAge[1]) === 0) return null;
  const age = Number(headers.get('age') ?? '0');
  let deadline = Number.isFinite(expiry) ? expiry : Infinity;
  if (maxAge && Number.isFinite(date) && Number.isFinite(age) && age >= 0) {
    const seconds = Number(maxAge[1]);
    deadline = Math.min(deadline, now + (seconds - Math.max(age, (now - date) / 1000)) * 1000);
  }
  return Number.isFinite(deadline) && deadline > now ? deadline : null;
}

type Entry = { accessed: number; stored: number; bytes: number; expiry: number };
type TileResult = { data: ArrayBuffer; cacheControl?: string; expires?: string };
type CacheEnvironment = { storage?: CacheStorage; fetcher?: typeof fetch; now?: () => number; origin?: string; maxEntries?: number; maxBytes?: number; onDiagnostics?: (value: TileCacheDiagnostics) => void };

function tileResult(data: ArrayBuffer, expiry: number | null, headers: Headers, now: number): TileResult {
  const control = headers.get('cache-control');
  return { data, ...(expiry === null ? (control ? { cacheControl: control } : {}) : {
    cacheControl: `max-age=${Math.max(0, Math.floor((expiry - now) / 1000))}`,
    expires: new Date(expiry).toUTCString(),
  }), ...(expiry === null && headers.get('expires') ? { expires: headers.get('expires')! } : {}) };
}
async function digestBytes(data: ArrayBuffer): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', new Uint8Array(data));
  return Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('');
}

/** Bounded LRU of compressed bytes. MapLibre separately keeps decoded GPU tiles. */
export function createViewedTileCache(environment: CacheEnvironment = {}) {
  const clock = environment.now ?? Date.now;
  const fetcher = environment.fetcher ?? fetch;
  let cache: Cache | undefined;
  let storageReady: Promise<void> | undefined;
  let maintenance = Promise.resolve();
  const entries = new Map<string, Entry>();
  const metrics: TileCacheDiagnostics = { available: 'unknown', entries: 0, bytes: 0, hits: 0, misses: 0, evictions: 0, policyDelegations: 0, persistenceAllowed };
  function publish() {
    metrics.entries = entries.size;
    metrics.bytes = [...entries.values()].reduce((sum, entry) => sum + entry.bytes, 0);
    metrics.persistenceAllowed = persistenceAllowed;
    environment.onDiagnostics?.({ ...metrics });
  }

  const serialize = (operation: () => Promise<void>) => {
    maintenance = maintenance.then(operation).catch(() => {
      cache = undefined; entries.clear(); metrics.available = 'unavailable'; publish();
    });
    return maintenance;
  };
  async function initialize() {
    if (storageReady) return storageReady;
    storageReady = (async () => {
      const storage = environment.storage ?? globalThis.caches;
      if (!storage) { metrics.available = 'unavailable'; publish(); return; }
      cache = await storage.open(TILE_CACHE_NAME);
      metrics.available = 'available';
      for (const key of await cache.keys()) {
        const response = await cache.match(key);
        const expiry = Number(response?.headers.get(META_EXPIRY));
        const accessed = Number(response?.headers.get(META_ACCESS));
        const stored = Number(response?.headers.get(META_STORED));
        const bytes = Number(response?.headers.get(META_SIZE));
        if (!response || !Number.isFinite(expiry) || expiry <= clock() || !Number.isFinite(accessed) || !Number.isFinite(stored) || stored <= 0 || !Number.isInteger(bytes) || bytes <= 0 || bytes > MAX_TILE_BYTES) {
          await cache.delete(key); continue;
        }
        entries.set(key.url, { expiry, accessed, stored, bytes });
      }
      await prune();
      publish();
    })().catch(() => { cache = undefined; entries.clear(); metrics.available = 'unavailable'; publish(); });
    return storageReady;
  }
  async function prune() {
    const maxEntries = environment.maxEntries ?? settings.maxEntries;
    const maxBytes = environment.maxBytes ?? settings.maxBytes;
    let bytes = [...entries.values()].reduce((sum, entry) => sum + entry.bytes, 0);
    for (const [key, entry] of [...entries].sort((a, b) => a[1].accessed - b[1].accessed)) {
      if (Math.min(entry.expiry, entry.stored + settings.maxTtlMs) > clock() && entries.size <= maxEntries && bytes <= maxBytes) continue;
      entries.delete(key); bytes -= entry.bytes; metrics.evictions++; await cache?.delete(key);
    }
    publish();
  }
  async function cacheKey(url: string) {
    const hash = await digestBytes(new TextEncoder().encode(url).buffer);
    return `${environment.origin ?? globalThis.location?.origin ?? 'https://cache.invalid'}/__uec_tile_cache__/${hash}`;
  }
  async function save(key: string, data: ArrayBuffer, expiry: number, headers: Headers, generation: number, stored = clock(), digest?: string) {
    if (!cache || !settings.enabled || !persistenceAllowed) return;
    const storedHeaders = new Headers({ 'content-type': headers.get('content-type') ?? 'application/octet-stream',
      [META_EXPIRY]: String(expiry), [META_ACCESS]: String(clock()), [META_SIZE]: String(data.byteLength), [META_STORED]: String(stored), [META_DIGEST]: digest ?? await digestBytes(data) });
    if (!cache || !settings.enabled || !persistenceAllowed || generation !== persistenceGeneration) return;
    await cache.put(key, new Response(data.slice(0), { headers: storedHeaders }));
    if (!persistenceAllowed || generation !== persistenceGeneration) { await cache.delete(key); return; }
    entries.set(key, { expiry, accessed: clock(), stored, bytes: data.byteLength });
    await prune();
  }
  return {
    async clear(): Promise<void> {
      // Requests started before Clear must not repopulate it on completion.
      persistenceGeneration++;
      await initialize();
      await serialize(async () => {
        if (cache) for (const key of await cache.keys()) await cache.delete(key);
        entries.clear(); publish();
      });
    },
    async trim(): Promise<void> { await initialize(); await serialize(prune); },
    async load(protocolUrl: string, signal: AbortSignal): Promise<TileResult> {
      const url = allowedTileUrl(protocolUrl);
      if (!url) throw new Error('Unsupported map tile URL');
      const generation = persistenceGeneration;
      signal.throwIfAborted();
      if (settings.enabled && persistenceAllowed) await initialize();
      signal.throwIfAborted();
      let key: string | undefined;
      try { if (settings.enabled && persistenceAllowed && cache) key = await cacheKey(url); } catch { /* Crypto/storage may be unavailable. */ }
      if (key && cache && settings.enabled && persistenceAllowed && generation === persistenceGeneration) {
        try {
          const metadata = entries.get(key);
          if (metadata && Math.min(metadata.expiry, metadata.stored + settings.maxTtlMs) > clock()) {
            const hit = await cache.match(key);
            const data = hit ? await hit.arrayBuffer() : null;
            const digest = data ? await digestBytes(data) : null;
            if (data && data.byteLength === metadata.bytes && digest === hit!.headers.get(META_DIGEST)) {
              signal.throwIfAborted();
              const expiry = Math.min(metadata.expiry, metadata.stored + settings.maxTtlMs);
              await serialize(() => save(key!, data, metadata.expiry, hit!.headers, generation, metadata.stored, digest!));
              metrics.hits++; publish();
              return tileResult(data, expiry, hit!.headers, clock());
            }
          }
          entries.delete(key);
          await cache.delete(key);
        } catch (error) { if (signal.aborted) throw error; }
      }
      signal.throwIfAborted();
      metrics.misses++; publish();
      const response = await fetcher(url, { signal, mode: 'cors', credentials: 'omit', cache: 'default' });
      if (!response.ok || response.type === 'opaque') throw new Error(`Map tile unavailable (${response.status})`);
      const data = await response.arrayBuffer();
      signal.throwIfAborted();
      const providerExpiry = tileFreshUntil(response.headers, clock());
      const expiry = providerExpiry === null ? null : Math.min(providerExpiry, clock() + settings.maxTtlMs);
      if (expiry === null) { metrics.policyDelegations++; publish(); }
      if (settings.enabled && persistenceAllowed && key && expiry !== null && data.byteLength > 0 && data.byteLength <= MAX_TILE_BYTES && /^image\//i.test(response.headers.get('content-type') ?? '')) {
        await serialize(() => save(key!, data, expiry, response.headers, generation));
      }
      return tileResult(data, expiry, response.headers, clock());
    },
  };
}

let activeCache: ReturnType<typeof createViewedTileCache> | undefined;
export function loadViewedTile(url: string, signal: AbortSignal): Promise<TileResult> {
  activeCache ??= createViewedTileCache({ onDiagnostics: notifyDiagnostics });
  return activeCache.load(url, signal);
}
export async function clearTileCache(): Promise<void> {
  activeCache ??= createViewedTileCache({ onDiagnostics: notifyDiagnostics });
  await activeCache.clear();
}
