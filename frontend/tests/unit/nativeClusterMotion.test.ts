import { describe, expect, it, vi } from 'vitest';
import { clusterMotionImage, clusterMotionKey, NativeClusterMotionController } from '../../src/design-lab/components/nativeClusterMotion';

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
