import { parseRealPreviewMapFeed, RealPreviewMapFeedError, type RealPreviewMapFeed } from './RealPreviewMapFeedRepository';
import { TEST_RELEASE_PATH } from '../features/devPreview/devPreviewContract';
import type { JsonMapCollection } from '../design-lab/components/jsonMapFallback';

// v2 adds country/category/activity projection fields. Keep older candidate
// entries out of this stricter filterable projection.
const CACHE_NAME = 'uec-candidate-map-projection-v2';
let cacheGeneration = 0;

export type CandidateMapFilters = Readonly<{ sourceIds?: readonly string[]; countryCodes?: readonly string[]; categoryKeys?: readonly string[]; activityKeys?: readonly string[] }>;

/** Filter the complete configured projection before MapLibre rebuilds clusters. */
export function filterTestReleaseMapCollection(collection: JsonMapCollection, filters: CandidateMapFilters): JsonMapCollection {
  const sources = new Set(filters.sourceIds ?? []), countries = new Set(filters.countryCodes ?? []), categories = new Set(filters.categoryKeys ?? []), activities = new Set(filters.activityKeys ?? []);
  return { ...collection, features: collection.features.filter(({ properties }) => {
    const strings = (key: string) => Array.isArray(properties[key]) ? properties[key].filter((value): value is string => typeof value === 'string') : [];
    if (sources.size && (typeof properties.source_id !== 'string' || !sources.has(properties.source_id))) return false;
    if (countries.size && (typeof properties.country_code !== 'string' || !countries.has(properties.country_code))) return false;
    if (categories.size && !strings('category_keys').some(value => categories.has(value))) return false;
    if (activities.size && !strings('activity_keys').some(value => activities.has(value))) return false;
    return true;
  }) };
}

function cacheKey(releaseId: string, snapshotId: string): Request {
  return new Request(new URL(`/__uec_candidate_map_cache__/${encodeURIComponent(releaseId)}/${snapshotId}`, globalThis.location?.origin ?? 'https://uec.invalid').href, { method: 'GET' });
}

function abortIsolated<T>(shared: Promise<T>, signal?: AbortSignal): Promise<T> {
  if (!signal) return shared;
  if (signal.aborted) return Promise.reject(new DOMException('Aborted', 'AbortError'));
  return new Promise((resolve, reject) => {
    const abort = () => reject(new DOMException('Aborted', 'AbortError'));
    signal.addEventListener('abort', abort, { once: true });
    shared.then(value => { signal.removeEventListener('abort', abort); resolve(value); }, error => { signal.removeEventListener('abort', abort); reject(error); });
  });
}

/**
 * The configured candidate uses the same compact map collection and native
 * cluster renderer as the private preview, while retaining an independent
 * cache namespace and its stricter authenticated DTO boundary.
 */
export function createTestReleaseMapFeedRepository(fetcher: typeof fetch = fetch) {
  const mapFlights = new Map<string, Promise<RealPreviewMapFeed>>();
  return {
    async load(signal?: AbortSignal): Promise<RealPreviewMapFeed> {
      const canCache = typeof caches !== 'undefined' && typeof location !== 'undefined' && /^(localhost|127\.0\.0\.1)$/.test(location.hostname);
      if (!canCache) return loadCandidateFeed(fetcher, undefined, signal);
      const cache = await caches.open(CACHE_NAME);
      // There is one configured candidate at a time. Its cached response keeps
      // the server ETag, allowing a 304 before the full projection is queried.
      const cachedRequest = (await cache.keys())[0];
      const cached = cachedRequest ? await cache.match(cachedRequest) : undefined;
      const etag = cached?.headers.get('etag') ?? null;
      const flightKey = etag ?? 'candidate-map-without-etag';
      const existing = mapFlights.get(flightKey);
      if (existing) return abortIsolated(existing, signal);
      const generation = cacheGeneration;
      const work = loadCandidateFeed(fetcher, cache, undefined, cached, etag, generation);
      mapFlights.set(flightKey, work);
      void work.finally(() => { if (mapFlights.get(flightKey) === work) mapFlights.delete(flightKey); });
      return abortIsolated(work, signal);
    },
  };
}

async function persistCandidateFeed(cache: Cache, key: Request, payload: unknown, etag: string | null, generation: number): Promise<void> {
  // Cache Storage can take much longer than projection parsing for a large
  // candidate. Yield first so a valid map renders without waiting on disk.
  await new Promise<void>(resolve => setTimeout(resolve, 0));
  if (generation !== cacheGeneration) return;
  await cache.put(key, new Response(JSON.stringify(payload), { headers: { 'content-type': 'application/json', ...(etag ? { etag } : {}) } }));
  if (generation !== cacheGeneration) {
    await cache.delete(key);
    return;
  }
  for (const request of await cache.keys()) {
    if (generation !== cacheGeneration) return;
    if (request.url !== key.url) await cache.delete(request);
  }
}

async function loadCandidateFeed(fetcher: typeof fetch, projectionCache?: Cache, signal?: AbortSignal, cached?: Response, etag?: string | null, generation = cacheGeneration): Promise<RealPreviewMapFeed> {
      let response: Response;
      try {
        response = await fetcher(`${TEST_RELEASE_PATH}/map/feed`, { credentials: 'same-origin', cache: 'no-store', ...(etag ? { headers: { 'If-None-Match': etag } } : {}), ...(signal ? { signal } : {}) });
      } catch {
        throw new RealPreviewMapFeedError('The corrected candidate map feed could not be reached.');
      }
      if (response.status === 304 && cached) {
        try {
          const parsed = parseRealPreviewMapFeed(await cached.json(), true);
          return { ...parsed, cacheStatus: 'hit', decodedBytes: new TextEncoder().encode(JSON.stringify(parsed.collection)).byteLength };
        } catch {
          throw new RealPreviewMapFeedError('The corrected candidate map cache was invalid.');
        }
      }
      if (!response.ok) {
        throw new RealPreviewMapFeedError(response.status === 401 || response.status === 403
          ? 'The corrected candidate map session is not authorized.'
          : 'The corrected candidate map feed could not be loaded.');
      }
      const payload = await response.json();
      const parsed = parseRealPreviewMapFeed(payload, true);
      const meta = payload as { meta: { release_id: string; snapshot_id: string } };
      if (!projectionCache) {
        return { ...parsed, cacheStatus: 'unavailable', decodedBytes: new TextEncoder().encode(JSON.stringify(parsed.collection)).byteLength };
      }
      const key = cacheKey(meta.meta.release_id, meta.meta.snapshot_id);
      const responseEtag = response.headers.get('etag');
      void persistCandidateFeed(projectionCache, key, payload, responseEtag, generation).catch(() => {
        // Map rendering remains valid when local Cache Storage is unavailable.
      });
      return { ...parsed, cacheStatus: 'miss', decodedBytes: new TextEncoder().encode(JSON.stringify(parsed.collection)).byteLength };
}

export async function clearTestReleaseMapCache(): Promise<number> {
  cacheGeneration++;
  if (typeof caches === 'undefined') return 0;
  const cache = await caches.open(CACHE_NAME);
  const entries = await cache.keys();
  await Promise.all(entries.map(request => cache.delete(request)));
  return entries.length;
}

export async function testReleaseMapCacheEntryCount(): Promise<number | null> {
  if (typeof caches === 'undefined') return null;
  return (await (await caches.open(CACHE_NAME)).keys()).length;
}
