import { describe, expect, it } from 'vitest';
import streetsRaw from '../../src/map/assets/worldStreetsManifest.json?raw';
import satelliteRaw from '../../src/map/assets/worldSatelliteManifest.json?raw';
import { getWorldBaselineSettings, updateWorldBaselineSettings, worldTileId } from '../../src/map/worldBaseline';

describe('self-hosted low-zoom world baseline', () => {
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
});
