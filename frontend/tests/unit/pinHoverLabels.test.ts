import { describe, expect, it, vi } from 'vitest';
import { createPinHoverLabels, individualHoverPin } from '../../src/design-lab/pinHoverLabels';
import { createSearchBoundsArea } from '../../src/design-lab/components/mapSurfaceLayers';

const id = '550e8400-e29b-41d4-a716-446655440000';
const other = '550e8400-e29b-41d4-a716-446655440001';
const label = { name: 'Synthetic public name', categoryKey: 'slaughter' };
const signal = () => new AbortController().signal;
describe('public pin hover labels', () => {
  it('requires an active verified context and individual UUID before any read', async () => {
    const read = vi.fn(async () => label), cache = createPinHoverLabels(read);
    expect(await cache.resolve(id, signal())).toBeNull();
    cache.setContext('release:manifest:restriction:filters');
    expect(await cache.resolve('a'.repeat(32), signal())).toBeNull();
    expect(read).not.toHaveBeenCalled();
  });
  it('retains only a bounded, short-lived label cache and expires without refreshing TTL', async () => {
    let now = 0;
    const read = vi.fn(async () => label), cache = createPinHoverLabels(read, () => now, 1, 30);
    cache.setContext('first');
    await cache.resolve(id, signal()); now = 20; await cache.resolve(id, signal());
    expect(read).toHaveBeenCalledTimes(1);
    now = 31; await cache.resolve(id, signal());
    expect(read).toHaveBeenCalledTimes(2);
    await cache.resolve(other, signal()); await cache.resolve(id, signal());
    expect(read).toHaveBeenCalledTimes(4);
  });
  it('aborts and discards pending results across restriction/filter/active context changes', async () => {
    let finish!: (value: typeof label) => void;
    let pendingSignal!: AbortSignal;
    const read = vi.fn((_id: string, incoming: AbortSignal) => { pendingSignal = incoming; return new Promise<typeof label>(resolve => { finish = resolve; }); });
    const cache = createPinHoverLabels(read);
    cache.setContext('first'); const pending = cache.resolve(id, signal());
    cache.setContext('new-restrictions'); expect(pendingSignal.aborted).toBe(true);
    finish(label); expect(await pending).toBeNull();
    cache.setContext(null); expect(await cache.resolve(id, signal())).toBeNull();
  });
  it('rejects invalid, restricted, empty and aborted reads, without negative cache or stale names', async () => {
    const controller = new AbortController();
    const read = vi.fn().mockRejectedValueOnce(new Error('404')).mockResolvedValueOnce({ ...label, categoryKey: 'private_key' })
      .mockResolvedValueOnce({ ...label, name: '' }).mockResolvedValue(label);
    const cache = createPinHoverLabels(read); cache.setContext('first');
    for (let index = 0; index < 3; index++) expect(await cache.resolve(id, signal())).toBeNull();
    controller.abort(); expect(await cache.resolve(id, controller.signal)).toBeNull();
    expect(await cache.resolve(id, signal())).toEqual(label);
    expect(read).toHaveBeenCalledTimes(4);
  });
  it('cancels a read when pointer leaves even if the transport ignores abort', async () => {
    const controller = new AbortController();
    let finish!: (value: typeof label) => void;
    const cache = createPinHoverLabels(() => new Promise(resolve => { finish = resolve; }));
    cache.setContext('first'); const pending = cache.resolve(id, controller.signal);
    controller.abort(); finish(label); expect(await pending).toBeNull();
  });
  it('allows ordinary source/approximate pin UUIDs but rejects clusters and opaque aggregate keys', () => {
    const point = { geometry: { type: 'Point', coordinates: [1, 50] }, properties: { key: id, kind: 'reference', weight: 1 } };
    expect(individualHoverPin(point)).toEqual({ id, coordinates: [1, 50] });
    for (const properties of [{ key: 'a'.repeat(32) }, { key: id, cluster: true }, { key: id, cluster_id: 3 }, { key: id, kind: 'aggregate' }, { key: id, weight: 2 }]) {
      expect(individualHoverPin({ ...point, properties })).toBeNull();
    }
    expect(individualHoverPin({ ...point, geometry: { type: 'Polygon', coordinates: [] } })).toBeNull();
  });
});
describe('snapshot area perimeter', () => {
  it('preserves the exact queried bounds in a closed ring rather than camera-dependent geometry', () => {
    const bounds = { west: -5, south: 40, east: 3, north: 50 };
    const area = createSearchBoundsArea(bounds);
    expect(area.features[0]?.geometry.coordinates[0]).toEqual([[-5, 40], [3, 40], [3, 50], [-5, 50], [-5, 40]]);
    expect(area.features[0]?.properties).toEqual({ scope: 'search-area' });
    expect(bounds).toEqual({ west: -5, south: 40, east: 3, north: 50 });
  });
  it('clears and fails closed for bounds the query would reject', () => {
    expect(createSearchBoundsArea(null).features).toEqual([]);
    for (const bounds of [{ west: 5, east: -5, south: 0, north: 10 }, { west: -180, east: 181, south: 0, north: 10 }, { west: 0, east: 10, south: 0, north: NaN }])
      expect(createSearchBoundsArea(bounds).features).toEqual([]);
  });
});
