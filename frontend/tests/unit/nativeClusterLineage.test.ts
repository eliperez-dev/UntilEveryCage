import { afterEach, describe, it, expect, vi } from 'vitest';
import { GeoJSONVT } from '@maplibre/geojson-vt';
import { matchNativeClusterLineage, NATIVE_LINEAGE_PORT, readNativeClusterLineage } from '../../src/map/nativeClusterLineage';
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

afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); });

function portSource(reply: unknown, respond = true) {
  const port1 = { onmessage: undefined as undefined | ((event: { data: unknown }) => void), close: vi.fn() };
  const port2 = { close: vi.fn() };
  vi.stubGlobal('MessageChannel', class { port1 = port1; port2 = port2; });
  const postMessage = vi.fn(() => { if (respond) queueMicrotask(() => port1.onmessage?.({ data: reply })); });
  const sendAsync = vi.fn();
  return { source: { actorPromise: Promise.resolve({ mapId: 'map-a', target: { postMessage }, sendAsync }) }, port1, port2, postMessage, sendAsync };
}

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
  it('uses one map-scoped reply port instead of the tile actor queue, then closes both ends', async () => {
    const { source, port1, port2, postMessage, sendAsync } = portSource([['c:1', 'p:a']]);
    const request = { parents: ['c:1'], targets: ['p:a'] };
    expect(await readNativeClusterLineage(source as any, request)).toEqual([['c:1', 'p:a']]);
    expect(postMessage).toHaveBeenCalledOnce();
    expect(postMessage).toHaveBeenCalledWith({ command: NATIVE_LINEAGE_PORT, mapId: 'map-a', request }, { transfer: [port2] });
    expect(sendAsync).not.toHaveBeenCalled();
    expect(port1.close).toHaveBeenCalledOnce(); expect(port2.close).toHaveBeenCalledOnce();
  });
  it('rejects a reply containing identities outside the requested scene and closes its ports', async () => {
    const { source, port1, port2 } = portSource([['c:other-map', 'p:a']]);
    await expect(readNativeClusterLineage(source as any, { parents: ['c:1'], targets: ['p:a'] })).rejects.toThrow('Invalid native lineage reply');
    expect(port1.close).toHaveBeenCalledOnce(); expect(port2.close).toHaveBeenCalledOnce();
  });
  it('expires an unanswered port without retaining it or blocking subsequent work', async () => {
    vi.useFakeTimers();
    const { source, port1, port2 } = portSource([], false);
    const pending = expect(readNativeClusterLineage(source as any, { parents: ['c:1'], targets: ['p:a'] })).rejects.toThrow('Native lineage read timed out');
    await vi.advanceTimersByTimeAsync(500); await pending;
    expect(port1.close).toHaveBeenCalledOnce(); expect(port2.close).toHaveBeenCalledOnce();
    expect(vi.getTimerCount()).toBe(0);
  });
  it('rejects oversized or malformed requests before contacting a worker', async () => {
    const { source, postMessage, sendAsync } = portSource([]);
    for (const request of [{ parents: [], targets: Array(2001).fill('p:a') }, { parents: [null], targets: [] }]) {
      expect(await readNativeClusterLineage(source as any, request as any)).toEqual([]);
    }
    expect(postMessage).not.toHaveBeenCalled(); expect(sendAsync).not.toHaveBeenCalled();
  });
});
