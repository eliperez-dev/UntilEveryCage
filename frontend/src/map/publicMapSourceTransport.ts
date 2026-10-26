import { publicIndexIdentity } from './clusterIndexCache';

export const PUBLIC_MAP_TRANSPORT_FIELD = 'uec_public_geojson_transport_v1';
const MAX_TEXT_LENGTH = 64 * 1024 * 1024;
type Parameters = { source?: string; data?: unknown };
export type PublicTransportPrototype = {
  _getLoadGeoJSONParameters(...args: unknown[]): Promise<Parameters | undefined>;
};
type Envelope = { type: 'FeatureCollection'; features: []; [PUBLIC_MAP_TRANSPORT_FIELD]: string; encodeMs: number };

function object(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}
function scalar(value: unknown): boolean {
  return value === null || typeof value === 'string' || typeof value === 'boolean'
    || (typeof value === 'number' && Number.isFinite(value) && !Object.is(value, -0));
}
function eligible(data: unknown): data is Record<string, unknown> & { features: unknown[] } {
  if (!object(data) || data.type !== 'FeatureCollection' || !Array.isArray(data.features)
    || data.features.length < 1000 || data.features.length > 250_000 || !publicIndexIdentity(data.uec_public_index)) return false;
  for (const feature of data.features) {
    if (!object(feature) || feature.type !== 'Feature' || typeof feature.id !== 'string'
      || !object(feature.geometry) || feature.geometry.type !== 'Point' || !Array.isArray(feature.geometry.coordinates)
      || feature.geometry.coordinates.length !== 2 || !feature.geometry.coordinates.every(Number.isFinite)
      || !object(feature.properties) || Object.getPrototypeOf(feature.properties) !== Object.prototype) return false;
    for (const value of Object.values(feature.properties)) {
      if (scalar(value)) continue;
      if (!Array.isArray(value) || Object.getPrototypeOf(value) !== Array.prototype || !value.every(scalar)) return false;
    }
  }
  return true;
}

/** Only outgoing worker parameters change; native main-thread data stays intact. */
export function encodePublicMapTransport(data: unknown): unknown {
  const started = performance.now();
  try {
    if (!eligible(data)) return data;
    const json = JSON.stringify(data);
    if (json.length > MAX_TEXT_LENGTH) return data;
    return { type: 'FeatureCollection', features: [], [PUBLIC_MAP_TRANSPORT_FIELD]: json,
      encodeMs: performance.now() - started } satisfies Envelope;
  } catch { return data; }
}

export function decodePublicMapTransport(data: unknown): { data: unknown; encodeMs: number; parseMs: number } {
  if (!object(data) || !(PUBLIC_MAP_TRANSPORT_FIELD in data)) return { data, encodeMs: 0, parseMs: 0 };
  const text = data[PUBLIC_MAP_TRANSPORT_FIELD];
  if (data.type !== 'FeatureCollection' || !Array.isArray(data.features) || data.features.length !== 0
    || typeof text !== 'string' || text.length > MAX_TEXT_LENGTH) throw new Error('Invalid public map transport');
  const started = performance.now();
  const decoded: unknown = JSON.parse(text);
  if (!object(decoded) || decoded.type !== 'FeatureCollection' || !Array.isArray(decoded.features)
    || decoded.features.length > 250_000 || !publicIndexIdentity(decoded.uec_public_index)) throw new Error('Invalid public map transport');
  return { data: decoded, encodeMs: typeof data.encodeMs === 'number' && Number.isFinite(data.encodeMs)
    && data.encodeMs >= 0 && data.encodeMs < 60_000 ? data.encodeMs : 0, parseMs: performance.now() - started };
}

const installed = new WeakSet<object>();
/** The matching engine version is checked by the frontend build gate. */
export function installPublicMapTransport(prototype: PublicTransportPrototype): boolean {
  if (installed.has(prototype)) return true;
  const original = prototype._getLoadGeoJSONParameters;
  if (typeof original !== 'function') return false;
  installed.add(prototype);
  prototype._getLoadGeoJSONParameters = async function(...args) {
    const parameters = await original.apply(this, args);
    if (parameters?.source === 'locations' && parameters.data) parameters.data = encodePublicMapTransport(parameters.data);
    return parameters;
  };
  return true;
}
