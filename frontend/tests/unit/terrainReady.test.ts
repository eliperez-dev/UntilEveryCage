import { describe, expect, it, vi } from 'vitest';
import { waitForTerrainSource } from '../../src/design-lab/components/terrainReady';

function sourceMap() {
  const listeners = new Map<string, Set<(event: { sourceId: string }) => void>>();
  const map = {
    ready: false, getSource: () => ({}), isSourceLoaded: () => map.ready,
    on: (type: string, listener: (event: { sourceId: string }) => void) => { const group = listeners.get(type) ?? new Set(); group.add(listener); listeners.set(type, group); },
    off: (type: string, listener: (event: { sourceId: string }) => void) => { listeners.get(type)?.delete(listener); },
    fire: (type: string, sourceId: string) => { for (const listener of [...listeners.get(type) ?? []]) listener({ sourceId }); },
    listenerCount: () => [...listeners.values()].reduce((count, group) => count + group.size, 0),
  };
  return map;
}

describe('terrain readiness before the first tilt', () => {
  it('waits for actual DEM completion and ignores unrelated raster events', async () => {
    const map = sourceMap(), done = vi.fn();
    const pending = waitForTerrainSource(map, 'dem', new AbortController().signal).then(done);
    map.fire('sourcedata', 'dem'); await Promise.resolve(); expect(done).not.toHaveBeenCalled();
    map.ready = true; map.fire('sourcedata', 'base'); await Promise.resolve(); expect(done).not.toHaveBeenCalled();
    map.fire('sourcedata', 'dem'); await pending; expect(done).toHaveBeenCalledWith(true); expect(map.listenerCount()).toBe(0);
  });
  it('cleans up on cancellation without waiting for tiles or triggering a second transition', async () => {
    const map = sourceMap(), controller = new AbortController();
    const pending = waitForTerrainSource(map, 'dem', controller.signal);
    controller.abort(); await expect(pending).resolves.toBe(false); expect(map.listenerCount()).toBe(0);
    map.ready = true; map.fire('sourcedata', 'dem'); expect(map.listenerCount()).toBe(0);
  });
  it('distinguishes DEM failure from unrelated errors and reuses already loaded elevation', async () => {
    const map = sourceMap(), done = vi.fn();
    const pending = waitForTerrainSource(map, 'dem', new AbortController().signal).then(done);
    map.fire('error', 'base'); await Promise.resolve(); expect(done).not.toHaveBeenCalled();
    map.fire('error', 'dem'); await pending; expect(done).toHaveBeenCalledWith(false); expect(map.listenerCount()).toBe(0);
    map.ready = true; await expect(waitForTerrainSource(map, 'dem', new AbortController().signal)).resolves.toBe(true); expect(map.listenerCount()).toBe(0);
  });
  it('ends a stalled elevation request and releases its listeners', async () => {
    vi.useFakeTimers();
    try {
      const map = sourceMap(), pending = waitForTerrainSource(map, 'dem', new AbortController().signal, 100);
      await vi.advanceTimersByTimeAsync(100);
      await expect(pending).resolves.toBe(false); expect(map.listenerCount()).toBe(0);
    } finally { vi.useRealTimers(); }
  });
});
