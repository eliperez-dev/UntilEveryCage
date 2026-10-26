import { describe, expect, it, vi } from 'vitest';
import { GeoJSONVT, Supercluster } from '@maplibre/geojson-vt';
import KDBush from 'kdbush';
import { CLUSTER_INDEX_CODEC_VERSION, exportClusterIndex, restoreClusterIndex, type ClusterIndexSnapshot } from '../../src/map/clusterIndexCodec';

const empty = { type: 'FeatureCollection' as const, features: [] };
const options = {
  updateable: true, cluster: true, extent: 8192, buffer: 128,
  clusterOptions: {
    minZoom: 0, maxZoom: 8, extent: 8192, radius: 800, nodeSize: 64,
    map: (props: GeoJSON.GeoJsonProperties) => ({ representedCount: Number(props?.weight ?? 1), approximateCount: props?.precision === 'approximate' ? Number(props.weight) : 0 }),
    reduce: (accumulated: Record<string, unknown>, props: Record<string, unknown>) => {
      accumulated.representedCount = Number(accumulated.representedCount) + Number(props.representedCount);
      accumulated.approximateCount = Number(accumulated.approximateCount) + Number(props.approximateCount);
    },
  },
};
const data: GeoJSON.FeatureCollection<GeoJSON.Point> = {
  type: 'FeatureCollection',
  features: [
    [0, 0], [0.005, 0.005], [0.01, 0], [30, 30], [30.01, 30.01],
    [179.999, 10], [-179.999, 10], [10, 84.99], [10.0001, 84.9901],
  ].map((coordinates, index) => ({
    type: 'Feature', id: `synthetic-${index}`, geometry: { type: 'Point', coordinates },
    properties: { id: `synthetic-${index}`, weight: index === 0 ? 7 : 1, precision: index === 0 ? 'approximate' : 'exact', category_keys: ['slaughter'] },
  })),
};

function snapshot(): ClusterIndexSnapshot {
  const value = exportClusterIndex(new GeoJSONVT(data, options));
  expect(value).not.toBeNull();
  return value!;
}

describe('version-locked built cluster index codec', () => {
  it('restores the full hierarchy without loading, initializing, clustering or sorting points', () => {
    const saved = snapshot();
    const load = vi.spyOn(Supercluster.prototype, 'load');
    const initialize = vi.spyOn(Supercluster.prototype, 'initialize');
    const finish = vi.spyOn(KDBush.prototype, 'finish');
    const restored = restoreClusterIndex(structuredClone(saved), () => new GeoJSONVT(empty, options));
    expect(restored).not.toBeNull();
    expect(load).not.toHaveBeenCalled();
    expect(initialize).not.toHaveBeenCalled();
    expect(finish).not.toHaveBeenCalled();
    vi.restoreAllMocks();
  });

  it('matches cold tiles, weighted counts, children, leaves, expansion and original source at all zooms', () => {
    const cold = new GeoJSONVT(data, options);
    const restored = restoreClusterIndex(exportClusterIndex(cold), () => new GeoJSONVT(empty, options))!;
    expect(restored).not.toBeNull();
    expect(restored.getData()).toEqual(cold.getData());
    const clusterIndex = (index: GeoJSONVT) => (index as unknown as { tileIndex: Supercluster }).tileIndex;
    for (let z = 0; z <= 10; z++) {
      for (const box of [[-180, -90, 180, 90], [179, 0, -179, 20], [0, 84, 20, 90]] as [number, number, number, number][]) {
        expect(clusterIndex(restored).getClusters(box, z)).toEqual(clusterIndex(cold).getClusters(box, z));
      }
      const size = 2 ** z;
      for (const [x, y] of [[0, 0], [size - 1, Math.floor(size * .472)], [Math.floor(size / 2), Math.floor(size / 2)], [Math.floor(size * .527), 0]]) {
        const tile = cold.getTile(z, x!, y!);
        expect(restored.getTile(z, x!, y!)).toEqual(tile);
        for (const feature of tile?.features ?? []) {
          if (feature.tags?.cluster !== true) continue;
          const id = Number(feature.tags.cluster_id);
          expect(restored.getClusterExpansionZoom(id)).toEqual(cold.getClusterExpansionZoom(id));
          expect(restored.getClusterChildren(id)).toEqual(cold.getClusterChildren(id));
          expect(restored.getClusterLeaves(id, 100, 0)).toEqual(cold.getClusterLeaves(id, 100, 0));
          expect(restored.getClusterLeaves(id, 1, 1)).toEqual(cold.getClusterLeaves(id, 1, 1));
        }
      }
    }
    const world = restored.getTile(0, 0, 0)!;
    expect(world.features.some(feature => Number(feature.tags?.representedCount) > Number(feature.tags?.point_count))).toBe(true);
    expect(world.features.some(feature => Number(feature.tags?.approximateCount) === 7)).toBe(true);
  });

  it('restores fresh reducer closures and remains compatible with changed cluster options', () => {
    const cold = new GeoJSONVT(data, options);
    const restored = restoreClusterIndex(exportClusterIndex(cold), () => new GeoJSONVT(empty, options))!;
    expect(restored).not.toBeNull();
    const changed = { ...options.clusterOptions, radius: 1600 };
    cold.updateClusterOptions(true, changed);
    restored.updateClusterOptions(true, changed);
    expect(restored.getTile(4, 8, 8)).toEqual(cold.getTile(4, 8, 8));
  });

  it('supports non-reducer hierarchies and nonzero minimum zoom', () => {
    const simpleOptions = { updateable: true, cluster: true, clusterOptions: { minZoom: 2, maxZoom: 5 } };
    const cold = new GeoJSONVT(data, simpleOptions);
    const restored = restoreClusterIndex(exportClusterIndex(cold), () => new GeoJSONVT(empty, simpleOptions))!;
    expect(restored).not.toBeNull();
    expect(restored.getTile(0, 0, 0)).toEqual(cold.getTile(0, 0, 0));
    expect(restored.getTile(6, 32, 32)).toEqual(cold.getTile(6, 32, 32));
  });

  it('checks KD partition ordering rather than only buffer shape', () => {
    const grid: GeoJSON.FeatureCollection<GeoJSON.Point> = { type: 'FeatureCollection', features:
      Array.from({ length: 600 }, (_, index) => ({ type: 'Feature', geometry: { type: 'Point', coordinates: [(index % 30) * 4 - 60, Math.floor(index / 30) * 4 - 40] }, properties: { weight: 1 } })) };
    const cold = new GeoJSONVT(grid, options);
    const saved = exportClusterIndex(cold)!;
    expect(restoreClusterIndex(saved, () => new GeoJSONVT(empty, options))).not.toBeNull();
    const tree = KDBush.from(saved.trees[9]!.buffer);
    const last = tree.numItems - 1;
    [tree.ids[0], tree.ids[last]] = [tree.ids[last]!, tree.ids[0]!];
    for (const axis of [0, 1]) [tree.coords[axis], tree.coords[last * 2 + axis]] = [tree.coords[last * 2 + axis]!, tree.coords[axis]!];
    expect(restoreClusterIndex(saved, () => new GeoJSONVT(empty, options))).toBeNull();
  });

  it.each([
    ['codec', (value: ClusterIndexSnapshot) => { value.codec = 'old' as typeof CLUSTER_INDEX_CODEC_VERSION; }],
    ['options', (value: ClusterIndexSnapshot) => { value.options += '-different'; }],
    ['tree count', (value: ClusterIndexSnapshot) => { value.trees.pop(); }],
    ['buffer header', (value: ClusterIndexSnapshot) => { new Uint8Array(value.trees[0]!.buffer)[0] = 0; }],
    ['truncated buffer', (value: ClusterIndexSnapshot) => { value.trees[0]!.buffer = value.trees[0]!.buffer.slice(0, 10); }],
    ['geometry', (value: ClusterIndexSnapshot) => { value.points[0]!.geometry[0] = NaN; }],
    ['pointer', (value: ClusterIndexSnapshot) => { value.trees[0]!.flatData[3] = 999_999_999; }],
    ['count', (value: ClusterIndexSnapshot) => { value.trees[0]!.flatData[5] = -3; }],
    ['non-zoom infinity', (value: ClusterIndexSnapshot) => { value.trees[0]!.flatData[0] = Infinity; }],
    ['property infinity', (value: ClusterIndexSnapshot) => { value.trees[0]!.flatData[6] = Infinity; }],
    ['property pointer', (value: ClusterIndexSnapshot) => { value.trees[0]!.flatData[6] = 999_999; }],
  ])('rejects corrupt %s without exposing an incomplete index', (_label, corrupt) => {
    const saved = snapshot();
    corrupt(saved);
    expect(restoreClusterIndex(saved, () => new GeoJSONVT(empty, options))).toBeNull();
  });

  it('rejects engine-option mismatch, nonempty factory results and nonclustered indexes', () => {
    expect(restoreClusterIndex(snapshot(), () => new GeoJSONVT(empty, { ...options, clusterOptions: { ...options.clusterOptions, radius: 900 } }))).toBeNull();
    expect(restoreClusterIndex(snapshot(), () => new GeoJSONVT(data, options))).toBeNull();
    expect(exportClusterIndex(new GeoJSONVT(data, { cluster: false }))).toBeNull();
    expect(exportClusterIndex(new GeoJSONVT(empty, options))).toBeNull();
    expect(restoreClusterIndex({}, () => { throw new Error('factory unavailable'); })).toBeNull();
  });
});
