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
  it('installs paint once and changes only its own bounded feature state during gestures', async () => {
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
    controller.footprint = [-1, -1, 1, 1];
    controller.presentNodes.get('p:child').coordinates = [0, 0];
    controller.mask(new Set(['c:0']), true);
    expect(map.setFeatureState).toHaveBeenLastCalledWith({ source: 'locations', id: 'child' }, { [CLUSTER_MOTION_HIDDEN_STATE]: true });
    controller.mask(new Set(['c:0']), false);
    expect(map.setFeatureState).toHaveBeenLastCalledWith({ source: 'locations', id: 0 }, { [CLUSTER_MOTION_HIDDEN_STATE]: true });
    controller.applyMask(); controller.applyMask();
    expect(map.redraw).not.toHaveBeenCalled();
    await Promise.resolve();
    expect(map.redraw).not.toHaveBeenCalled();
    map.on.mock.calls.at(-1)![1]();
    expect(map.redraw).toHaveBeenCalledTimes(1);
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
  it('waits for native placement when a worker installs new buckets between frames', async () => {
    let insideInputTask = true;
    let placed = false;
    const map = { on: vi.fn(), off: vi.fn(), triggerRepaint: vi.fn(), redraw: vi.fn(() => {
      if (insideInputTask) throw new Error('Attempting to run(), but is already running.');
      if (!placed) throw new Error('Length of new data is 101, which does not match current length of 0');
    }) };
    const controller = new NativeClusterMotionController({ getMap: () => map as any, reducedMotion: () => false, enabled: () => true, duration: () => 210, limit: () => 1200 }) as any;
    controller.repaint(); controller.repaint(); controller.repaint();
    expect(map.redraw).not.toHaveBeenCalled();
    insideInputTask = false;
    await Promise.resolve();
    expect(map.redraw).not.toHaveBeenCalled();
    expect(map.triggerRepaint).toHaveBeenCalledTimes(1);
    placed = true;
    map.on.mock.calls.at(-1)![1]();
    expect(map.redraw).toHaveBeenCalledTimes(1);
  });
  it('keeps the overlay until restored native pixels have actually repainted', async () => {
    const order: string[] = [];
    const map = { getSource: () => ({}), isSourceLoaded: () => true, on: vi.fn(), off: vi.fn(), triggerRepaint: vi.fn(), removeFeatureState: vi.fn(), redraw: vi.fn(() => order.push('native paint')) };
    const controller = new NativeClusterMotionController({ getMap: () => map as any, reducedMotion: () => false, enabled: () => true, duration: () => 210, limit: () => 1200 }) as any;
    controller.hidden.set('c:1', 1);
    controller.clear = vi.fn(() => order.push('clear overlay'));
    controller.unmask(true);
    expect(order).toEqual([]);
    await Promise.resolve();
    expect(order).toEqual([]);
    map.on.mock.calls.at(-1)![1]();
    expect(order).toEqual(['native paint', 'clear overlay']);
  });
  it('repaints a native render in the same composite but never treats a timer as placement', async () => {
    const map = { on: vi.fn(), off: vi.fn(), triggerRepaint: vi.fn(), redraw: vi.fn() };
    const controller = new NativeClusterMotionController({ getMap: () => map as any, reducedMotion: () => false, enabled: () => true, duration: () => 210, limit: () => 1200 }) as any;
    controller.advanceRender = () => controller.repaint();
    controller.onRender();
    expect(map.redraw).not.toHaveBeenCalled();
    await Promise.resolve();
    expect(map.redraw).toHaveBeenCalledTimes(1);
    expect(map.on).not.toHaveBeenCalled();
    controller.onRender(false);
    await Promise.resolve();
    expect(map.redraw).toHaveBeenCalledTimes(1);
    expect(map.on).toHaveBeenCalledOnce();
    map.on.mock.calls.at(-1)![1]();
    expect(map.redraw).toHaveBeenCalledTimes(2);
  });
  it('completes handoffs requested by a render listener in the same paint', async () => {
    const done = vi.fn();
    let controller: any;
    const map = { redraw: () => controller.repaint(done) };
    controller = new NativeClusterMotionController({ getMap: () => map as any, reducedMotion: () => false, enabled: () => true, duration: () => 210, limit: () => 1200 });
    controller.nativePaint = true;
    controller.repaint();
    controller.nativePaint = false;
    await Promise.resolve();
    expect(done).toHaveBeenCalledTimes(1);
  });
  it('repaints before dropping a held scene even when its hidden marks left the native query', async () => {
    const order: string[] = [];
    const map = { getSource: () => ({}), isSourceLoaded: () => true, on: vi.fn(), off: vi.fn(), triggerRepaint: vi.fn(), redraw: () => order.push('native paint') };
    const controller = new NativeClusterMotionController({ getMap: () => map as any, reducedMotion: () => false, enabled: () => true, duration: () => 210, limit: () => 1200 }) as any;
    controller.heldDrawn = true; controller.clear = () => order.push('clear overlay');
    controller.unmask(true);
    expect(order).toEqual([]);
    await Promise.resolve();
    expect(order).toEqual([]);
    map.on.mock.calls.at(-1)![1]();
    expect(order).toEqual(['native paint', 'clear overlay']);
  });
  it('retains the original held scene through rapid camera retargets without rebuilding it', () => {
    let zoom = 6;
    const map = { getBounds: () => ({ getWest: () => -1, getEast: () => 1, getSouth: () => -1, getNorth: () => 1 }), getZoom: () => zoom, isZooming: () => true, getSource: () => undefined };
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
  it('does not disarm a merge on the tiny first eased camera step', () => {
    const map = { getZoom: () => 5.995, isZooming: () => true, getSource: () => ({}) };
    const controller = new NativeClusterMotionController({ getMap: () => map as any, reducedMotion: () => false, enabled: () => true, duration: () => 210, limit: () => 1000 }) as any;
    controller.before = new Map([['c:1', { key: 'c:1', id: 1 }]]);
    controller.capture = () => controller.before;
    controller.draw = vi.fn(); controller.armed = true; controller.zoom = 6; controller.lastCameraZoom = 6;
    const reveal = vi.spyOn(controller, 'revealSnapshot');
    controller.onRender();
    expect(controller.armed).toBe(true);
    expect(reveal).not.toHaveBeenCalled();
  });
  it('retains the scene while source tiles settle and bounds that wait independently of pairing', () => {
    vi.useFakeTimers();
    try {
      const map = { getZoom: () => 8, isZooming: () => false, isSourceLoaded: () => false, getSource: () => ({}) };
      const controller = new NativeClusterMotionController({ getMap: () => map as any, reducedMotion: () => false, enabled: () => true, duration: () => 210, limit: () => 1200 }) as any;
      controller.before = new Map([['c:1', { key: 'c:1', id: 1 }]]);
      controller.capture = () => controller.before;
      controller.applyMask = vi.fn(); controller.draw = vi.fn();
      controller.armed = true; controller.zoom = 6; controller.lastCameraZoom = 8;
      const cancel = vi.spyOn(controller, 'cancel');
      controller.onRender();
      vi.advanceTimersByTime(1500);
      expect(controller.armed).toBe(true); expect(cancel).not.toHaveBeenCalled();
      vi.advanceTimersByTime(500);
      expect(cancel).toHaveBeenCalledWith(false, 'source-timeout');
    } finally { vi.useRealTimers(); }
  });
  it('continues the existing visible cue when another zoom starts during playback', () => {
    const controller = new NativeClusterMotionController({ getMap: () => ({ getZoom: () => 10, getBounds: () => ({ getWest: () => -1, getEast: () => 1, getSouth: () => -1, getNorth: () => 1 }) } as any), reducedMotion: () => false, enabled: () => true, duration: () => 210, limit: () => 1000 }) as any;
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

describe('newly exposed regions', () => {
  it('never blanket-hides marks outside the original viewport', () => {
    const map = { getSource: () => ({}), setFeatureState: vi.fn(), removeFeatureState: vi.fn(), redraw: vi.fn(), on: vi.fn(), off: vi.fn(), triggerRepaint: vi.fn() };
    const controller = new NativeClusterMotionController({ getMap: () => map as any, reducedMotion: () => false, enabled: () => true, duration: () => 210, limit: () => 1200 }) as any;
    controller.footprint = [-125, 30, -115, 42];
    controller.presentNodes = new Map([
      ['c:1', { key: 'c:1', id: 1, coordinates: [-120, 35] }],
      ['c:2', { key: 'c:2', id: 2, coordinates: [-75, 40] }],
    ]);
    controller.mask(new Set(['c:old']), true);
    expect([...controller.hidden.keys()]).toEqual(['c:1']);
    controller.mask(new Set(), false);
    expect(controller.hidden.size).toBe(0);
  });
});
