export const DEFAULT_FACILITY_PIN_SCALE = 0.8;

/** Icon sizes/offsets share their anchor; cluster bodies and location areas stay independent. */
export function applyFacilityPinScale(map: {
  getLayer(id: string): unknown;
  setLayoutProperty(id: string, property: string, value: number): unknown;
}, requested = DEFAULT_FACILITY_PIN_SCALE): void {
  const scale = Number.isFinite(requested) ? Math.max(0.6, Math.min(1.6, requested)) : DEFAULT_FACILITY_PIN_SCALE;
  for (const [id, base] of [
    ['v1-source-pins', 0.5], ['v1-source-shadows', 1],
    ['approx-reference-pins', 0.5], ['approx-reference-shadows', 1],
    ['approx-reference-points', 0.5], ['approx-reference-cue', 0.5],
    ['mvt-v1-source-pins', 0.5], ['mvt-v1-source-shadows', 1], ['mvt-reference-center', 0.5],
  ] as const) {
    if (map.getLayer(id)) map.setLayoutProperty(id, 'icon-size', base * scale);
  }
}
