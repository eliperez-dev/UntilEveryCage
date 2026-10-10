import type { JsonMapCollection, JsonMapFeature } from '../design-lab/components/jsonMapFallback';
import { isTaxonomyPrimaryKey } from '../domain/taxonomy';

export type RealPreviewMapFeed = Readonly<{
  collection: JsonMapCollection;
  snapshotId: string;
  cacheStatus: 'hit' | 'miss' | 'unavailable';
  decodedBytes?: number;
  previewLabel?: string;
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
export function parseRealPreviewMapFeed(payload: unknown, candidateOnly = false): RealPreviewMapFeed {
  if (!payload || typeof payload !== 'object') throw new RealPreviewMapFeedError('The private map feed returned an invalid response.');
  const envelope = payload as Record<string, unknown>;
  const rows = candidateOnly && envelope.data && typeof envelope.data === 'object' && !Array.isArray(envelope.data)
    ? (envelope.data as Record<string, unknown>).points
    : envelope.data;
  if ((candidateOnly ? envelope.api_version !== 'dev-test-v1' : envelope.api_version !== 'real-preview-v1') || !Array.isArray(rows) || !envelope.meta || typeof envelope.meta !== 'object') {
    throw new RealPreviewMapFeedError('The private map feed returned an invalid response.');
  }
  const meta = envelope.meta as Record<string, unknown>;
  const snapshotPattern = candidateOnly ? /^(?:[a-f0-9]{32}|[a-f0-9]{64})$/ : /^[a-f0-9]{64}$/;
  if (meta.bounded !== true || meta.private_preview !== true || meta.scope !== (candidateOnly ? 'candidate_map' : 'default_map_scope') || meta.zoom_max !== 14
    || typeof meta.snapshot_id !== 'string' || !snapshotPattern.test(meta.snapshot_id)) {
    throw new RealPreviewMapFeedError('The private map feed did not confirm its private, bounded scope.');
  }
  if (candidateOnly && (meta.candidate_only !== true || meta.test_only !== false || typeof meta.release_id !== 'string' || typeof meta.preview_label !== 'string')) {
    throw new RealPreviewMapFeedError('The corrected candidate map feed did not confirm its configured private boundary.');
  }
  const features: JsonMapFeature[] = rows.map((value) => {
    if (!value || typeof value !== 'object') throw new RealPreviewMapFeedError('The private map feed returned an invalid feature.');
    const row = value as Record<string, unknown>;
    const kind = row.kind;
    const key = row.key;
    const weight = row.weight;
    if (!['source_coordinate', 'city_reference', 'provider_address_point_private', 'provider_locality_approximate'].includes(String(kind)) || typeof key !== 'string' || !key || key.length > 160
      || typeof row.source_id !== 'string' || typeof row.precision !== 'string'
      || !finiteCoordinate(row.latitude, -90, 90) || !finiteCoordinate(row.longitude, -180, 180)
      || typeof weight !== 'number' || !Number.isSafeInteger(weight) || weight < 1) {
      throw new RealPreviewMapFeedError('The private map feed returned an invalid feature.');
    }
    if (row.category_key !== undefined && typeof row.category_key !== 'string') throw new RealPreviewMapFeedError('The private map feed returned an invalid category key.');
    if (row.category_keys !== undefined && (!Array.isArray(row.category_keys) || row.category_keys.length > 16 || !row.category_keys.every(item => typeof item === 'string'))) throw new RealPreviewMapFeedError('The private map feed returned invalid category keys.');
    if (candidateOnly && row.country_code !== undefined && row.country_code !== null && (typeof row.country_code !== 'string' || !/^[A-Z]{2}$/.test(row.country_code))) throw new RealPreviewMapFeedError('The corrected candidate map feed returned an invalid country code.');
    if (candidateOnly && row.activity_keys !== undefined && (!Array.isArray(row.activity_keys) || row.activity_keys.length > 64 || !row.activity_keys.every(item => typeof item === 'string' && item.length > 0 && item.length <= 240))) throw new RealPreviewMapFeedError('The corrected candidate map feed returned invalid activity keys.');
    const categoryKeys = [...new Set(((row.category_keys as string[] | undefined) ?? []).map(item => isTaxonomyPrimaryKey(item) ? item : 'unclassified'))];
    if (categoryKeys.length === 0) categoryKeys.push(isTaxonomyPrimaryKey(row.category_key) ? row.category_key : 'unclassified');
    const categoryKey = typeof row.category_key === 'string' ? row.category_key : categoryKeys[0]!;
    const precision = row.precision;
    return {
      type: 'Feature',
      id: `${key}:${row.source_id}`,
      geometry: { type: 'Point', coordinates: [row.longitude, row.latitude] },
      properties: {
        key,
        source_id: row.source_id,
        kind: kind === 'city_reference' ? 'reference' : kind === 'source_coordinate' ? 'source-coordinate' : String(kind),
        precision,
        weight,
        category_key: categoryKey,
        category_keys: categoryKeys,
        ...(candidateOnly && (typeof row.country_code === 'string' || row.country_code === null) ? { country_code: row.country_code } : {}),
        ...(candidateOnly && Array.isArray(row.activity_keys) ? { activity_keys: [...new Set(row.activity_keys as string[])] } : {}),
        // Only references need a latitude correction for the map-scale disc.
        ...(kind === 'city_reference' ? { cosLatitude: Math.max(0.087, Math.cos(row.latitude * Math.PI / 180)) } : {}),
      },
    };
  });
  return {
    collection: { type: 'FeatureCollection', features },
    snapshotId: meta.snapshot_id,
    cacheStatus: 'unavailable',
    ...(candidateOnly ? { previewLabel: meta.preview_label as string } : {}),
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
