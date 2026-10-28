import { describe, it, expect, vi } from 'vitest';
import { GeoJSONVT } from '@maplibre/geojson-vt';
import { matchNativeClusterLineage, readNativeClusterLineage } from '../../src/map/nativeClusterLineage';
import { exportClusterIndex, restoreClusterIndex } from '../../src/map/clusterIndexCodec';

const data: GeoJSON.FeatureCollection<GeoJSON.Point> = {
  type: 'FeatureCollection', features: Array.from({ length: 10000 }, (_, i) => ({
    type: 'Feature', id: `synthetic-${i}`, properties: { key: `synthetic-${i}` },
    geometry: { type: 'Point', coordinates: [-124 + i % 160 * .35, 26 + Math.floor(i / 160) * .35] },
  })),
};
const options = { cluster: true, updateable: true, clusterOptions: { maxZoom: 9, radius: 50 } };
const native = new GeoJSONVT(data, options);
const key = (feature: any) => feature.properties.cluster ? `c:${feature.properties.cluster_id}` : `p:${feature.properties.key}`;
const scene = (index: any, zoom: number, box: [number, number, number, number] = [-180, -85, 180, 85]) => index.tileIndex.getClusters(box, zoom);

describe('single native worker lineage pass', () => {
  it('pairs every visible descendant across eight skipped levels with its actual native ancestor', () => {
    const parents = scene(native, 1), targets = scene(native, 9);
    const request = { parents: parents.map(key), targets: targets.slice(0, 1200).map(key) };
    const pairs = matchNativeClusterLineage(native, request);
    expect(pairs.length).toBe(request.targets.length);
    const descendants = new Map<string, string>();
    for (const parent of parents) {
      for (const leaf of native.getClusterLeaves(parent.properties.cluster_id, Infinity, 0)) descendants.set(key(leaf), key(parent));
    }
    for (const [parent, child] of pairs) {
      const target = targets.find((feature: any) => key(feature) === child);
      const leaf = target.properties.cluster ? native.getClusterLeaves(target.properties.cluster_id, 1, 0)[0] : target;
      expect(descendants.get(key(leaf))).toBe(parent);
    }
  });
  it('leaves newly revealed regions unpaired and returns the same lineage after index restore', () => {
    const parents = scene(native, 2), targets = scene(native, 7, [-124, 26, -118, 34]);
    const request = { parents: parents.map(key), targets: targets.map(key) };
    const pairs = matchNativeClusterLineage(native, request);
    expect(pairs.length).toBeGreaterThan(0);
    expect(pairs.length).toBe(targets.length);
    expect(new Set(pairs.map(pair => pair[0])).size).toBeLessThan(parents.length);
    const restored = restoreClusterIndex(exportClusterIndex(native), () => new GeoJSONVT({ type: 'FeatureCollection', features: [] }, options));
    expect(matchNativeClusterLineage(restored, request)).toEqual(pairs);
  });
  it('does not pair stable marks, unrelated parents, or requests exceeding the mark cap', () => {
    expect(matchNativeClusterLineage(native, { parents: ['c:invalid'], targets: ['p:synthetic-1'] })).toEqual([]);
    expect(matchNativeClusterLineage(native, { parents: ['p:synthetic-1'], targets: ['p:synthetic-1'] })).toEqual([]);
    expect(matchNativeClusterLineage(native, { parents: [], targets: Array(2001).fill('p:synthetic-1') })).toEqual([]);
  });
  it('sends only identity keys in one worker request without child queries or data changes', async () => {
    const sendAsync = vi.fn(async () => [['c:1', 'p:a']]);
    const source = { actorPromise: Promise.resolve({ sendAsync }), getClusterChildren: vi.fn(), setData: vi.fn() };
    expect(await readNativeClusterLineage(source as any, { parents: ['c:1'], targets: ['p:a'] })).toEqual([['c:1', 'p:a']]);
    expect(sendAsync).toHaveBeenCalledTimes(1);
    expect(sendAsync).toHaveBeenCalledWith({ type: 'GCC', data: { type: 'geojson', source: 'locations', uecMotionLineage: { parents: ['c:1'], targets: ['p:a'] } } });
    expect(source.getClusterChildren).not.toHaveBeenCalled(); expect(source.setData).not.toHaveBeenCalled();
  });
});
