import { parseRealPreviewMapFeed, RealPreviewMapFeedError, type RealPreviewMapFeed } from './RealPreviewMapFeedRepository';
import { TEST_RELEASE_PATH } from '../features/devPreview/devPreviewContract';

const CACHE_NAME = 'uec-candidate-map-projection-v1';

function cacheKey(releaseId: string, snapshotId: string): string {
  return `${location.origin}/__uec_candidate_map_cache__/${encodeURIComponent(releaseId)}/${snapshotId}`;
}

/**
 * The configured candidate uses the same compact map collection and native
 * cluster renderer as the private preview, while retaining an independent
 * cache namespace and its stricter authenticated DTO boundary.
 */
export function createTestReleaseMapFeedRepository(fetcher: typeof fetch = fetch) {
  return {
    async load(signal?: AbortSignal): Promise<RealPreviewMapFeed> {
      let response: Response;
      try {
        response = await fetcher(`${TEST_RELEASE_PATH}/map/feed`, { credentials: 'same-origin', cache: 'no-store', ...(signal ? { signal } : {}) });
      } catch {
        throw new RealPreviewMapFeedError('The corrected candidate map feed could not be reached.');
      }
      if (!response.ok) {
        throw new RealPreviewMapFeedError(response.status === 401 || response.status === 403
          ? 'The corrected candidate map session is not authorized.'
          : 'The corrected candidate map feed could not be loaded.');
      }
      const payload = await response.json();
      const parsed = parseRealPreviewMapFeed(payload, true);
      const meta = payload as { meta: { release_id: string; snapshot_id: string } };
      if (typeof caches === 'undefined' || typeof location === 'undefined' || !/^(localhost|127\.0\.0\.1)$/.test(location.hostname)) {
        return { ...parsed, cacheStatus: 'unavailable', decodedBytes: new TextEncoder().encode(JSON.stringify(parsed.collection)).byteLength };
      }
      const cache = await caches.open(CACHE_NAME);
      await cache.put(cacheKey(meta.meta.release_id, meta.meta.snapshot_id), new Response(JSON.stringify(payload), { headers: { 'content-type': 'application/json' } }));
      for (const request of await cache.keys()) {
        if (!request.url.includes(`/__uec_candidate_map_cache__/${encodeURIComponent(meta.meta.release_id)}/`)) await cache.delete(request);
      }
      return { ...parsed, cacheStatus: 'miss', decodedBytes: new TextEncoder().encode(JSON.stringify(parsed.collection)).byteLength };
    },
  };
}

export async function clearTestReleaseMapCache(): Promise<number> {
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
