import { describe, expect, it, vi } from 'vitest';
import { RASTER_READY_TIMEOUT_MS, waitForSourceReady, waitForTerrainSource } from '../../src/design-lab/components/terrainReady';

function sourceMap() {
  const listeners = new Map<string, Set<(event: { sourceId: string; sourceDataType?: string }) => void>>();
  const map = {
    ready: false, getSource: () => ({}), isSourceLoaded: () => map.ready,
    on: (type: string, listener: (event: { sourceId: string }) => void) => { const group = listeners.get(type) ?? new Set(); group.add(listener); listeners.set(type, group); },
    off: (type: string, listener: (event: { sourceId: string }) => void) => { listeners.get(type)?.delete(listener); },
    fire: (type: string, sourceId: string, sourceDataType?: string) => { for (const listener of [...listeners.get(type) ?? []]) listener({ sourceId, sourceDataType }); },
    listenerCount: () => [...listeners.values()].reduce((count, group) => count + group.size, 0),
  };
  return map;
}

describe('terrain readiness before the first tilt', () => {
  it('does not accept new metadata while the previous raster tiles are still loaded', async () => {
    const map = sourceMap(), done = vi.fn();
    const pending = waitForSourceReady(map, 'base', new AbortController().signal).then(done);
    map.ready = true; map.fire('sourcedata', 'base', 'metadata');
    map.fire('render', ''); map.fire('idle', '');
    await Promise.resolve(); expect(done).not.toHaveBeenCalled();
    map.ready = false; map.fire('sourcedata', 'base', 'content');
    await Promise.resolve(); expect(done).not.toHaveBeenCalled();
    map.ready = true; map.fire('sourcedata', 'base', 'content');
    await pending; expect(done).toHaveBeenCalledWith(true); expect(map.listenerCount()).toBe(0);
  });
  it('requires fresh metadata and content after setTiles, including initial and frame readiness checks', async () => {
    const map = sourceMap(), done = vi.fn(); map.ready = true;
    const pending = waitForSourceReady(map, 'base', new AbortController().signal, RASTER_READY_TIMEOUT_MS, { requireFreshContent: true }).then(done);
    map.fire('render', ''); map.fire('idle', ''); map.fire('sourcedata', 'base', 'content');
    await Promise.resolve(); expect(done).not.toHaveBeenCalled();
    map.fire('sourcedata', 'base', 'metadata'); map.fire('render', ''); map.fire('idle', '');
    await Promise.resolve(); expect(done).not.toHaveBeenCalled();
    map.ready = false; map.fire('sourcedata', 'base', 'content'); map.fire('render', '');
    await Promise.resolve(); expect(done).not.toHaveBeenCalled();
    map.ready = true; map.fire('render', '');
    await pending; expect(done).toHaveBeenCalledWith(true); expect(map.listenerCount()).toBe(0);
    // Unchanged healthy sources still return immediately without listeners.
    await expect(waitForSourceReady(map, 'base', new AbortController().signal)).resolves.toBe(true);
    expect(map.listenerCount()).toBe(0);
  });
  it('allows raster preparation beyond the DEM bound without extending terrain startup', async () => {
    vi.useFakeTimers();
    try {
      const map = sourceMap(), done = vi.fn();
      const raster = waitForSourceReady(map, 'candidate-base', new AbortController().signal, RASTER_READY_TIMEOUT_MS).then(done);
      const terrain = waitForTerrainSource(map, 'dem', new AbortController().signal);
      await vi.advanceTimersByTimeAsync(10_000);
      await expect(terrain).resolves.toBe(false); expect(done).not.toHaveBeenCalled();
      map.ready = true; map.fire('sourcedata', 'candidate-base');
      await raster; expect(done).toHaveBeenCalledWith(true); expect(map.listenerCount()).toBe(0);
    } finally { vi.useRealTimers(); }
  });
  it('keeps the longer raster wait bounded and cancellable', async () => {
    vi.useFakeTimers();
    try {
      const map = sourceMap(), controller = new AbortController();
      const cancelled = waitForSourceReady(map, 'candidate-base', controller.signal, RASTER_READY_TIMEOUT_MS);
      controller.abort(); await expect(cancelled).resolves.toBe(false); expect(map.listenerCount()).toBe(0);
      const failed = waitForSourceReady(map, 'candidate-base', new AbortController().signal, RASTER_READY_TIMEOUT_MS);
      map.fire('error', 'candidate-base'); await expect(failed).resolves.toBe(false); expect(map.listenerCount()).toBe(0);
      const stalled = waitForSourceReady(map, 'candidate-base', new AbortController().signal, RASTER_READY_TIMEOUT_MS);
      await vi.advanceTimersByTimeAsync(RASTER_READY_TIMEOUT_MS);
      await expect(stalled).resolves.toBe(false); expect(map.listenerCount()).toBe(0);
    } finally { vi.useRealTimers(); }
  });
  it('shares the same readiness lifecycle with raster candidate and base sources', async () => {
    expect(waitForTerrainSource).toBe(waitForSourceReady);
    const map = sourceMap(), pending = waitForSourceReady(map, 'base-candidate', new AbortController().signal);
    map.fire('sourcedata', 'base-candidate');
    map.ready = true; map.fire('idle', '');
    await expect(pending).resolves.toBe(true); expect(map.listenerCount()).toBe(0);
  });
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
  it('detects readiness that changes during native tile retention after the last source event', async () => {
    const map = sourceMap(), done = vi.fn();
    const pending = waitForTerrainSource(map, 'dem', new AbortController().signal).then(done);
    map.fire('sourcedata', 'dem'); await Promise.resolve(); expect(done).not.toHaveBeenCalled();
    // Native render removes a pending tile that is no longer retained. There
    // need not be another DEM sourcedata event, and imagery may remain busy.
    map.ready = true; map.fire('render', ''); await pending;
    expect(done).toHaveBeenCalledWith(true); expect(done).toHaveBeenCalledTimes(1);
    expect(map.listenerCount()).toBe(0);
  });
  it('checks only DEM readiness on render/idle and removes all new listeners on abort', async () => {
    const map = sourceMap(), controller = new AbortController(), done = vi.fn();
    const pending = waitForTerrainSource(map, 'dem', controller.signal).then(done);
    map.fire('render', ''); map.fire('idle', ''); await Promise.resolve(); expect(done).not.toHaveBeenCalled();
    controller.abort(); await pending; expect(done).toHaveBeenCalledWith(false); expect(map.listenerCount()).toBe(0);
    map.ready = true; map.fire('render', ''); map.fire('idle', ''); expect(done).toHaveBeenCalledTimes(1);
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
