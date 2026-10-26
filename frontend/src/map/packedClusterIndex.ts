import { CLUSTER_INDEX_CODEC_VERSION, type ClusterIndexSnapshot } from './clusterIndexCodec';

export const PACKED_CLUSTER_INDEX_VERSION = 'uec-packed-cluster-index-v1';
export const COMPRESSED_CLUSTER_INDEX_VERSION = 'uec-compressed-cluster-index-v1';
export const REFERENCED_CLUSTER_INDEX_VERSION = 'uec-referenced-cluster-index-v1';
const MAX_BYTES = 128 * 1024 * 1024;
const MAX_STORED_BYTES = 64 * 1024 * 1024;
const MAX_JSON_BYTES = 64 * 1024 * 1024;
const MAX_BUFFERS = 52;
const arrayBufferLength = Object.getOwnPropertyDescriptor(ArrayBuffer.prototype, 'byteLength')!.get!;
export type PackedIndex = { format: typeof PACKED_CLUSTER_INDEX_VERSION; json: string; buffers: ArrayBuffer[] };
export type CompressedPackedIndex = { format: typeof COMPRESSED_CLUSTER_INDEX_VERSION; jsonGzip: ArrayBuffer; jsonBytes: number; buffers: ArrayBuffer[] };
export type ReferencedPackedIndex = { format: typeof REFERENCED_CLUSTER_INDEX_VERSION; json: string; buffers: ArrayBuffer[]; pointCount: number; inputCount: number };
export type StoredPackedIndex = PackedIndex | CompressedPackedIndex | ReferencedPackedIndex;
export class PackedIndexError extends Error {
  constructor(readonly reason: 'cache-limit' | 'compression-unavailable') { super(reason); }
}

function bufferLength(value: unknown): number | null {
  try { const length = Number(arrayBufferLength.call(value)); return Number.isSafeInteger(length) ? length : null; }
  catch { return null; }
}

function object(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function validEnvelope(value: unknown): value is PackedIndex {
  if (!object(value) || value.format !== PACKED_CLUSTER_INDEX_VERSION || typeof value.json !== 'string'
    || value.json.length > MAX_BYTES / 2 || !Array.isArray(value.buffers) || value.buffers.length > MAX_BUFFERS) return false;
  let bytes = value.json.length * 2;
  for (const buffer of value.buffers) {
    const length = bufferLength(buffer);
    if (length === null || length < 8) return false;
    bytes += length;
    if (bytes > MAX_BYTES) return false;
  }
  return true;
}

/** Keep large object graphs out of IndexedDB's structured-clone path. */
export function packClusterIndex(snapshot: ClusterIndexSnapshot): PackedIndex {
  const buffers: ArrayBuffer[] = [];
  const trees = snapshot.trees.map(tree => {
    if (!tree) return null;
    const buffer = buffers.push(tree.buffer) - 1;
    const values = tree.flatData;
    const flatData = buffers.push(values.buffer.slice(values.byteOffset, values.byteOffset + values.byteLength) as ArrayBuffer) - 1;
    return { buffer, flatData };
  });
  const result: PackedIndex = { format: PACKED_CLUSTER_INDEX_VERSION,
    json: JSON.stringify({ codec: snapshot.codec, options: snapshot.options, points: snapshot.points,
      stride: snapshot.stride, clusterProps: snapshot.clusterProps, trees }), buffers };
  if (!validEnvelope(result)) throw new PackedIndexError('cache-limit');
  return result;
}

export function storedClusterIndexBytes(value: StoredPackedIndex): number {
  return value.buffers.reduce((bytes, buffer) => bytes + buffer.byteLength, 0)
    + (value.format === COMPRESSED_CLUSTER_INDEX_VERSION ? value.jsonGzip.byteLength : value.json.length * 2);
}

type InputFeature = { id: string | number; geometry: { type: 'Point'; coordinates: number[] }; properties: Record<string, unknown> };
function inputFeature(value: unknown): value is InputFeature {
  if (!object(value) || (typeof value.id !== 'string' && typeof value.id !== 'number') || !object(value.geometry)
    || value.geometry.type !== 'Point' || !Array.isArray(value.geometry.coordinates) || !object(value.properties)) return false;
  const [longitude, latitude] = value.geometry.coordinates;
  return Number.isFinite(longitude) && Number.isFinite(latitude) && Math.abs(Number(longitude)) <= 180 && Math.abs(Number(latitude)) <= 90;
}

/** Repeated point tags already exist in the identity-hashed current input. */
function referenceClusterIndex(snapshot: ClusterIndexSnapshot, input: readonly unknown[]): ReferencedPackedIndex | null {
  const tags = new Map<object, number>();
  for (let index = 0; index < input.length; index++) {
    const feature = input[index];
    if (!inputFeature(feature)) return null;
    tags.set(feature.properties, index);
  }
  const coordinates = new Float64Array(snapshot.points.length * 2);
  const references = new Uint32Array(snapshot.points.length);
  for (let index = 0; index < snapshot.points.length; index++) {
    const point = snapshot.points[index]!;
    const reference = point.tags ? tags.get(point.tags) : undefined;
    if (reference === undefined) return null;
    const feature = input[reference] as InputFeature;
    const x = point.geometry[0]!, y = point.geometry[1]!;
    if (point.id !== feature.id || point.geometry.length !== 3 || point.geometry[2] !== 0
      || point.minX !== x || point.maxX !== x || point.minY !== y || point.maxY !== y
      || Object.keys(point).some(key => !['id', 'type', 'geometry', 'tags', 'minX', 'minY', 'maxX', 'maxY'].includes(key))) return null;
    coordinates[index * 2] = x; coordinates[index * 2 + 1] = y; references[index] = reference;
  }
  const packed = packClusterIndex({ ...snapshot, points: [] });
  return { format: REFERENCED_CLUSTER_INDEX_VERSION, json: packed.json,
    buffers: [...packed.buffers, coordinates.buffer, references.buffer], pointCount: snapshot.points.length, inputCount: input.length };
}

function restoreReferencedClusterIndex(payload: Record<string, unknown>, input: readonly unknown[] | undefined, limit: number): unknown | null {
  if (!input || payload.inputCount !== input.length || !Number.isSafeInteger(payload.pointCount) || Number(payload.pointCount) < 1
    || Number(payload.pointCount) > 250_000 || typeof payload.json !== 'string' || !Array.isArray(payload.buffers)
    || payload.buffers.length < 2 || payload.buffers.length > MAX_BUFFERS + 2) return null;
  let bytes = payload.json.length * 2;
  for (const buffer of payload.buffers) {
    const length = bufferLength(buffer);
    if (length === null || length < 8) return null;
    bytes += length;
  }
  if (bytes > limit) return null;
  const buffers = payload.buffers as ArrayBuffer[];
  const pointCount = Number(payload.pointCount);
  const coordinateBuffer = buffers[buffers.length - 2]!, referenceBuffer = buffers[buffers.length - 1]!;
  if (coordinateBuffer.byteLength !== pointCount * 16 || referenceBuffer.byteLength !== pointCount * 4) return null;
  const snapshot = unpackClusterIndex({ format: PACKED_CLUSTER_INDEX_VERSION, json: payload.json, buffers: buffers.slice(0, -2) });
  if (!object(snapshot) || !Array.isArray(snapshot.points) || snapshot.points.length !== 0) return null;
  const coordinates = new Float64Array(coordinateBuffer), references = new Uint32Array(referenceBuffer);
  const points: ClusterIndexSnapshot['points'] = new Array(pointCount);
  for (let index = 0; index < pointCount; index++) {
    const feature = input[references[index]!];
    if (!inputFeature(feature)) return null;
    const x = coordinates[index * 2]!, y = coordinates[index * 2 + 1]!;
    const [longitude, latitude] = feature.geometry.coordinates;
    const projectedX = longitude! / 360 + .5;
    const sin = Math.sin(latitude! * Math.PI / 180);
    const projectedY = Math.max(0, Math.min(1, .5 - .25 * Math.log((1 + sin) / (1 - sin)) / Math.PI));
    // Include the exact wrapped world copies made by the pinned native engine.
    if (!(x === projectedX || x === projectedX - 1 || x === projectedX + 1) || y !== projectedY) return null;
    points[index] = { id: feature.id, type: 'Point', geometry: [x, y, 0], tags: feature.properties,
      minX: x, maxX: x, minY: y, maxY: y };
  }
  return { ...snapshot, points };
}

/** Capture synchronously, then compress repeated public properties off-thread. */
export async function encodeStoredClusterIndex(snapshot: ClusterIndexSnapshot, currentInput?: readonly unknown[]): Promise<StoredPackedIndex> {
  if (currentInput) {
    const referenced = referenceClusterIndex(snapshot, currentInput);
    if (referenced && storedClusterIndexBytes(referenced) <= MAX_STORED_BYTES) return referenced;
  }
  const packed = packClusterIndex(snapshot);
  if (storedClusterIndexBytes(packed) <= 8 * 1024 * 1024) return packed;
  if (typeof CompressionStream === 'undefined') {
    if (storedClusterIndexBytes(packed) <= MAX_STORED_BYTES) return packed;
    throw new PackedIndexError('compression-unavailable');
  }
  const blob = new Blob([packed.json]);
  if (blob.size > MAX_JSON_BYTES) throw new PackedIndexError('cache-limit');
  const jsonGzip = await new Response(blob.stream().pipeThrough(new CompressionStream('gzip'))).arrayBuffer();
  const result: CompressedPackedIndex = { format: COMPRESSED_CLUSTER_INDEX_VERSION,
    jsonGzip, jsonBytes: blob.size, buffers: packed.buffers };
  if (storedClusterIndexBytes(result) > MAX_STORED_BYTES) throw new PackedIndexError('cache-limit');
  return result;
}

/** Limit inflation before joining or parsing the decoded JSON string. */
export async function decodeStoredClusterIndex(payload: unknown, maxStoredBytes = MAX_STORED_BYTES, onTiming?: (timing: { inflateMs: number; parseMs: number }) => void, currentInput?: readonly unknown[]): Promise<unknown | null> {
  if (!Number.isFinite(maxStoredBytes) || maxStoredBytes < 1) return null;
  const limit = Math.min(MAX_STORED_BYTES, maxStoredBytes);
  if (object(payload) && payload.format === REFERENCED_CLUSTER_INDEX_VERSION) {
    const started = performance.now();
    const result = restoreReferencedClusterIndex(payload, currentInput, limit);
    onTiming?.({ inflateMs: 0, parseMs: performance.now() - started });
    return result;
  }
  if (object(payload) && payload.format === PACKED_CLUSTER_INDEX_VERSION) {
    const started = performance.now();
    const result = validEnvelope(payload) && storedClusterIndexBytes(payload) <= limit ? unpackClusterIndex(payload) : null;
    onTiming?.({ inflateMs: 0, parseMs: performance.now() - started });
    return result;
  }
  try {
    if (!object(payload) || payload.format !== COMPRESSED_CLUSTER_INDEX_VERSION
      || !Number.isSafeInteger(payload.jsonBytes) || Number(payload.jsonBytes) < 1 || Number(payload.jsonBytes) > MAX_JSON_BYTES
      || !Array.isArray(payload.buffers) || payload.buffers.length > MAX_BUFFERS
      || typeof DecompressionStream === 'undefined') return null;
    const gzipBytes = bufferLength(payload.jsonGzip);
    if (gzipBytes === null || gzipBytes < 8) return null;
    let storedBytes = gzipBytes;
    for (const buffer of payload.buffers) {
      const length = bufferLength(buffer);
      if (length === null || length < 8) return null;
      storedBytes += length;
    }
    if (storedBytes > limit) return null;
    const started = performance.now();
    const reader = new Blob([payload.jsonGzip as ArrayBuffer]).stream().pipeThrough(new DecompressionStream('gzip')).getReader();
    const decoder = new TextDecoder('utf-8', { fatal: true });
    const pieces: string[] = [];
    let decodedBytes = 0;
    try {
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        decodedBytes += value.byteLength;
        if (decodedBytes > Number(payload.jsonBytes) || decodedBytes > MAX_JSON_BYTES) { await reader.cancel(); return null; }
        pieces.push(decoder.decode(value, { stream: true }));
      }
    } finally { reader.releaseLock(); }
    if (decodedBytes !== payload.jsonBytes) return null;
    pieces.push(decoder.decode());
    const json = pieces.join('');
    const inflated = performance.now();
    const result = unpackClusterIndex({ format: PACKED_CLUSTER_INDEX_VERSION, json, buffers: payload.buffers });
    onTiming?.({ inflateMs: inflated - started, parseMs: performance.now() - inflated });
    return result;
  } catch { return null; }
}

/** Decode the transport envelope. The index codec validates all engine fields. */
export function unpackClusterIndex(payload: unknown): unknown | null {
  try {
    if (!validEnvelope(payload)) return null;
    const value: unknown = JSON.parse(payload.json);
    if (!object(value) || value.codec !== CLUSTER_INDEX_CODEC_VERSION || typeof value.options !== 'string'
      || value.options.length > 4096 || ![6, 7].includes(Number(value.stride))
      || !Array.isArray(value.points) || value.points.length > 250_000
      || !Array.isArray(value.clusterProps) || value.clusterProps.length > 500_000
      || !Array.isArray(value.trees) || value.trees.length < 2 || value.trees.length > 26) return null;
    const used = new Set<number>();
    const trees = value.trees.map((tree: unknown) => {
      if (tree === null) return null;
      if (!object(tree) || Object.keys(tree).length !== 2 || !Number.isSafeInteger(tree.buffer)
        || !Number.isSafeInteger(tree.flatData)) throw new Error('Invalid buffer reference');
      const buffer = Number(tree.buffer), flatData = Number(tree.flatData);
      for (const index of [buffer, flatData]) {
        if (index < 0 || index >= payload.buffers.length || used.has(index)) throw new Error('Invalid buffer reference');
        used.add(index);
      }
      const flatBuffer = payload.buffers[flatData]!;
      if (flatBuffer.byteLength % 8 !== 0) throw new Error('Unaligned numeric buffer');
      return { buffer: payload.buffers[buffer]!, flatData: new Float64Array(flatBuffer) };
    });
    if (used.size !== payload.buffers.length) return null;
    return { codec: value.codec, options: value.options, points: value.points, stride: value.stride,
      clusterProps: value.clusterProps, trees };
  } catch { return null; }
}
