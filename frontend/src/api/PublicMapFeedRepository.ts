import type { JsonMapCollection, JsonMapFeature } from '../design-lab/components/jsonMapFallback';
import type { LocalProfile } from './LocalLocationRepository';

export type PublicMapFeed = Readonly<{
  collection: JsonMapCollection;
  meta: Readonly<{
    profile: LocalProfile;
    releaseId: string;
    featureCount: number;
    publicRecordCount: number;
    unmappedCount: number;
    releaseLabel: string;
    datasetVersion: string;
    suppressionGeneration: number;
    manifestSha256: string;
  }>;
}>;

export class PublicMapFeedError extends Error {
  constructor(message = 'The public map feed could not be loaded.') { super(message); this.name = 'PublicMapFeedError'; }
}

/** Reuse a map projection only when its public release and suppression identity still match. */
export function canReusePublicMapFeed(
  currentReleaseId: string | null | undefined,
  currentIdentity: string | null | undefined,
  loadedReleaseId: string | null | undefined,
  loadedIdentity: string | null | undefined,
  hasCollection: boolean,
): boolean {
  return !!currentReleaseId && hasCollection
    && currentReleaseId === loadedReleaseId
    && currentIdentity === loadedIdentity;
}

const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const categories = new Set(['animal_keeping_and_production', 'slaughter', 'processing_and_preparation', 'research_and_animal_use', 'other_regulated_premises', 'unclassified']);
const precisions = new Set(['source_reported', 'exact', 'approximate', 'city']);
const isObject = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value);

/** Validate the public map-only projection and copy only its allowlisted fields. */
export function parsePublicMapFeed(payload: unknown, profile: LocalProfile, releaseId: string): PublicMapFeed {
  if (!isObject(payload) || payload.api_version !== 'v2' || !isObject(payload.meta) || !isObject(payload.data)
    || payload.data.type !== 'FeatureCollection' || !Array.isArray(payload.data.features)) throw new PublicMapFeedError('The public map feed returned an invalid response.');
  const meta = payload.meta;
  const integer = (value: unknown) => Number.isSafeInteger(value) && Number(value) >= 0;
  if (meta.profile !== profile || meta.release_id !== releaseId || typeof meta.manifest_sha256 !== 'string' || !/^[a-f0-9]{64}$/.test(meta.manifest_sha256)
    || !integer(meta.suppression_generation) || !integer(meta.feature_count) || !integer(meta.public_record_count) || !integer(meta.unmapped_count)
    || typeof meta.release_label !== 'string' || typeof meta.dataset_version !== 'string'
    || meta.feature_count !== payload.data.features.length || Number(meta.feature_count) + Number(meta.unmapped_count) > Number(meta.public_record_count)) {
    throw new PublicMapFeedError('The public map feed did not confirm the selected release and its counts.');
  }
  const features: JsonMapFeature[] = payload.data.features.map(value => {
    if (!isObject(value) || !isObject(value.geometry) || value.geometry.type !== 'Point' || !Array.isArray(value.geometry.coordinates)
      || !isObject(value.properties)) throw new PublicMapFeedError('The public map feed returned an invalid feature.');
    const props = value.properties;
    const [longitude, latitude] = value.geometry.coordinates;
    const categoryKeys = props.category_keys;
    if (typeof value.id !== 'string' || !uuid.test(value.id) || props.facility_id !== value.id
      || typeof props.source_id !== 'string' || !props.source_id || props.source_id.length > 160
      || typeof longitude !== 'number' || !Number.isFinite(longitude) || longitude < -180 || longitude > 180
      || typeof latitude !== 'number' || !Number.isFinite(latitude) || latitude < -90 || latitude > 90
      || typeof props.precision !== 'string' || !precisions.has(props.precision)
      || typeof props.weight !== 'number' || props.weight !== 1
      || typeof props.category_key !== 'string' || !categories.has(props.category_key)
      || !Array.isArray(categoryKeys) || categoryKeys.length > 16 || !categoryKeys.every(item => typeof item === 'string' && categories.has(item))) {
      throw new PublicMapFeedError('The public map feed returned an invalid feature.');
    }
    const precision = props.precision;
    const kind = precision === 'city' ? 'reference' : 'source-coordinate';
    return {
      type: 'Feature', id: value.id,
      geometry: { type: 'Point', coordinates: [longitude, latitude] },
      properties: {
        id: value.id, key: value.id, facility_id: value.id,
        source_id: props.source_id, kind, precision, weight: 1,
        category_key: props.category_key, category_keys: [...new Set(categoryKeys as string[])],
        ...(precision === 'city' ? { cosLatitude: Math.max(0.087, Math.cos(latitude * Math.PI / 180)) } : {}),
      },
    };
  });
  return { collection: { type: 'FeatureCollection', features }, meta: {
    profile, releaseId, featureCount: Number(meta.feature_count), publicRecordCount: Number(meta.public_record_count),
    unmappedCount: Number(meta.unmapped_count), releaseLabel: meta.release_label, datasetVersion: meta.dataset_version,
    suppressionGeneration: Number(meta.suppression_generation), manifestSha256: meta.manifest_sha256,
  } };
}

export function createPublicMapFeedRepository(fetcher: typeof fetch = globalThis.fetch) {
  return {
    async load(profile: LocalProfile, releaseId: string, signal?: AbortSignal): Promise<PublicMapFeed> {
      const params = new URLSearchParams({ profile, release_id: releaseId });
      let response: Response;
      try { response = await fetcher.call(globalThis, `/api/v2/map/feed?${params}`, { method: 'GET', cache: 'no-store', credentials: 'omit', headers: { Accept: 'application/json' }, ...(signal ? { signal } : {}) }); }
      catch (error) { if (signal?.aborted) throw error; throw new PublicMapFeedError(); }
      if (!response.ok) throw new PublicMapFeedError(response.status === 404 || response.status === 410 ? 'The selected public map release is no longer available.' : undefined);
      try { return parsePublicMapFeed(await response.json(), profile, releaseId); }
      catch (error) { if (error instanceof PublicMapFeedError) throw error; throw new PublicMapFeedError('The public map feed returned invalid JSON.'); }
    },
  };
}
