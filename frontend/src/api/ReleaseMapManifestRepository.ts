export type ReleaseProfile = 'official' | 'secondary' | 'community';

export type ReleaseMapManifest = Readonly<{
  schemaVersion: string;
  releaseId: string;
  profile: ReleaseProfile;
  generatedAt: string;
  suppressionGeneration: string | number;
  attribution: readonly string[];
  bounds: readonly [number, number, number, number];
  minZoom: number;
  maxZoom: number;
  tileUrlTemplate: string;
  sourceLayer: 'uec_map';
  featureSchemaVersion: string;
  hashes: Readonly<Record<string, string>>;
  etags: Readonly<Record<string, string>>;
  cachePolicy: Readonly<Record<string, string | number | boolean>>;
}>;

export class ReleaseMapManifestError extends Error {
  constructor(readonly kind: 'network' | 'unavailable' | 'invalid-contract', message: string) {
    super(message);
    this.name = 'ReleaseMapManifestError';
  }
}

type FetchLike = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
const PROFILES = new Set<ReleaseProfile>(['official', 'secondary', 'community']);
const SHA256 = /^[a-f0-9]{64}$/i;

function record(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : null;
}

function nonempty(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0;
}

function stringMap(value: unknown, hashes = false): Readonly<Record<string, string>> | null {
  const row = record(value);
  if (!row || Object.keys(row).length === 0) return null;
  const entries = Object.entries(row);
  if (!entries.every(([key, item]) => nonempty(key) && nonempty(item) && (!hashes || SHA256.test(item)))) return null;
  return Object.freeze(Object.fromEntries(entries) as Record<string, string>);
}

function cacheMap(value: unknown): Readonly<Record<string, string | number | boolean>> | null {
  const row = record(value);
  if (!row || Object.keys(row).length === 0) return null;
  if (!Object.entries(row).every(([key, item]) => nonempty(key) && (
    nonempty(item) || typeof item === 'boolean' || (typeof item === 'number' && Number.isSafeInteger(item) && item >= 0)
  ))) return null;
  return Object.freeze(row as Record<string, string | number | boolean>);
}

function parseArtifact(value: unknown, releaseId: string, profile: ReleaseProfile, currentGeneration: string | number): ReleaseMapManifest | null {
  const row = record(value);
  if (!row) throw new ReleaseMapManifestError('invalid-contract', 'The public map manifest was invalid.');
  if (row.eligible === false || row.status === 'ineligible') return null;
  if ((row.eligible !== undefined && row.eligible !== true)
    || (row.status !== undefined && row.status !== 'eligible')) throw new ReleaseMapManifestError('invalid-contract', 'The map manifest eligibility was invalid.');
  if (String(row.suppression_generation) !== String(currentGeneration)) return null;
  const bounds = row.bounds;
  const hashes = stringMap(row.hashes, true);
  const etags = stringMap(row.etags);
  const cachePolicy = cacheMap(row.cache_policy);
  const attribution = row.attribution;
  if (!nonempty(row.schema_version) || row.release_id !== releaseId || row.profile !== profile
    || !nonempty(row.generated_at) || !Number.isFinite(Date.parse(row.generated_at))
    || !(nonempty(row.suppression_generation) || (typeof row.suppression_generation === 'number' && Number.isSafeInteger(row.suppression_generation) && row.suppression_generation >= 0))
    || !Array.isArray(attribution) || attribution.length === 0 || !attribution.every(nonempty)
    || !Array.isArray(bounds) || bounds.length !== 4 || !bounds.every(item => typeof item === 'number' && Number.isFinite(item))
    || bounds[0] < -180 || bounds[2] > 180 || bounds[0] >= bounds[2] || bounds[1] < -90 || bounds[3] > 90 || bounds[1] >= bounds[3]
    || typeof row.min_zoom !== 'number' || !Number.isFinite(row.min_zoom) || row.min_zoom < 0
    || typeof row.max_zoom !== 'number' || !Number.isFinite(row.max_zoom) || row.max_zoom < row.min_zoom
    || !nonempty(row.tile_url_template) || row.source_layer !== 'uec_map' || !nonempty(row.feature_schema_version)
    || !hashes || !etags || !cachePolicy) {
    throw new ReleaseMapManifestError('invalid-contract', 'The public map manifest was rejected safely.');
  }
  const tileUrlTemplate = row.tile_url_template as string;
  let tile: URL;
  try {
    const resolved = tileUrlTemplate.replaceAll('{z}', '0').replaceAll('{x}', '0').replaceAll('{y}', '0');
    tile = new URL(resolved, globalThis.location?.origin ?? 'http://localhost');
  } catch { throw new ReleaseMapManifestError('invalid-contract', 'The map tile URL was invalid.'); }
  const origin = globalThis.location?.origin ?? 'http://localhost';
  if (tile.origin !== origin || tile.username || tile.password || tile.protocol !== new URL(origin).protocol
    || !['{z}', '{x}', '{y}'].every(token => tileUrlTemplate.includes(token))
    || /\{(?!z\}|x\}|y\})[^}]*\}/.test(tileUrlTemplate)) {
    throw new ReleaseMapManifestError('invalid-contract', 'The map tile URL must be a same-origin XYZ template.');
  }
  return Object.freeze({
    schemaVersion: row.schema_version, releaseId, profile, generatedAt: row.generated_at,
    suppressionGeneration: row.suppression_generation as string | number,
    attribution: Object.freeze([...attribution]), bounds: Object.freeze([...bounds]) as unknown as ReleaseMapManifest['bounds'],
    minZoom: row.min_zoom, maxZoom: row.max_zoom, tileUrlTemplate,
    sourceLayer: 'uec_map', featureSchemaVersion: row.feature_schema_version,
    hashes, etags, cachePolicy,
  });
}

export function parseReleaseMapManifest(payload: unknown, expectedReleaseId?: string, expectedProfile?: ReleaseProfile): ReleaseMapManifest | null {
  const envelope = record(payload);
  const data = record(envelope?.data);
  if (!envelope || envelope.api_version !== 'v2' || !data || !nonempty(data.release_id)
    || typeof data.profile !== 'string' || !PROFILES.has(data.profile as ReleaseProfile)
    || !nonempty(data.manifest_sha256) || !SHA256.test(data.manifest_sha256)
    || !(nonempty(data.suppression_generation) || (typeof data.suppression_generation === 'number' && Number.isSafeInteger(data.suppression_generation) && data.suppression_generation >= 0))) {
    throw new ReleaseMapManifestError('invalid-contract', 'The release manifest response was rejected safely.');
  }
  const profile = data.profile as ReleaseProfile;
  if ((expectedReleaseId !== undefined && data.release_id !== expectedReleaseId)
    || (expectedProfile !== undefined && profile !== expectedProfile)) {
    throw new ReleaseMapManifestError('invalid-contract', 'The release manifest did not match the selected release and profile.');
  }
  const manifest = record(data.manifest);
  if (!manifest) throw new ReleaseMapManifestError('invalid-contract', 'The release manifest body was invalid.');
  const artifact = manifest.map_artifact;
  if (artifact === undefined || artifact === null) return null;
  return parseArtifact(artifact, data.release_id, profile, data.suppression_generation);
}

/** Reads only the public release manifest. Network or validation failure never selects private preview data. */
export class ReleaseMapManifestRepository {
  constructor(private readonly fetcher: FetchLike = globalThis.fetch) {}

  async load(profile: ReleaseProfile = 'official', signal?: AbortSignal, expectedReleaseId?: string): Promise<ReleaseMapManifest | null> {
    if (!PROFILES.has(profile)) throw new ReleaseMapManifestError('invalid-contract', 'The selected release profile is invalid.');
    let response: Response;
    try {
      response = await this.fetcher.call(globalThis, `/api/v2/releases/manifest?profile=${encodeURIComponent(profile)}`, {
        method: 'GET', cache: 'no-store', headers: { Accept: 'application/json' }, ...(signal ? { signal } : {}),
      });
    } catch (error) {
      if (signal?.aborted) throw error;
      throw new ReleaseMapManifestError('network', 'The public release manifest could not be revalidated.');
    }
    if (response.status === 304) throw new ReleaseMapManifestError('invalid-contract', 'A not-modified response cannot confirm current map suppression state.');
    if (!response.ok) throw new ReleaseMapManifestError(response.status >= 500 ? 'unavailable' : 'invalid-contract', 'The public release manifest is unavailable.');
    let payload: unknown;
    try { payload = await response.json(); } catch { throw new ReleaseMapManifestError('invalid-contract', 'The public release manifest was not valid JSON.'); }
    return parseReleaseMapManifest(payload, expectedReleaseId, profile);
  }
}
