import type { MapDisplaySettings } from '../contract';
import { DEFAULT_FACILITY_PIN_SCALE } from './facilityPinScale';

export const DEFAULT_MAP_DISPLAY_SETTINGS: MapDisplaySettings = Object.freeze({
  clusterMode: 'auto', pinScale: DEFAULT_FACILITY_PIN_SCALE, optimizedPins: false, coordinateRadius: 6.5,
});

/** Accept partial UI requests, retaining current values for malformed input. */
export function mergeMapDisplaySettings(current: MapDisplaySettings, patch: Partial<MapDisplaySettings>): MapDisplaySettings {
  const bounded = (value: unknown, fallback: number, low: number, high: number) => typeof value === 'number' && Number.isFinite(value) ? Math.max(low, Math.min(high, value)) : fallback;
  return {
    clusterMode: patch.clusterMode === 'auto' || patch.clusterMode === 'on' || patch.clusterMode === 'off' ? patch.clusterMode : current.clusterMode,
    pinScale: bounded(patch.pinScale, current.pinScale, 0.6, 1.6),
    optimizedPins: typeof patch.optimizedPins === 'boolean' ? patch.optimizedPins : current.optimizedPins,
    coordinateRadius: bounded(patch.coordinateRadius, current.coordinateRadius, 3, 12),
  };
}
