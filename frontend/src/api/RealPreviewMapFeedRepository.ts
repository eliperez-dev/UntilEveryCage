import type { JsonMapCollection, JsonMapFeature } from '../design-lab/components/jsonMapFallback';

export type RealPreviewMapFeed = Readonly<{
  collection: JsonMapCollection;
  snapshotId: string;
  cacheStatus: 'hit' | 'miss' | 'unavailable';
  decodedBytes?: number;
}>;

export class RealPreviewMapFeedError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'RealPreviewMapFeedError';
  }
}

function finiteCoordinate(value: unknown, min: number, max: number): value is number {
  return typeof value === 'number' && Number.isFinite(value) && value >= min && value <= max;
}

/** Parse the compact map-only envelope without carrying record details into the map source. */
export function parseRealPreviewMapFeed(payload: unknown): RealPreviewMapFeed {
  if (!payload || typeof payload !== 'object') throw new RealPreviewMapFeedError('The private map feed returned an invalid response.');
  const envelope = payload as Record<string, unknown>;
  if (envelope.api_version !== 'real-preview-v1' || !Array.isArray(envelope.data) || !envelope.meta || typeof envelope.meta !== 'object') {
    throw new RealPreviewMapFeedError('The private map feed returned an invalid response.');
  }
  const meta = envelope.meta as Record<string, unknown>;
  if (meta.bounded !== true || meta.private_preview !== true || meta.scope !== 'default_map_scope' || meta.zoom_max !== 14
    || typeof meta.snapshot_id !== 'string' || !/^[a-f0-9]{64}$/.test(meta.snapshot_id)) {
    throw new RealPreviewMapFeedError('The private map feed did not confirm its private, bounded scope.');
  }
  const features: JsonMapFeature[] = envelope.data.map((value) => {
    if (!value || typeof value !== 'object') throw new RealPreviewMapFeedError('The private map feed returned an invalid feature.');
    const row = value as Record<string, unknown>;
    const kind = row.kind;
    const key = row.key;
    const weight = row.weight;
    if ((kind !== 'source_coordinate' && kind !== 'city_reference') || typeof key !== 'string' || !key || key.length > 160
      || typeof row.source_id !== 'string' || typeof row.precision !== 'string'
      || !finiteCoordinate(row.latitude, -90, 90) || !finiteCoordinate(row.longitude, -180, 180)
      || typeof weight !== 'number' || !Number.isSafeInteger(weight) || weight < 1) {
      throw new RealPreviewMapFeedError('The private map feed returned an invalid feature.');
    }
    const precision = row.precision;
    return {
      type: 'Feature',
      id: `${key}:${row.source_id}`,
      geometry: { type: 'Point', coordinates: [row.longitude, row.latitude] },
      properties: {
        key,
        source_id: row.source_id,
        kind: kind === 'city_reference' ? 'reference' : 'source-coordinate',
        precision,
        weight,
        // Only references need a latitude correction for the map-scale disc.
        ...(kind === 'city_reference' ? { cosLatitude: Math.max(0.087, Math.cos(row.latitude * Math.PI / 180)) } : {}),
      },
    };
  });
  return {
    collection: { type: 'FeatureCollection', features },
    snapshotId: meta.snapshot_id,
    cacheStatus: 'unavailable',
  };
}

const CACHE_NAME = 'uec-private-map-projection-v1';

function cacheKey(snapshotId: string, sourceId: string | null): string {
  const scope = sourceId ?? 'all';
  return `${location.origin}/__uec_private_map_cache__/${snapshotId}/${encodeURIComponent(scope)}`;
}

async function currentSnapshotId(fetcher: typeof fetch, signal?: AbortSignal): Promise<string> {
  const response = await fetcher('/dev/real-preview/counts', {
    credentials: 'same-origin', cache: 'no-store', ...(signal ? { signal } : {}),
  });
  if (!response.ok) throw new RealPreviewMapFeedError('The private preview snapshot identity could not be loaded.');
  const payload = await response.json() as { meta?: { snapshot_id?: unknown } };
  const value = payload.meta?.snapshot_id;
  if (typeof value !== 'string' || !/^[a-f0-9]{64}$/.test(value))
    throw new RealPreviewMapFeedError('The private preview snapshot identity was invalid.');
  return value;
}

export function createRealPreviewMapFeedRepository(fetcher: typeof fetch = fetch) {
  return {
    async load(sourceId: string | null, signal?: AbortSignal): Promise<RealPreviewMapFeed> {
      const params = new URLSearchParams();
      if (sourceId) params.set('source_id', sourceId);
      // Cache Storage is used only by the loopback development preview. The
      // small counts request supplies the current immutable snapshot identity,
      // so a changed import can never reuse an older full projection.
      let snapshotId: string | undefined;
      let projectionCache: Cache | undefined;
      if (typeof caches !== 'undefined' && typeof location !== 'undefined' && /^(localhost|127\.0\.0\.1)$/.test(location.hostname)) {
        snapshotId = await currentSnapshotId(fetcher, signal);
        projectionCache = await caches.open(CACHE_NAME);
        const cached = await projectionCache.match(cacheKey(snapshotId, sourceId));
        if (cached) {
          const parsed = parseRealPreviewMapFeed(await cached.json());
          if (parsed.snapshotId === snapshotId) return { ...parsed, cacheStatus: 'hit', decodedBytes: new TextEncoder().encode(JSON.stringify(parsed.collection)).byteLength };
        }
      }
      const response = await fetcher(`/dev/real-preview/map/feed${params.size ? `?${params}` : ''}`, {
        credentials: 'same-origin',
        cache: 'no-store',
        ...(signal ? { signal } : {}),
      });
      if (!response.ok) {
        const message = response.status === 401 || response.status === 403
          ? 'The private preview session is not authorized to load map locations.'
          : 'The private map feed could not be loaded.';
        throw new RealPreviewMapFeedError(message);
      }
      const payload = await response.json();
      const parsed = parseRealPreviewMapFeed(payload);
      if (snapshotId && parsed.snapshotId !== snapshotId)
        throw new RealPreviewMapFeedError('The private map projection changed while it was loading. Reload to use the new snapshot.');
      if (projectionCache && snapshotId) {
        await projectionCache.put(cacheKey(snapshotId, sourceId), new Response(JSON.stringify(payload), {
          headers: { 'content-type': 'application/json' },
        }));
        for (const request of await projectionCache.keys()) {
          if (!request.url.includes(`/__uec_private_map_cache__/${snapshotId}/`)) await projectionCache.delete(request);
        }
      }
      return { ...parsed, cacheStatus: projectionCache ? 'miss' : 'unavailable', decodedBytes: new TextEncoder().encode(JSON.stringify(parsed.collection)).byteLength };
    },
  };
}

export async function clearRealPreviewMapCache(): Promise<number> {
  if (typeof caches === 'undefined') return 0;
  const cache = await caches.open(CACHE_NAME);
  const entries = await cache.keys();
  await Promise.all(entries.map((request) => cache.delete(request)));
  return entries.length;
}

export async function realPreviewMapCacheEntryCount(): Promise<number | null> {
  if (typeof caches === 'undefined') return null;
  return (await (await caches.open(CACHE_NAME)).keys()).length;
}
