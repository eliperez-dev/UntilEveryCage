import { describe, expect, it } from 'vitest';
import { DEFAULT_MAP_DISPLAY_SETTINGS, mergeMapDisplaySettings } from '../../src/design-lab/components/mapDisplaySettings';
describe('map display settings requests', () => {
  it('shares initial defaults with the renderer and changes only explicitly supplied values', () => {
    expect(DEFAULT_MAP_DISPLAY_SETTINGS).toEqual({ clusterMode: 'auto', pinScale: 0.8, optimizedPins: false, coordinateRadius: 6.5 });
    expect(mergeMapDisplaySettings(DEFAULT_MAP_DISPLAY_SETTINGS, { optimizedPins: true })).toEqual({ ...DEFAULT_MAP_DISPLAY_SETTINGS, optimizedPins: true });
    expect(DEFAULT_MAP_DISPLAY_SETTINGS.optimizedPins).toBe(false);
  });
  it('clamps sizes, preserves values for malformed patches and accepts all three cluster states', () => {
    expect(mergeMapDisplaySettings(DEFAULT_MAP_DISPLAY_SETTINGS, { pinScale: 9, coordinateRadius: -1 })).toEqual({ ...DEFAULT_MAP_DISPLAY_SETTINGS, pinScale: 1.6, coordinateRadius: 3 });
    expect(mergeMapDisplaySettings(DEFAULT_MAP_DISPLAY_SETTINGS, { pinScale: NaN, coordinateRadius: Infinity, optimizedPins: 'yes', clusterMode: 'maybe' } as any)).toEqual(DEFAULT_MAP_DISPLAY_SETTINGS);
    for (const clusterMode of ['auto', 'on', 'off'] as const) expect(mergeMapDisplaySettings(DEFAULT_MAP_DISPLAY_SETTINGS, { clusterMode }).clusterMode).toBe(clusterMode);
  });
});
