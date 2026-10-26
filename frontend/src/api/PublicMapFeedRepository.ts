import type { JsonMapCollection, JsonMapFeature } from '../design-lab/components/jsonMapFallback';
import type { LocalProfile } from './LocalLocationRepository';
import { PublicReleaseRepository, type PublicReleaseIdentity } from './PublicReleaseRepository';

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
    /** Diagnostic only: cache contents remain public-only and identity-validated. */
    cacheStatus?: 'hit' | 'miss' | 'unavailable';
    decodedBytes?: number;
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
const categoryIcon: Record<string, string> = {
  animal_keeping_and_production: 'v1-pin-green', slaughter: 'v1-pin-red',
  processing_and_preparation: 'v1-pin-grey', research_and_animal_use: 'v1-pin-violet',
  other_regulated_premises: 'v1-pin-orange', unclassified: 'v1-pin-grey',
};

type CompactFeed = Readonly<{ format: 'compact-v1'; dictionaries: Record<string, unknown>; features: unknown[] }>;
const isCompactFeed = (value: unknown): value is CompactFeed => isObject(value) && value.format === 'compact-v1' && isObject(value.dictionaries) && Array.isArray(value.features);

/** Expand the additive compact wire once, before the existing GeoJSON validator. */
function expandCompactFeed(data: CompactFeed): Record<string, unknown> {
  const sources = data.dictionaries.source_ids;
  const categories = data.dictionaries.category_keys;
  const precisions = data.dictionaries.precisions;
  if (!Array.isArray(sources) || !Array.isArray(categories) || !Array.isArray(precisions)) throw new PublicMapFeedError('The public map feed returned an invalid compact response.');
  const from = (values: unknown[], index: unknown) => Number.isInteger(index) && Number(index) >= 0 && Number(index) < values.length ? values[Number(index)] : undefined;
  const features = data.features.map(row => {
    if (!Array.isArray(row) || (row.length !== 7 && row.length !== 8)) throw new PublicMapFeedError('The public map feed returned an invalid compact feature.');
    const [id, longitude, latitude, source, category, categoryKeys, precision] = row;
    const facilityId = id;
    const sourceId = from(sources, source);
    const categoryKey = from(categories, category);
    const precisionValue = from(precisions, precision);
    if (!Array.isArray(categoryKeys)) throw new PublicMapFeedError('The public map feed returned an invalid compact feature.');
    return { type: 'Feature', id: facilityId, geometry: { type: 'Point', coordinates: [longitude, latitude] }, properties: {
      facility_id: facilityId, source_id: sourceId, category_key: categoryKey,
      category_keys: categoryKeys.map(index => from(categories, index)), precision: precisionValue, weight: 1,
      ...(row.length === 8 ? { country_code: row[7] } : {}),
    } };
  });
  return { type: 'FeatureCollection', features };
}

/** Validate the public map-only projection and copy only its allowlisted fields. */
export function parsePublicMapFeed(payload: unknown, profile: LocalProfile, releaseId: string): PublicMapFeed {
  if (!isObject(payload) || payload.api_version !== 'v2' || !isObject(payload.meta) || !isObject(payload.data)) throw new PublicMapFeedError('The public map feed returned an invalid response.');
  const collection = isCompactFeed(payload.data) ? expandCompactFeed(payload.data) : payload.data;
  if (collection.type !== 'FeatureCollection' || !Array.isArray(collection.features)) throw new PublicMapFeedError('The public map feed returned an invalid response.');
  const meta = payload.meta;
  const integer = (value: unknown) => Number.isSafeInteger(value) && Number(value) >= 0;
  if (meta.profile !== profile || meta.release_id !== releaseId || typeof meta.manifest_sha256 !== 'string' || !/^[a-f0-9]{64}$/.test(meta.manifest_sha256)
    || !integer(meta.suppression_generation) || !integer(meta.feature_count) || !integer(meta.public_record_count) || !integer(meta.unmapped_count)
    || typeof meta.release_label !== 'string' || typeof meta.dataset_version !== 'string'
    || meta.feature_count !== collection.features.length || Number(meta.feature_count) + Number(meta.unmapped_count) > Number(meta.public_record_count)) {
    throw new PublicMapFeedError('The public map feed did not confirm the selected release and its counts.');
  }
  const features: JsonMapFeature[] = collection.features.map(value => {
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
    // Approximate coordinates are display references, not facility pins.
    // Source-reported coordinates remain point features: their source origin
    // does not make them an independently verified exact location.
    const kind = precision === 'city' || precision === 'approximate' ? 'reference' : 'source-coordinate';
    return {
      type: 'Feature', id: value.id,
      geometry: { type: 'Point', coordinates: [longitude, latitude] },
      properties: {
        id: value.id, key: value.id, facility_id: value.id,
        source_id: props.source_id, kind, precision, weight: 1,
        ...(typeof props.country_code === 'string' && /^[A-Z]{2}$/.test(props.country_code) ? { country_code: props.country_code } : {}),
        category_key: props.category_key, category_keys: [...new Set(categoryKeys as string[])],
        icon: categoryIcon[props.category_key],
        // Reference circles use a ground-distance paint expression. Supply a
        // latitude factor for every reference, including non-city
        // approximations, instead of falling back to a fixed screen radius.
        ...(kind === 'reference' ? { cosLatitude: Math.max(0.087, Math.cos(latitude * Math.PI / 180)) } : {}),
      },
    };
  });
  return { collection: { type: 'FeatureCollection', features }, meta: {
    profile, releaseId, featureCount: Number(meta.feature_count), publicRecordCount: Number(meta.public_record_count),
    unmappedCount: Number(meta.unmapped_count), releaseLabel: meta.release_label, datasetVersion: meta.dataset_version,
    suppressionGeneration: Number(meta.suppression_generation), manifestSha256: meta.manifest_sha256,
  } };
}

const PUBLIC_CACHE_NAME = 'uec-public-map-projection-v2';
const PROJECTION_BYTES_HEADER = 'x-uec-projection-bytes';
const PROJECTION_METRIC_HEADER = 'x-uec-projection-metric';
const PROJECTION_METRIC_VERSION = '1';
function cachedProjectionBytes(response: Response): number | undefined {
  if (response.headers.get(PROJECTION_METRIC_HEADER) !== PROJECTION_METRIC_VERSION) return undefined;
  const value = Number(response.headers.get(PROJECTION_BYTES_HEADER));
  return Number.isSafeInteger(value) && value > 0 && value <= 256 * 1048576 ? value : undefined;
}
function markDecodedFeed(): void {
  // Aggregate phase timing only; never attach source rows or request context.
  try { globalThis.performance?.mark?.('uec-public-map-feed-decoded'); } catch { /* Timing is optional. */ }
}
const inFlight = new Map<string, Promise<PublicMapFeed>>();
const cacheKey = (identity: PublicReleaseIdentity, profile: LocalProfile) => {
  const path = `/__uec_public_map_cache__/${encodeURIComponent(profile)}/${encodeURIComponent(identity.releaseId)}/${identity.manifestSha256}/${identity.suppressionGeneration}`;
  return new Request(new URL(path, globalThis.location?.origin ?? 'https://uec.invalid').href, { method: 'GET' });
};

export async function clearPublicMapCache(): Promise<void> {
  if (!globalThis.caches) return;
  await caches.delete(PUBLIC_CACHE_NAME);
}

export async function publicMapCacheEntryCount(): Promise<number> {
  if (!globalThis.caches) return 0;
  return (await (await caches.open(PUBLIC_CACHE_NAME)).keys()).length;
}

async function trimPublicMapCache(cache: Cache, keep: Request): Promise<void> {
  const keys = await cache.keys();
  // Retain only the active projection, including when a restriction changes
  // without a new release. Historical releases can be fetched again explicitly.
  for (const key of keys) if (key.url !== keep.url) await cache.delete(key);
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

export function createPublicMapFeedRepository(fetcher: typeof fetch = globalThis.fetch) {
  return {
    async load(profile: LocalProfile, releaseId: string, signal?: AbortSignal, identity?: PublicReleaseIdentity): Promise<PublicMapFeed> {
      // A current identity is checked before Cache Storage is read. The caller can
      // supply the manifest it already fetched to avoid a duplicate request.
      const current = identity ?? await new PublicReleaseRepository(fetcher).current(profile, signal);
      if (!current || current.releaseId !== releaseId) throw new PublicMapFeedError('The selected public map release is no longer available.');
      const key = cacheKey(current, profile);
      const flightKey = `${profile}|${current.releaseId}|${current.manifestSha256}|${current.suppressionGeneration}`;
      const existing = inFlight.get(flightKey);
      if (existing) return abortIsolated(existing, signal);
      const work = (async (): Promise<PublicMapFeed> => {
      let projectionCache: Cache | undefined;
      try { if (globalThis.caches) {
        projectionCache = await caches.open(PUBLIC_CACHE_NAME);
        const cached = await projectionCache.match(key);
        if (cached) {
          try {
            const parsed = parsePublicMapFeed(await cached.json(), profile, releaseId);
            if (parsed.meta.manifestSha256 !== current.manifestSha256 || parsed.meta.suppressionGeneration !== current.suppressionGeneration) throw new PublicMapFeedError();
            markDecodedFeed();
            await trimPublicMapCache(projectionCache, key);
            // Reuse the once-measured diagnostic. Older entries can load with
            // this optional metric unavailable, without reserializing all points.
            const decodedBytes = cachedProjectionBytes(cached);
            return { ...parsed, meta: { ...parsed.meta, cacheStatus: 'hit', ...(decodedBytes === undefined ? {} : { decodedBytes }) } };
          } catch { await projectionCache.delete(key); }
        }
      } } catch { projectionCache = undefined; }
      const params = new URLSearchParams({ profile, release_id: releaseId, format: 'compact' });
      let response: Response;
      try { response = await fetcher.call(globalThis, `/api/v2/map/feed?${params}`, { method: 'GET', cache: 'no-store', credentials: 'omit', headers: { Accept: 'application/json' } }); }
      catch { throw new PublicMapFeedError(); }
      if (!response.ok) throw new PublicMapFeedError(response.status === 404 || response.status === 410 ? 'The selected public map release is no longer available.' : undefined);
      try {
        const payload = await response.json();
        const parsed = parsePublicMapFeed(payload, profile, releaseId);
        if (parsed.meta.manifestSha256 !== current.manifestSha256 || parsed.meta.suppressionGeneration !== current.suppressionGeneration) throw new PublicMapFeedError('The public map feed changed while it was loading.');
        markDecodedFeed();
        const decodedBytes = new TextEncoder().encode(JSON.stringify(parsed.collection)).byteLength;
        if (projectionCache) {
          try {
            await projectionCache.put(key, new Response(JSON.stringify(payload), { headers: { 'content-type': 'application/json',
              [PROJECTION_BYTES_HEADER]: String(decodedBytes), [PROJECTION_METRIC_HEADER]: PROJECTION_METRIC_VERSION } }));
            await trimPublicMapCache(projectionCache, key);
          } catch { projectionCache = undefined; }
        }
        return { ...parsed, meta: { ...parsed.meta, cacheStatus: projectionCache ? 'miss' : 'unavailable', decodedBytes } };
      }
      catch (error) { if (error instanceof PublicMapFeedError) throw error; throw new PublicMapFeedError('The public map feed returned invalid JSON.'); }
      })();
      inFlight.set(flightKey, work);
      const settled = () => { if (inFlight.get(flightKey) === work) inFlight.delete(flightKey); };
      void work.then(settled, settled);
      return abortIsolated(work, signal);
    },
  };
}
