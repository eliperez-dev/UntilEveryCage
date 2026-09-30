import type { JsonMapCollection, JsonMapFeature } from '../design-lab/components/jsonMapFallback';

export type RealPreviewMapFeed = Readonly<{
  collection: JsonMapCollection;
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
  if (meta.bounded !== true || meta.private_preview !== true || meta.scope !== 'default_map_scope' || meta.zoom_max !== 14) {
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
  };
}

export function createRealPreviewMapFeedRepository(fetcher: typeof fetch = fetch) {
  return {
    async load(sourceId: string | null, signal?: AbortSignal): Promise<RealPreviewMapFeed> {
      const params = new URLSearchParams();
      if (sourceId) params.set('source_id', sourceId);
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
      return parseRealPreviewMapFeed(await response.json());
    },
  };
}
