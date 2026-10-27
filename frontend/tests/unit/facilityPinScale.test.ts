import { describe, expect, it, vi } from 'vitest';
import { applyFacilityPinScale, DEFAULT_FACILITY_PIN_SCALE } from '../../src/design-lab/components/facilityPinScale';
describe('facility pin sizing', () => {
  it('defaults every public/MVT pin and its attached art to 80% without changing cluster/data/uncertainty channels', () => {
    const changes: unknown[][] = [];
    const map = { getLayer: () => ({}), setLayoutProperty: (...args: unknown[]) => changes.push(args), setData: vi.fn(), setClusterOptions: vi.fn(), setPaintProperty: vi.fn() };
    expect(DEFAULT_FACILITY_PIN_SCALE).toBe(0.8); applyFacilityPinScale(map);
    for (const layer of ['v1-source-pins', 'approx-reference-pins', 'approx-reference-points', 'approx-reference-cue', 'mvt-v1-source-pins', 'mvt-reference-center']) expect(changes).toContainEqual([layer, 'icon-size', 0.4]);
    for (const layer of ['v1-source-shadows', 'approx-reference-shadows', 'mvt-v1-source-shadows']) expect(changes).toContainEqual([layer, 'icon-size', 0.8]);
    expect(changes).toHaveLength(9);
    expect(map.setData).not.toHaveBeenCalled(); expect(map.setClusterOptions).not.toHaveBeenCalled(); expect(map.setPaintProperty).not.toHaveBeenCalled();
  });
  it('clamps live tuning and rejects non-finite sizing, retaining anchor offsets', () => {
    const map = { getLayer: (id: string) => id === 'v1-source-pins' ? {} : undefined, setLayoutProperty: vi.fn() };
    for (const [requested, size] of [[0, 0.3], [9, 0.8], [NaN, 0.4], [1.2, 0.6]]) {
      map.setLayoutProperty.mockClear(); applyFacilityPinScale(map, requested); expect(map.setLayoutProperty).toHaveBeenCalledTimes(1); expect(map.setLayoutProperty).toHaveBeenCalledWith('v1-source-pins', 'icon-size', size);
    }
  });
});
