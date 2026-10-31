import { describe, expect, it } from 'vitest';
import { GeoJSONVT } from '@maplibre/geojson-vt';
import { installNativeClusterMetadata, nativeClusterParents, NATIVE_CLUSTER_PARENTS } from '../../src/map/nativeClusterMetadata';
import { matchNativeClusterLineage } from '../../src/map/nativeClusterLineage';
import { exportClusterIndex, restoreClusterIndex } from '../../src/map/clusterIndexCodec';

const data: GeoJSON.FeatureCollection<GeoJSON.Point> = { type: 'FeatureCollection', features: Array.from({ length: 400 }, (_, i) => ({
  type: 'Feature', id: `synthetic-${i}`, properties: { key: `synthetic-${i}`, weight: 1 },
  geometry: { type: 'Point', coordinates: [-122 + i % 20 * .02, 37 + Math.floor(i / 20) * .02] },
})) };
const options = { cluster: true, updateable: true, clusterOptions: { maxZoom: 9, radius: 50 } };
function tile(index: GeoJSONVT, zoom: number) {
  const scale = 2 ** zoom;
  return index.getTile(zoom, Math.floor((-121.8 + 180) / 360 * scale), Math.floor((1 - Math.asinh(Math.tan(37.2 * Math.PI / 180)) / Math.PI) / 2 * scale))!;
}

describe('tile-local native parent metadata', () => {
  it('identifies known roots and rejects missing or malformed ancestry', () => {
    expect(nativeClusterParents({})).toBeUndefined();
    expect(nativeClusterParents({ [NATIVE_CLUSTER_PARENTS]: '' })).toEqual([]);
    expect(nativeClusterParents({ [NATIVE_CLUSTER_PARENTS]: '12,34' })).toEqual(['c:12', 'c:34']);
    for (const value of ['bad', '-1', '1.2', '1,'.repeat(100), 12]) expect(nativeClusterParents({ [NATIVE_CLUSTER_PARENTS]: value })).toBeUndefined();
  });
  it.each([false, true])('supplies every actual ancestor across skipped zoom levels (reducer: %s)', reduced => {
    const index = installNativeClusterMetadata(new GeoJSONVT(data, reduced ? { ...options, clusterOptions: { ...options.clusterOptions,
      map: (properties: Record<string, unknown>) => ({ weight: Number(properties.weight) }),
      reduce: (accumulated: Record<string, unknown>, properties: Record<string, unknown>) => { accumulated.weight = Number(accumulated.weight) + Number(properties.weight); },
    } } : options));
    let points = 0, clusters = 0, links = 0;
    for (const zoom of [0, 5, 8, 10]) {
      for (const feature of tile(index, zoom).features.slice(0, 5)) {
        const properties = feature.tags!, ancestors = nativeClusterParents(properties)!;
        expect(ancestors).toBeDefined();
        const key = typeof properties.cluster_id === 'number' ? `c:${properties.cluster_id}` : `p:${properties.key}`;
        if (key.startsWith('c:')) clusters++; else points++;
        for (const ancestor of ancestors) {
          expect(matchNativeClusterLineage(index, { parents: [ancestor], targets: [key] })).toEqual([[ancestor, key]]);
          links++;
        }
      }
    }
    expect(points).toBeGreaterThan(0); expect(clusters).toBeGreaterThan(0); expect(links).toBeGreaterThan(10);
  });
  it('does not mutate source tags or persisted snapshots, including after restoration', () => {
    const index = new GeoJSONVT(data, options), before = exportClusterIndex(index)!;
    installNativeClusterMetadata(index); installNativeClusterMetadata(index);
    const expected = tile(index, 10).features;
    const after = exportClusterIndex(index)!;
    expect(after.points).toEqual(before.points); expect(after.clusterProps).toEqual(before.clusterProps);
    expect(after.points.every(point => !Object.hasOwn(point.tags ?? {}, NATIVE_CLUSTER_PARENTS))).toBe(true);
    const restored = installNativeClusterMetadata(restoreClusterIndex(after, () => new GeoJSONVT({ type: 'FeatureCollection', features: [] }, options))!);
    expect(tile(restored as GeoJSONVT, 10).features).toEqual(expected);
  });
  it('recomputes links after native data updates instead of reusing a previous tree generation', () => {
    const index = installNativeClusterMetadata(new GeoJSONVT(data, options));
    tile(index, 10);
    index.updateData({ remove: data.features.slice(0, 200).map(feature => feature.id!) });
    const fresh = installNativeClusterMetadata(new GeoJSONVT({ ...data, features: data.features.slice(200) }, options));
    expect(tile(index, 10).features).toEqual(tile(fresh, 10).features);
  });
  it('identifies points as roots with clustering disabled without changing source properties', () => {
    const index = installNativeClusterMetadata(new GeoJSONVT(data, { cluster: false, updateable: true }));
    expect(tile(index, 5).features.every(feature => nativeClusterParents(feature.tags!)?.length === 0)).toBe(true);
    expect((index as any).source.every((point: any) => !Object.hasOwn(point.tags, NATIVE_CLUSTER_PARENTS))).toBe(true);
  });
});
