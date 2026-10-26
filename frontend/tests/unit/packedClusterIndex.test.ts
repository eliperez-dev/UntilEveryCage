// @vitest-environment node
import { describe, expect, it } from 'vitest';
import { GeoJSONVT } from '@maplibre/geojson-vt';
import { exportClusterIndex, restoreClusterIndex } from '../../src/map/clusterIndexCodec';
import { packClusterIndex, unpackClusterIndex, encodeStoredClusterIndex, decodeStoredClusterIndex, storedClusterIndexBytes, COMPRESSED_CLUSTER_INDEX_VERSION, REFERENCED_CLUSTER_INDEX_VERSION, type PackedIndex, type CompressedPackedIndex, type ReferencedPackedIndex } from '../../src/map/packedClusterIndex';

const options = { updateable: true, cluster: true, clusterOptions: { maxZoom: 8 } };
const data: GeoJSON.FeatureCollection<GeoJSON.Point> = { type: 'FeatureCollection', features:
  Array.from({ length: 150 }, (_, index) => ({ type: 'Feature', id: `synthetic-${index}`,
    geometry: { type: 'Point', coordinates: [4 + index * .00001, 51] },
    properties: { weight: 1, buffer: 40, flatData: 41, marker: { format: 'ArrayBuffer', json: 'ordinary source property' } } })) };
data.features.push({ type: 'Feature', id: 'synthetic-far', geometry: { type: 'Point', coordinates: [24, 51] }, properties: { weight: 1 } });

function packed() {
  return packClusterIndex(exportClusterIndex(new GeoJSONVT(data, options))!);
}

describe('compact cluster-index transport', () => {
  it('references exact current properties and preserves native wrapped/high-latitude point semantics', async () => {
    const input: GeoJSON.FeatureCollection<GeoJSON.Point> = { type: 'FeatureCollection', features: [...data.features,
      { type: 'Feature', id: 'synthetic-west', geometry: { type: 'Point', coordinates: [-179.999, 85] }, properties: { weight: 7 } },
      { type: 'Feature', id: 'synthetic-east', geometry: { type: 'Point', coordinates: [179.999, -85] }, properties: { weight: 3 } }] };
    const native = new GeoJSONVT(input, { ...options, buffer: 2048, extent: 8192 });
    const snapshot = exportClusterIndex(native, false, false)!;
    const encoded = await encodeStoredClusterIndex(snapshot, input.features);
    expect(encoded.format).toBe(REFERENCED_CLUSTER_INDEX_VERSION);
    expect(JSON.stringify(encoded)).not.toContain('ordinary source property');
    const decoded = await decodeStoredClusterIndex(structuredClone(encoded), undefined, undefined, input.features) as typeof snapshot;
    const restored = restoreClusterIndex(decoded, () => new GeoJSONVT({ type: 'FeatureCollection', features: [] }, { ...options, buffer: 2048, extent: 8192 }))!;
    expect(restored).not.toBeNull();
    expect(restored.getData()).toEqual(native.getData());
    for (let zoom = 0; zoom <= 9; zoom++) {
      const size = 2 ** zoom;
      for (const x of [0, size - 1, size / 2 | 0]) for (const y of [0, size - 1, size / 2 | 0]) {
        expect(restored.getTile(zoom, x, y)).toEqual(native.getTile(zoom, x, y));
      }
    }
    expect(decoded.points[0]!.tags).toBe(input.features.find(feature => feature.id === decoded.points[0]!.id)!.properties);
  });

  it('rejects point-reference corruption, missing current input and coordinate changes', async () => {
    const snapshot = exportClusterIndex(new GeoJSONVT(data, options), false, false)!;
    const encoded = await encodeStoredClusterIndex(snapshot, data.features) as ReferencedPackedIndex;
    expect(encoded.format).toBe(REFERENCED_CLUSTER_INDEX_VERSION);
    expect(await decodeStoredClusterIndex(encoded)).toBeNull();
    const corrupt = structuredClone(encoded);
    new Uint32Array(corrupt.buffers.at(-1)!)[0] = data.features.length;
    expect(await decodeStoredClusterIndex(corrupt, undefined, undefined, data.features)).toBeNull();
    const moved = structuredClone(data.features);
    moved[0]!.geometry.coordinates[0] = 20;
    expect(await decodeStoredClusterIndex(encoded, undefined, undefined, moved)).toBeNull();
    expect(await decodeStoredClusterIndex({ ...encoded, pointCount: 250_001 }, undefined, undefined, data.features)).toBeNull();
    expect(await decodeStoredClusterIndex({ ...encoded, buffers: encoded.buffers.slice(0, -1) }, undefined, undefined, data.features)).toBeNull();
  });

  it('roundtrips native buffers, Infinity and arbitrary public properties without rebuilding', () => {
    const native = new GeoJSONVT(data, options);
    const snapshot = exportClusterIndex(native)!;
    const payload = packClusterIndex(snapshot);
    expect(Object.keys(payload).sort()).toEqual(['buffers', 'format', 'json']);
    expect(payload.buffers.every(buffer => Object.prototype.toString.call(buffer) === '[object ArrayBuffer]')).toBe(true);
    const decoded = unpackClusterIndex(structuredClone(payload));
    const restored = restoreClusterIndex(decoded, () => new GeoJSONVT({ type: 'FeatureCollection', features: [] }, options));
    expect(restored).not.toBeNull();
    expect(restored!.getData()).toEqual(native.getData());
    for (let zoom = 0; zoom <= 9; zoom++) expect(restored!.getTile(zoom, 2 ** zoom / 2 | 0, 2 ** zoom / 2 | 0))
      .toEqual(native.getTile(zoom, 2 ** zoom / 2 | 0, 2 ** zoom / 2 | 0));
    const decodedSnapshot = decoded as typeof snapshot;
    expect(decodedSnapshot.trees.some(tree => tree?.flatData.includes(Infinity))).toBe(true);
    expect(decodedSnapshot.points[0]!.tags).toEqual(data.features[0]!.properties);
  });

  it.each([
    ['format', (value: PackedIndex) => { value.format = 'old' as PackedIndex['format']; }],
    ['JSON', (value: PackedIndex) => { value.json = '{'; }],
    ['schema', (value: PackedIndex) => { value.json = '{}'; }],
    ['version', (value: PackedIndex) => { const json = JSON.parse(value.json); json.codec = 'old'; value.json = JSON.stringify(json); }],
    ['buffer count', (value: PackedIndex) => { value.buffers = Array.from({ length: 53 }, () => new ArrayBuffer(8)); }],
    ['missing buffer', (value: PackedIndex) => { value.buffers.pop(); }],
    ['extra buffer', (value: PackedIndex) => { value.buffers.push(new ArrayBuffer(8)); }],
    ['numeric alignment', (value: PackedIndex) => { value.buffers[1] = new ArrayBuffer(9); }],
    ['reference bounds', (value: PackedIndex) => { const json = JSON.parse(value.json); json.trees[0].buffer = 9999; value.json = JSON.stringify(json); }],
    ['duplicate references', (value: PackedIndex) => { const json = JSON.parse(value.json); json.trees[0].flatData = json.trees[0].buffer; value.json = JSON.stringify(json); }],
    ['object buffer', (value: PackedIndex) => { value.buffers[0] = {} as ArrayBuffer; }],
    ['spoofed buffer', (value: PackedIndex) => { value.buffers[0] = { [Symbol.toStringTag]: 'ArrayBuffer', byteLength: 8 } as unknown as ArrayBuffer; }],
  ])('rejects malformed %s before engine restoration', (_name, corrupt) => {
    const payload = packed();
    corrupt(payload);
    expect(unpackClusterIndex(payload)).toBeNull();
  });

  it('bounds total bytes before parsing JSON', () => {
    const payload = packed();
    const buffer = new ArrayBuffer(4 * 1024 * 1024);
    payload.buffers = Array.from({ length: 40 }, () => buffer);
    expect(unpackClusterIndex(payload)).toBeNull();
  });

  it('compresses an index beyond the old 64 MiB raw limit without losing source properties', async () => {
    const snapshot = exportClusterIndex(new GeoJSONVT(data, options))!;
    const point = snapshot.points[0]!;
    snapshot.points = Array.from({ length: 20_000 }, (_, index) => ({ ...point, id: `synthetic-${index}`,
      tags: { ...point.tags, source_note: 'synthetic '.repeat(180) } }));
    expect(storedClusterIndexBytes(packClusterIndex(snapshot))).toBeGreaterThan(64 * 1024 * 1024);
    const compressed = await encodeStoredClusterIndex(snapshot);
    expect(compressed.format).toBe(COMPRESSED_CLUSTER_INDEX_VERSION);
    expect(await decodeStoredClusterIndex(compressed, 1)).toBeNull();
    expect(storedClusterIndexBytes(compressed)).toBeLessThan(8 * 1024 * 1024);
    const decoded = await decodeStoredClusterIndex(compressed) as typeof snapshot;
    expect(decoded.points).toEqual(snapshot.points);
    expect(decoded.trees[0]!.flatData).toEqual(snapshot.trees[0]!.flatData);
  }, 20_000);

  it('rejects corrupt gzip and underdeclared inflated size before parsing', async () => {
    const snapshot = exportClusterIndex(new GeoJSONVT(data, options))!;
    snapshot.points = Array.from({ length: 5_000 }, () => ({ ...snapshot.points[0]!, tags: { source_note: 'x'.repeat(1000) } }));
    const compressed = await encodeStoredClusterIndex(snapshot) as CompressedPackedIndex;
    expect(compressed.format).toBe(COMPRESSED_CLUSTER_INDEX_VERSION);
    expect(await decodeStoredClusterIndex({ ...compressed, jsonBytes: compressed.jsonBytes - 1 })).toBeNull();
    const corrupt = structuredClone(compressed);
    new Uint8Array(corrupt.jsonGzip)[0] = 0;
    expect(await decodeStoredClusterIndex(corrupt)).toBeNull();
    expect(await decodeStoredClusterIndex({ ...compressed, jsonBytes: 128 * 1024 * 1024 })).toBeNull();
  }, 20_000);
});
