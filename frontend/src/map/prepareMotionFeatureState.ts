import type { Map as MapLibreMap } from 'maplibre-gl';

/** Run only in the custom layer's prerender, after native symbol placement.
 * Flush the locations source's paint attributes before its symbols draw.
 * Never render the scene again or advance camera/source-selection tasks.
 * Version-locked by check-cluster-cache-engine.mjs.
 */
export function prepareMotionFeatureState(map: MapLibreMap): void {
  const native = map as unknown as {
    style?: { tileManagers?: { locations?: { prepare(context: unknown): void } } };
    painter?: { context: unknown };
  };
  const source = native.style?.tileManagers?.locations;
  if (source && native.painter) source.prepare(native.painter.context);
}
