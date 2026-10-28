import { describe, expect, it, vi } from 'vitest';
import { createExpression } from '@maplibre/maplibre-gl-style-spec';
import { CLUSTER_MOTION_HIDDEN_STATE, clusterMotionImage, clusterMotionKey, clusterMotionOpacity, clusterMotionPaintOrder, clusterMotionPaths, NativeClusterMotionController } from '../../src/design-lab/components/nativeClusterMotion';

describe('wrapped transition geometry', () => {
  it('draws every visible world copy when one native identity is masked', () => {
    const paths = clusterMotionPaths([170, 10], [172, 11], 0, [-300, 300]);
    expect(paths).toEqual([
      { from: [-190, 10], to: [-188, 11] },
      { from: [170, 10], to: [172, 11] },
    ]);
  });
  it('crosses the antimeridian by the short path instead of tearing across the map', () => {
    const paths = clusterMotionPaths([179, 0], [-179, 1], 0, [-300, 300]);
    expect(paths).toEqual([
      { from: [-181, 0], to: [-179, 1] },
      { from: [179, 0], to: [181, 1] },
    ]);
    expect(paths.every(path => Math.abs(path.to[0] - path.from[0]) === 2)).toBe(true);
  });
  it('does not repeat marks when world copies are disabled', () => {
    expect(clusterMotionPaths([170, 0], [-179, 1], 360)).toEqual([
      { from: [530, 0], to: [541, 1] },
    ]);
  });
});

describe('selective native visibility and stacking', () => {
  function opacity(original: unknown, hidden: boolean, properties: Record<string, unknown>) {
    const parsed = createExpression(clusterMotionOpacity(original), 'icon-opacity');
    expect(parsed.result).toBe('success');
    if (parsed.result !== 'success') throw new Error(JSON.stringify(parsed.value));
    return parsed.value.evaluate({ zoom: 7 }, { type: 'Point', properties }, { [CLUSTER_MOTION_HIDDEN_STATE]: hidden });
  }
  it('leaves unchanged clusters and pins native while hiding new descendants', () => {
    expect(opacity(undefined, false, { cluster_id: 12 })).toBe(1);
    expect(opacity(undefined, false, { key: 'stable' })).toBe(1);
    expect(opacity(undefined, true, { cluster_id: 18 })).toBe(0);
    expect(opacity(undefined, true, { facility_id: 'new' })).toBe(0);
  });
  it('hides only actual transition participants and preserves existing opacity', () => {
    expect(opacity(.6, true, { cluster_id: 18 })).toBe(0);
    expect(opacity(.6, true, { id: 'child' })).toBe(0);
    expect(opacity(.6, false, { key: 'stable' })).toBe(.6);
    expect(opacity(['case', ['get', 'dim'], .25, 1], false, { key: 'stable', dim: true })).toBe(.25);
  });
  it('paints overlapping children in native bottom-to-top order, independent of worker traversal', () => {
    const node = (key: string) => ({ key, coordinates: [0, 0] as [number, number], properties: {}, layer: 'clusters' });
    const parent = node('c:1'), top = node('p:top'), bottom = node('p:bottom');
    const parentScene = new Map([[parent.key, parent]]), childScene = new Map([[top.key, top], [bottom.key, bottom]]);
    const pairs = [{ parent, child: top }, { parent, child: bottom }];
    for (const direction of ['split', 'merge'] as const) {
      const ordered = clusterMotionPaintOrder(pairs, direction === 'split' ? parentScene : childScene, direction === 'split' ? childScene : parentScene, direction);
      expect(ordered.parents).toEqual([parent]);
      expect(ordered.pairs.map(pair => pair.child.key)).toEqual(['p:bottom', 'p:top']);
    }
  });
  it('installs paint once and changes only its own bounded feature state during gestures', () => {
    const paint = new Map<string, unknown>();
    const map = {
      getLayer: (id: string) => id === 'clusters', getSource: () => ({}),
      getPaintProperty: (layer: string, property: string) => paint.get(`${layer}/${property}`),
      setPaintProperty: vi.fn((layer: string, property: string, value: unknown) => { paint.set(`${layer}/${property}`, value); }),
      setFeatureState: vi.fn(), removeFeatureState: vi.fn(), redraw: vi.fn(), triggerRepaint: vi.fn(), on: vi.fn(), off: vi.fn(), isSourceLoaded: () => true,
    };
    const controller = new NativeClusterMotionController({ getMap: () => map as any, reducedMotion: () => false, enabled: () => true, duration: () => 210, limit: () => 1000 }) as any;
    controller.configureLayers(); controller.configureLayers();
    expect(map.setPaintProperty).toHaveBeenCalledTimes(2);
    controller.presentNodes = new Map([
      ['c:0', { key: 'c:0', id: 0 }], ['p:child', { key: 'p:child', id: 'child' }],
    ]);
    controller.mask(new Set(['c:0']), true);
    expect(map.setFeatureState).toHaveBeenLastCalledWith({ source: 'locations', id: 'child' }, { [CLUSTER_MOTION_HIDDEN_STATE]: true });
    controller.mask(new Set(['c:0']), false);
    expect(map.setFeatureState).toHaveBeenLastCalledWith({ source: 'locations', id: 0 }, { [CLUSTER_MOTION_HIDDEN_STATE]: true });
    controller.applyMask(); controller.applyMask();
    expect(map.redraw).toHaveBeenCalledTimes(2);
    const clear = vi.spyOn(controller, 'clear');
    controller.invalidate();
    expect(clear).toHaveBeenCalled(); expect(controller.hidden.size).toBe(0); expect(controller.maskScope).toBeUndefined();
    expect(map.removeFeatureState).toHaveBeenCalledWith({ source: 'locations', id: 'child' }, CLUSTER_MOTION_HIDDEN_STATE);
    expect(map.removeFeatureState).toHaveBeenCalledWith({ source: 'locations', id: 0 }, CLUSTER_MOTION_HIDDEN_STATE);
    expect(map.setPaintProperty).toHaveBeenCalledTimes(2);
    paint.clear(); paint.set('clusters/icon-opacity', .7);
    controller.configureLayers(); controller.configureLayers();
    expect(paint.get('clusters/icon-opacity')).toEqual(clusterMotionOpacity(.7));
    expect(map.setPaintProperty).toHaveBeenCalledTimes(4);
  });
  it('retains the original held scene through rapid camera retargets without rebuilding it', () => {
    let zoom = 6;
    const map = { getZoom: () => zoom, isZooming: () => true, getSource: () => undefined };
    const controller = new NativeClusterMotionController({ getMap: () => map as any, reducedMotion: () => false, enabled: () => true, duration: () => 210, limit: () => 1000 }) as any;
    const scene = new Map([['c:1', { key: 'c:1', coordinates: [0, 0], properties: { cluster_id: 1 }, layer: 'clusters' }]]);
    controller.capture = vi.fn(() => scene); controller.image = () => ({}); controller.mask = vi.fn(); controller.draw = vi.fn();
    controller.onZoomStart();
    zoom = 7.5; controller.onMoveStart(); controller.onZoomStart();
    expect(controller.before).toBe(scene); expect(controller.zoom).toBe(6); expect(controller.lastCameraZoom).toBe(7.5);
    expect(controller.capture).toHaveBeenCalledTimes(1); expect(controller.mask).toHaveBeenCalledTimes(1);
  });
  it('cancels immediately when motion is disabled during a held gesture', () => {
    const controller = new NativeClusterMotionController({ getMap: () => ({} as any), reducedMotion: () => true, enabled: () => true, duration: () => 210, limit: () => 1000 }) as any;
    controller.armed = true;
    const cancel = vi.spyOn(controller, 'cancel');
    controller.onRender();
    expect(cancel).toHaveBeenCalledWith(false, 'disabled'); expect(controller.armed).toBe(false);
  });
  it('continues the existing visible cue when another zoom starts during playback', () => {
    const controller = new NativeClusterMotionController({ getMap: () => ({ getZoom: () => 10 } as any), reducedMotion: () => false, enabled: () => true, duration: () => 210, limit: () => 1000 }) as any;
    const motion = { direction: 'split', pairs: [], parents: [], startedAt: 123 };
    const destination = new Map([['p:child', { key: 'p:child' }]]);
    controller.motion = motion; controller.after = destination; controller.targetZoom = 10;
    controller.mask = vi.fn(); controller.capture = vi.fn();
    controller.onZoomStart();
    expect(controller.motion).toBe(motion); expect(controller.motion.startedAt).toBe(123);
    expect(controller.before).toBe(destination); expect(controller.zoom).toBe(10); expect(controller.queued).toBe(true);
    expect(controller.capture).not.toHaveBeenCalled();
  });
});

describe('native cluster transition identities and artwork', () => {
  it('matches rendered features to native children without turning facility ids into cluster ids', () => {
    expect(clusterMotionKey({ cluster_id: 0, key: 'facility' })).toBe('c:0');
    expect(clusterMotionKey({ key: 'facility', id: 'other' })).toBe('p:facility');
    expect(clusterMotionKey({ facility_id: 'facility' })).toBe('p:facility');
    expect(clusterMotionKey({})).toBeNull();
  });
  it('uses represented record counts for the existing cluster palette', () => {
    expect(clusterMotionImage({ cluster_id: 1, representedCount: 1001, point_count: 2 })).toBe('cluster-very-high');
    expect(clusterMotionImage({ cluster_id: 1, representedCount: 100 })).toBe('cluster-high');
    expect(clusterMotionImage({ cluster_id: 1, representedCount: 10 })).toBe('cluster-mid');
    expect(clusterMotionImage({ cluster_id: 1, representedCount: 2 })).toBe('cluster-low');
  });
  it('preserves the native multi-category priority and serialized rendered properties', () => {
    expect(clusterMotionImage({ category_keys: ['processing_and_preparation', 'slaughter'], category_key: 'research' })).toBe('v1-pin-red');
    expect(clusterMotionImage({ category_keys: '["research_and_animal_use"]', category_key: 'slaughter' })).toBe('v1-pin-violet');
    expect(clusterMotionImage({ category_keys: 'bad-json', category_key: 'farm' })).toBe('v1-pin-yellow');
    expect(clusterMotionImage({ category_key: 'general_food_business' })).toBe('v1-pin-orange');
  });
  it('retains category artwork across coarse and ordinary approximate references', () => {
    expect(clusterMotionImage({ precision: 'city', category_key: 'slaughter' })).toBe('v1-pin-red');
    expect(clusterMotionImage({ precision: 'approximate', category_key: 'slaughter' })).toBe('v1-pin-red');
    expect(clusterMotionImage({ precision: 'city', category_key: 'processing' })).toBe('v1-pin-graphite');
    expect(clusterMotionImage({ category_keys: ['processing_and_preparation'] })).toBe('v1-pin-graphite');
    expect(clusterMotionImage({})).toBe('v1-pin-grey');
  });
});

describe('bounded native hierarchy reuse', () => {
  const node = (id: number) => ({ key: `c:${id}`, coordinates: [0, 0], properties: { cluster_id: id }, layer: 'clusters' });
  const point = (id: number) => ({ type: 'Feature', geometry: { type: 'Point', coordinates: [0, 0] }, properties: { key: `synthetic-${id}` } });
  function fixture() {
    let source = { getClusterChildren: vi.fn(async (id: number) => [point(id)]) };
    const map = { getSource: () => source, isMoving: () => false, isSourceLoaded: () => true };
    const controller = new NativeClusterMotionController({ getMap: () => map as any, reducedMotion: () => false, enabled: () => true, duration: () => 210, limit: () => 1000 }) as any;
    return { controller, source, replaceSource: () => { source = { getClusterChildren: vi.fn(async (id: number) => [point(id)]) }; return source; } };
  }
  it('retains child queries across camera cancellation and invalidates on data/source changes', async () => {
    const { controller, source, replaceSource } = fixture();
    await controller.getChildren(node(1)); controller.cancel(); await controller.getChildren(node(1));
    expect(source.getClusterChildren).toHaveBeenCalledTimes(1);
    controller.invalidate(); await controller.getChildren(node(1));
    expect(source.getClusterChildren).toHaveBeenCalledTimes(2);
    const replacement = replaceSource(); await controller.getChildren(node(1));
    expect(replacement.getClusterChildren).toHaveBeenCalledTimes(1);
  });
  it('keeps both cache entries and retained child nodes bounded', async () => {
    const { controller, source } = fixture();
    source.getClusterChildren.mockImplementation(async id => Array.from({ length: 20 }, (_, index) => point(id * 20 + index)));
    for (let id = 0; id < 600; id++) await controller.getChildren(node(id));
    expect(controller.children.size).toBeLessThanOrEqual(512);
    expect([...controller.childCounts.values()].reduce((sum: number, count) => sum + Number(count), 0)).toBeLessThanOrEqual(4096);
  });
  it('warms native child reads while idle and stops after data invalidation', async () => {
    const { controller, source } = fixture();
    controller.capture = () => new Map([[node(1).key, node(1)]]);
    await controller.warm();
    expect(source.getClusterChildren).toHaveBeenCalledTimes(1);
    await controller.getChildren(node(1));
    expect(source.getClusterChildren).toHaveBeenCalledTimes(1);
  });
  it('pairs the whole visible scene instead of stopping after the first 80 branches', async () => {
    const { controller } = fixture();
    const parents = new Map(Array.from({ length: 100 }, (_, i) => [node(i).key, node(i)]));
    const targets = new Map(Array.from({ length: 100 }, (_, i) => [`p:synthetic-${i}`, { key: `p:synthetic-${i}` }]));
    expect(await controller.findPairs(parents, targets)).toHaveLength(100);
  });
  it('does not play a partial regional transition when the remaining lineage exceeds its budget', async () => {
    const { controller, source } = fixture();
    source.getClusterChildren.mockImplementation(async id => id === 1 ? [point(1)] : [{
      type: 'Feature', geometry: { type: 'Point', coordinates: [0, 0] }, properties: { cluster_id: id + 1 },
    }] as any);
    const parents = new Map([[node(1).key, node(1)], [node(2).key, node(2)]]);
    const targets = new Map([['p:synthetic-1', { key: 'p:synthetic-1' }]]);
    expect(await controller.findPairs(parents, targets)).toEqual([]);
  });
  it('ignores late lineage from an invalidated data generation', async () => {
    const { controller, source } = fixture();
    let finish!: (rows: any[]) => void;
    source.getClusterChildren.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
    const old = controller.getChildren(node(1)); controller.invalidate();
    const current = await controller.getChildren(node(1));
    finish([point(900)]);
    expect(await old).toEqual([]);
    expect(await controller.getChildren(node(1))).toEqual(current);
  });
});
