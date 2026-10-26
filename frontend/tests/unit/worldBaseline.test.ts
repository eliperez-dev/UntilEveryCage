import { afterEach, describe, expect, it, vi } from 'vitest';
import { readFileSync } from 'node:fs';
import { webcrypto } from 'node:crypto';
import streetsRaw from '../../src/map/assets/worldStreetsManifest.json?raw';
import satelliteRaw from '../../src/map/assets/worldSatelliteManifest.json?raw';
import { getWorldBaselineSettings, updateWorldBaselineSettings, worldTileId } from '../../src/map/worldBaseline';

describe('self-hosted low-zoom world baseline', () => {
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });
  it('addresses every tile exactly once in the bounded cumulative Hilbert table', () => {
    const ids = new Set<number>();
    for (let z = 0; z <= 5; z++) for (let x = 0; x < 2 ** z; x++) for (let y = 0; y < 2 ** z; y++) ids.add(worldTileId(z, x, y));
    expect(ids.size).toBe(1365);
    expect(Math.min(...ids)).toBe(0); expect(Math.max(...ids)).toBe(1364);
    expect([worldTileId(1, 0, 0), worldTileId(1, 0, 1), worldTileId(1, 1, 1), worldTileId(1, 1, 0)]).toEqual([1, 2, 3, 4]);
    expect(() => worldTileId(6, 0, 0)).toThrow();
    expect(() => worldTileId(1, 2, 0)).toThrow();
  });
  it('keeps per-zoom downloads real, content-addressed, and inside the measured budget', () => {
    let total = 0, through4 = 0;
    for (const raw of [streetsRaw, satelliteRaw]) {
      const manifest = JSON.parse(raw);
      expect(manifest.assets.map((asset: any) => asset.zoom)).toEqual([0, 1, 2, 3, 4, 5]);
      expect(manifest.tiles).toHaveLength(1365);
      for (const asset of manifest.assets) {
        expect(asset.file).toContain(asset.sha256.slice(0, 12));
        total += asset.bytes; if (asset.zoom <= 4) through4 += asset.bytes;
      }
      for (const [chunk, offset, length] of manifest.tiles) expect(offset + length).toBeLessThanOrEqual(manifest.assets[chunk].bytes);
    }
    expect(total).toBe(16899100); expect(through4).toBe(6716971);
    expect(total).toBeLessThan(24 * 1048576);
  });
  it('bounds every advertised warm-up level and budget', () => {
    for (let maxZoom = 0; maxZoom <= 5; maxZoom++) expect(updateWorldBaselineSettings({ maxZoom }).maxZoom).toBe(maxZoom);
    updateWorldBaselineSettings({ maxZoom: 50, maxBytes: 1 });
    expect(getWorldBaselineSettings()).toMatchObject({ maxZoom: 5, maxBytes: 8 * 1048576 });
  });
  it('persists RAM hits after cancellation without letting an old writer delete the new entry', async () => {
    vi.resetModules();
    vi.stubGlobal('crypto', webcrypto);
    vi.spyOn(document, 'hidden', 'get').mockReturnValue(false);
    const entries = new Map<string, Response>();
    let releaseFirst!: () => void, firstPutStarted!: () => void;
    const firstPut = new Promise<void>(resolve => { firstPutStarted = resolve; });
    const release = new Promise<void>(resolve => { releaseFirst = resolve; });
    let writes = 0;
    const cache = {
      keys: async () => [...entries.keys()].map(url => new Request(url)),
      match: async (url: string) => entries.get(url)?.clone(),
      delete: async (key: string | Request) => entries.delete(typeof key === 'string' ? key : key.url),
      put: async (url: string, response: Response) => {
        if (writes++ === 0) { firstPutStarted(); await release; }
        entries.set(url, response.clone());
      },
    };
    vi.stubGlobal('caches', { open: async () => cache });
    const fetcher = vi.fn(async (input: string) => {
      const file = new URL(input).pathname.split('/').at(-1)!;
      const assets = [...JSON.parse(streetsRaw).assets, ...JSON.parse(satelliteRaw).assets];
      if (!assets.some(asset => asset.zoom === 0 && asset.file === file)) throw new Error('Unexpected test asset');
      return new Response(new Uint8Array(readFileSync(`${process.cwd()}/public/world-baseline/${file}`)));
    });
    vi.stubGlobal('fetch', fetcher);
    const baseline = await import('../../src/map/worldBaseline');
    baseline.updateWorldBaselineSettings({ enabled: true, maxZoom: 0 });
    const older = baseline.warmWorldBaseline();
    await Promise.race([firstPut, older.then(() => { throw new Error(`Warm-up ended before persisting: ${JSON.stringify(baseline.getWorldBaselineDiagnostics())}; requests=${fetcher.mock.calls.length}`); })]);
    baseline.cancelWorldBaselineWarmup();
    await baseline.warmWorldBaseline();
    releaseFirst();
    await older;
    expect(entries.size).toBe(2);
    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(baseline.getWorldBaselineDiagnostics().readyChunks).toBe(2);
  });
});
